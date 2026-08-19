"""Discord OAuth, encrypted database credentials, and server-side sessions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
from typing import Optional
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from assignments import database_assignments


DISCORD_API = "https://discord.com/api/v10"
DISCORD_AUTHORIZE = "https://discord.com/oauth2/authorize"
SESSION_COOKIE = "recallibrate_session"
OAUTH_STATE_COOKIE = "recallibrate_oauth_state"
SESSION_DAYS = 14

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _truthy(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _csv_set(name: str) -> set[str]:
    return {value.strip() for value in os.getenv(name, "").split(",") if value.strip()}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DiscordUser:
    discord_id: str
    username: str
    display_name: str
    avatar_url: Optional[str]
    has_database: bool
    database_label: Optional[str]


class AuthStore:
    """Small persistent control store. Database passwords are always encrypted."""

    def __init__(self) -> None:
        default_path = Path(__file__).resolve().parent / "recallibrate-state.sqlite3"
        self.path = Path(os.getenv("RECALLIBRATE_STATE_PATH", str(default_path)))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.allowed_discord_ids = _csv_set("RECALLIBRATE_ALLOWED_DISCORD_IDS")
        self.allow_any_discord_user = _truthy("RECALLIBRATE_ALLOW_ANY_DISCORD_USER")
        self.allowed_database_hosts = {host.lower() for host in _csv_set("RECALLIBRATE_ALLOWED_DB_HOSTS")}
        self.database_assignments = database_assignments()
        self.allow_self_service_databases = _truthy("RECALLIBRATE_ALLOW_SELF_SERVICE_DATABASES")
        self.secure_cookies = _truthy("RECALLIBRATE_SECURE_COOKIES", default=True)
        self.client_id = os.getenv("DISCORD_CLIENT_ID", "")
        self.client_secret = os.getenv("DISCORD_CLIENT_SECRET", "")
        self.redirect_uri = os.getenv("DISCORD_REDIRECT_URI", "")
        key = os.getenv("RECALLIBRATE_CREDENTIAL_KEY", "")
        self.cipher = Fernet(key.encode("ascii")) if key else None
        if not _truthy("RECALLIBRATE_PORTFOLIO_ONLY"):
            self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    discord_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    avatar_hash TEXT,
                    encrypted_database_url BLOB,
                    database_label TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_login_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    discord_id TEXT NOT NULL REFERENCES users(discord_id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS sessions_expires_at_idx ON sessions(expires_at);
                """
            )

    def require_oauth_configuration(self) -> None:
        missing = [
            name
            for name, value in (
                ("DISCORD_CLIENT_ID", self.client_id),
                ("DISCORD_CLIENT_SECRET", self.client_secret),
                ("DISCORD_REDIRECT_URI", self.redirect_uri),
            )
            if not value
        ]
        if not self.allow_any_discord_user and not self.allowed_discord_ids:
            missing.append("RECALLIBRATE_ALLOWED_DISCORD_IDS")
        if missing:
            raise HTTPException(status_code=503, detail=f"Authentication is not configured: {', '.join(missing)}.")

    def require_cipher(self) -> Fernet:
        if not self.cipher:
            raise HTTPException(status_code=503, detail="RECALLIBRATE_CREDENTIAL_KEY is not configured.")
        return self.cipher

    def oauth_start(self) -> RedirectResponse:
        self.require_oauth_configuration()
        state = secrets.token_urlsafe(32)
        query = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "scope": "identify",
                "state": state,
            }
        )
        response = RedirectResponse(f"{DISCORD_AUTHORIZE}?{query}", status_code=302)
        response.set_cookie(
            OAUTH_STATE_COOKIE,
            state,
            max_age=600,
            httponly=True,
            secure=self.secure_cookies,
            samesite="lax",
        )
        return response

    async def oauth_callback(self, request: Request, code: str, state: str) -> RedirectResponse:
        self.require_oauth_configuration()
        expected_state = request.cookies.get(OAUTH_STATE_COOKIE)
        if not expected_state or not secrets.compare_digest(expected_state, state):
            raise HTTPException(status_code=400, detail="Discord login state did not match. Please try again.")

        profile = await asyncio.to_thread(self._discord_profile, code)

        discord_id = str(profile["id"])
        if not self.discord_user_allowed(discord_id):
            raise HTTPException(status_code=403, detail="This Discord account is not invited to Recallibrate.")

        now = _utcnow().isoformat()
        username = str(profile.get("username") or discord_id)
        display_name = str(profile.get("global_name") or username)
        avatar_hash = profile.get("avatar")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users (discord_id, username, display_name, avatar_hash, created_at, updated_at, last_login_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(discord_id) DO UPDATE SET
                    username = excluded.username,
                    display_name = excluded.display_name,
                    avatar_hash = excluded.avatar_hash,
                    updated_at = excluded.updated_at,
                    last_login_at = excluded.last_login_at
                """,
                (discord_id, username, display_name, avatar_hash, now, now, now),
            )
            conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))

        session_token = secrets.token_urlsafe(48)
        expires_at = (_utcnow() + timedelta(days=SESSION_DAYS)).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (token_hash, discord_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (_token_hash(session_token), discord_id, now, expires_at),
            )

        response = RedirectResponse("/", status_code=302)
        response.delete_cookie(OAUTH_STATE_COOKIE)
        response.set_cookie(
            SESSION_COOKIE,
            session_token,
            max_age=SESSION_DAYS * 86400,
            httponly=True,
            secure=self.secure_cookies,
            samesite="lax",
        )
        return response

    def _discord_profile(self, code: str) -> dict:
        token_body = urlencode(
            {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
            }
        ).encode("utf-8")
        token_request = UrlRequest(
            f"{DISCORD_API}/oauth2/token",
            data=token_body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urlopen(token_request, timeout=15) as response:
                access_token = json.load(response).get("access_token")
            if not access_token:
                raise HTTPException(status_code=400, detail="Discord could not complete that login.")
            user_request = UrlRequest(
                f"{DISCORD_API}/users/@me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            with urlopen(user_request, timeout=15) as response:
                return json.load(response)
        except HTTPError as error:
            raise HTTPException(status_code=400, detail="Discord could not complete that login.") from error
        except URLError as error:
            raise HTTPException(status_code=502, detail="Discord could not be reached. Please try again.") from error

    def current_user(self, request: Request) -> DiscordUser:
        token = request.cookies.get(SESSION_COOKIE)
        if not token:
            raise HTTPException(status_code=401, detail="Sign in with Discord to continue.")
        now = _utcnow().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT u.discord_id, u.username, u.display_name, u.avatar_hash,
                       u.encrypted_database_url IS NOT NULL AS has_database, u.database_label
                FROM sessions s
                JOIN users u ON u.discord_id = s.discord_id
                WHERE s.token_hash = ? AND s.expires_at > ?
                """,
                (_token_hash(token), now),
            ).fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Your Recallibrate session has expired.")
        if not self.discord_user_allowed(row["discord_id"]):
            raise HTTPException(status_code=403, detail="This Discord account is no longer invited to Recallibrate.")
        avatar_url = None
        if row["avatar_hash"]:
            avatar_url = f"https://cdn.discordapp.com/avatars/{row['discord_id']}/{row['avatar_hash']}.png?size=64"
        assignments = self.database_assignments.get(row["discord_id"], ())
        return DiscordUser(
            discord_id=row["discord_id"],
            username=row["username"],
            display_name=row["display_name"],
            avatar_url=avatar_url,
            has_database=bool(assignments or row["has_database"]),
            database_label=(assignments[0].label if len(assignments) == 1 else f"{len(assignments)} assigned databases") if assignments else row["database_label"],
        )

    def discord_user_allowed(self, discord_id: str) -> bool:
        return self.allow_any_discord_user or discord_id in self.allowed_discord_ids

    def database_choices_for(self, user: DiscordUser) -> list[dict[str, str]]:
        assignments = self.database_assignments.get(user.discord_id, ())
        if assignments:
            return [{"id": item.id, "label": item.label} for item in assignments]
        if self.allow_self_service_databases and user.has_database:
            return [{"id": "legacy", "label": user.database_label or "PostgreSQL"}]
        return []

    def database_url_for(self, user: DiscordUser, database_id: Optional[str]) -> str:
        assignments = self.database_assignments.get(user.discord_id, ())
        if assignments:
            selected = database_id or (assignments[0].id if len(assignments) == 1 else None)
            for assignment in assignments:
                if assignment.id == selected:
                    return assignment.url
            raise HTTPException(status_code=403, detail="That database is not assigned to this Discord account.")
        if not self.allow_self_service_databases:
            raise HTTPException(status_code=409, detail="No database is assigned to this Discord account yet.")
        if database_id not in {None, "legacy"}:
            raise HTTPException(status_code=403, detail="That database is not assigned to this Discord account.")
        cipher = self.require_cipher()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT encrypted_database_url FROM users WHERE discord_id = ?",
                (user.discord_id,),
            ).fetchone()
        if not row or not row["encrypted_database_url"]:
            raise HTTPException(status_code=409, detail="Connect a database before opening the workbench.")
        try:
            return cipher.decrypt(row["encrypted_database_url"]).decode("utf-8")
        except InvalidToken as error:
            raise HTTPException(status_code=503, detail="The saved database credential could not be decrypted.") from error

    def save_database_url(self, user: DiscordUser, database_url: str, label: str) -> None:
        encrypted = self.require_cipher().encrypt(database_url.encode("utf-8"))
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET encrypted_database_url = ?, database_label = ?, updated_at = ? WHERE discord_id = ?",
                (encrypted, label, _utcnow().isoformat(), user.discord_id),
            )

    def clear_database_url(self, user: DiscordUser) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET encrypted_database_url = NULL, database_label = NULL, updated_at = ? WHERE discord_id = ?",
                (_utcnow().isoformat(), user.discord_id),
            )

    def logout(self, request: Request) -> RedirectResponse:
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            with self._connect() as conn:
                conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
        response = RedirectResponse("/", status_code=303)
        response.delete_cookie(SESSION_COOKIE)
        return response


auth_store = AuthStore()
