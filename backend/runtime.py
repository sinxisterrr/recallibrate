"""Scoped Sage runtime pairing and proxy client for Recallibrate."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
import secrets
import socket
import sqlite3
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException


PAIRING_MINUTES = 10
REQUIRED_CAPABILITIES = {
    "database.tables.read",
    "database.records.read",
    "database.records.write",
    "database.records.delete",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeConnection:
    endpoint: str
    token: str
    label: str


class RuntimeStore:
    def __init__(self, path, cipher: Optional[Fernet]):
        self.path = path
        self.cipher = cipher
        self._initialize()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runtime_pairings (
                    id TEXT PRIMARY KEY,
                    discord_id TEXT NOT NULL REFERENCES users(discord_id) ON DELETE CASCADE,
                    endpoint TEXT NOT NULL,
                    code_hash TEXT NOT NULL UNIQUE,
                    expires_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runtime_connections (
                    discord_id TEXT PRIMARY KEY REFERENCES users(discord_id) ON DELETE CASCADE,
                    endpoint TEXT NOT NULL,
                    encrypted_token BLOB NOT NULL,
                    label TEXT NOT NULL,
                    verified_at TEXT NOT NULL
                );
                """
            )

    async def validate_endpoint(self, raw: str) -> str:
        parsed = urlparse(raw.strip())
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise HTTPException(status_code=400, detail="Enter the public HTTPS URL for your Sage runtime.")
        try:
            addresses = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        except socket.gaierror as error:
            raise HTTPException(status_code=400, detail="That Sage runtime host could not be found.") from error
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise HTTPException(status_code=403, detail="Sage runtime URLs must resolve to a public address.")
        port = f":{parsed.port}" if parsed.port else ""
        return f"https://{parsed.hostname}{port}"

    async def start(self, discord_id: str, endpoint: str) -> dict[str, str]:
        endpoint = await self.validate_endpoint(endpoint)
        pairing_id = secrets.token_urlsafe(18)
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        code = "".join(secrets.choice(alphabet) for _ in range(10))
        now = _utcnow()
        expires = now + timedelta(minutes=PAIRING_MINUTES)
        with self._connect() as conn:
            conn.execute("DELETE FROM runtime_pairings WHERE expires_at < ?", (now.isoformat(),))
            conn.execute(
                "INSERT INTO runtime_pairings (id,discord_id,endpoint,code_hash,expires_at,status,created_at,updated_at) VALUES (?,?,?,?,?,'pending',?,?)",
                (pairing_id, discord_id, endpoint, _digest(code.upper()), expires.isoformat(), now.isoformat(), now.isoformat()),
            )
        return {"id": pairing_id, "code": code, "expiresAt": expires.isoformat()}

    def status(self, discord_id: str, pairing_id: str) -> dict[str, Optional[str]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status,error,expires_at FROM runtime_pairings WHERE id=? AND discord_id=?",
                (pairing_id, discord_id),
            ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="That pairing request was not found.")
        return {"status": row["status"], "error": row["error"], "expiresAt": row["expires_at"]}

    async def claim(self, code: str, token: str) -> dict[str, bool]:
        if not code or not token:
            raise HTTPException(status_code=400, detail="Pairing code and scoped token are required.")
        now = _utcnow().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM runtime_pairings WHERE code_hash=? AND expires_at>=? AND status IN ('pending','failed')",
                (_digest(code.strip().upper()), now),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="That pairing code is invalid or expired.")
            conn.execute("UPDATE runtime_pairings SET status='claiming',error=NULL,updated_at=? WHERE id=?", (now, row["id"]))
        try:
            manifest = await self._request(row["endpoint"], "/.well-known/recallibrate-runtime", token, "GET", None)
            capabilities = set(manifest.get("capabilities") or [])
            if str(manifest.get("protocolVersion", "")).split(".")[0] != "1" or not REQUIRED_CAPABILITIES.issubset(capabilities):
                raise HTTPException(status_code=502, detail="That Sage runtime does not expose a compatible Recallibrate bridge.")
            probe = await self._request(row["endpoint"], "/v1/recallibrate/probe", token, "POST", {})
            if not probe.get("ok") or probe.get("credentialsExposed") is not False:
                raise HTTPException(status_code=502, detail="That Sage runtime did not pass its private database probe.")
            if not self.cipher:
                raise HTTPException(status_code=503, detail="RECALLIBRATE_CREDENTIAL_KEY is not configured.")
            encrypted = self.cipher.encrypt(token.encode("utf-8"))
            label = str(manifest.get("serviceName") or "Sage runtime")[:120]
            finished = _utcnow().isoformat()
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO runtime_connections (discord_id,endpoint,encrypted_token,label,verified_at) VALUES (?,?,?,?,?) ON CONFLICT(discord_id) DO UPDATE SET endpoint=excluded.endpoint,encrypted_token=excluded.encrypted_token,label=excluded.label,verified_at=excluded.verified_at",
                    (row["discord_id"], row["endpoint"], encrypted, label, finished),
                )
                conn.execute("UPDATE runtime_pairings SET status='connected',updated_at=? WHERE id=?", (finished, row["id"]))
            return {"ok": True}
        except Exception as error:
            message = error.detail if isinstance(error, HTTPException) else "Recallibrate could not verify that Sage runtime."
            with self._connect() as conn:
                conn.execute("UPDATE runtime_pairings SET status='failed',error=?,updated_at=? WHERE id=?", (str(message), _utcnow().isoformat(), row["id"]))
            if isinstance(error, HTTPException):
                raise
            raise HTTPException(status_code=502, detail=message) from error

    def connection(self, discord_id: str) -> Optional[RuntimeConnection]:
        with self._connect() as conn:
            row = conn.execute("SELECT endpoint,encrypted_token,label FROM runtime_connections WHERE discord_id=?", (discord_id,)).fetchone()
        if not row:
            return None
        if not self.cipher:
            raise HTTPException(status_code=503, detail="RECALLIBRATE_CREDENTIAL_KEY is not configured.")
        try:
            token = self.cipher.decrypt(row["encrypted_token"]).decode("utf-8")
        except InvalidToken as error:
            raise HTTPException(status_code=503, detail="The saved Sage runtime token could not be decrypted.") from error
        return RuntimeConnection(endpoint=row["endpoint"], token=token, label=row["label"])

    def disconnect(self, discord_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM runtime_connections WHERE discord_id=?", (discord_id,))

    async def proxy(self, connection: RuntimeConnection, path: str, method: str, payload: Optional[dict]) -> dict:
        return await self._request(connection.endpoint, path, connection.token, method, payload)

    async def _request(self, endpoint: str, path: str, token: str, method: str, payload: Optional[dict]) -> dict:
        def perform() -> dict:
            body = json.dumps(payload).encode("utf-8") if payload is not None else None
            request = Request(
                f"{endpoint}{path}", data=body, method=method,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json", **({"Content-Type": "application/json"} if body else {})},
            )
            try:
                with urlopen(request, timeout=30) as response:
                    return json.load(response)
            except HTTPError as error:
                try:
                    detail = json.load(error).get("error")
                except Exception:
                    detail = None
                raise HTTPException(status_code=error.code, detail=detail or "The Sage runtime rejected that request.") from error
            except URLError as error:
                raise HTTPException(status_code=502, detail="The Sage runtime could not be reached.") from error
        return await asyncio.to_thread(perform)
