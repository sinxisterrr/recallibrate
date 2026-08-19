"""Recallibrate's local PostgreSQL API and static frontend."""

import asyncio
from datetime import date
import ipaddress
import os
from pathlib import Path
import socket
from typing import Optional
from urllib.parse import urlparse

import asyncpg
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from auth import auth_store
from runtime import RuntimeStore


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
MAX_RESULTS = 500
LOW_CARDINALITY_LIMIT = 20
TEXT_TYPES = {"text", "character varying", "varchar", "character", "char"}
CAST_TYPES = {
    "boolean": "boolean",
    "smallint": "smallint",
    "integer": "integer",
    "bigint": "bigint",
    "numeric": "numeric",
    "decimal": "decimal",
    "real": "real",
    "double precision": "double precision",
    "date": "date",
    "timestamp without time zone": "timestamp without time zone",
    "timestamp with time zone": "timestamp with time zone",
    "uuid": "uuid",
}
PORTFOLIO_TABLES = {"sam_lore", "projects", "opinions", "skills", "favorites"}

PORTFOLIO_ONLY = os.getenv("RECALLIBRATE_PORTFOLIO_ONLY", "").lower() in {"1", "true", "yes"}
runtime_store = RuntimeStore(auth_store.path, auth_store.cipher) if not PORTFOLIO_ONLY else None

app = FastAPI(
    title="Recallibrate",
    docs_url=None if PORTFOLIO_ONLY else "/api/docs",
    openapi_url=None if PORTFOLIO_ONLY else "/api/openapi.json",
    redoc_url=None,
)


class ConnectRequest(BaseModel):
    db_url: str


class RuntimeStartRequest(BaseModel):
    endpoint: str


class RuntimeClaimRequest(BaseModel):
    action: str
    code: str
    token: str


class DatabaseRequest(BaseModel):
    database_id: Optional[str] = None


class TableRequest(DatabaseRequest):
    table_name: str


class SearchRequest(TableRequest):
    query: str = ""
    filters: Optional[dict[str, list[str]]] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    fuzzy: bool = False


class UpdateEntryRequest(TableRequest):
    record_id: str
    column_name: str
    new_text: str


class DeleteEntryRequest(TableRequest):
    record_id: str


class PortfolioSearchRequest(BaseModel):
    table_name: str
    query: str = ""
    filters: Optional[dict[str, list[str]]] = None
    fuzzy: bool = False


def quote_identifier(value: str) -> str:
    """Quote a PostgreSQL identifier after it has been schema-validated."""
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


async def table_schema(conn: asyncpg.Connection, table_name: str) -> list[asyncpg.Record]:
    columns = await conn.fetch(
        """
        SELECT column_name, data_type, udt_name, ordinal_position
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        ORDER BY ordinal_position
        """,
        table_name,
    )
    if not columns:
        raise HTTPException(status_code=404, detail="That table does not exist in the public schema.")
    return columns


async def connect_database(db_url: str) -> asyncpg.Connection:
    try:
        return await asyncpg.connect(db_url, timeout=12)
    except asyncpg.InvalidPasswordError as error:
        raise HTTPException(status_code=400, detail="The database rejected those credentials.") from error
    except (OSError, TimeoutError) as error:
        raise HTTPException(status_code=400, detail="Recallibrate could not reach that database host.") from error
    except asyncpg.PostgresError as error:
        raise HTTPException(status_code=400, detail=f"Database connection failed: {error}") from error


def portfolio_database_url() -> str:
    url = os.getenv("DEMO_DATABASE_URL")
    if not url:
        raise HTTPException(status_code=503, detail="The portfolio database is not configured yet.")
    return url


def require_portfolio_table(table_name: str) -> None:
    if table_name not in PORTFOLIO_TABLES:
        raise HTTPException(status_code=404, detail="That portfolio table does not exist.")


def require_local_mode() -> None:
    if PORTFOLIO_ONLY:
        raise HTTPException(status_code=404, detail="Not found.")


def require_self_service_databases() -> None:
    if not auth_store.allow_self_service_databases:
        raise HTTPException(status_code=404, detail="Not found.")


def current_database_url(request: Request, database_id: Optional[str] = None) -> str:
    user = auth_store.current_user(request)
    return auth_store.database_url_for(user, database_id)


def current_runtime(request: Request, database_id: Optional[str]):
    if database_id != "sage-runtime":
        return None
    user = auth_store.current_user(request)
    connection = runtime_store.connection(user.discord_id) if runtime_store else None
    if not connection:
        raise HTTPException(status_code=409, detail="Connect a Sage runtime before opening it.")
    return connection


def request_payload(payload: BaseModel) -> dict:
    return payload.model_dump(mode="json", exclude_none=True)


async def database_label(db_url: str) -> str:
    parsed = urlparse(db_url)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Enter a valid PostgreSQL connection URL.")
    hostname = parsed.hostname.lower()
    if hostname not in auth_store.allowed_database_hosts:
        try:
            addresses = await asyncio.to_thread(
                socket.getaddrinfo, hostname, parsed.port or 5432, type=socket.SOCK_STREAM
            )
        except socket.gaierror as error:
            raise HTTPException(status_code=400, detail="That database host could not be found.") from error
        resolved = {item[4][0] for item in addresses}
        if not resolved or any(not ipaddress.ip_address(address).is_global for address in resolved):
            raise HTTPException(
                status_code=403,
                detail="Private database hosts must be approved by Dystopian staff.",
            )
    database_name = parsed.path.lstrip("/") or "postgres"
    try:
        port = f":{parsed.port}" if parsed.port else ""
    except ValueError as error:
        raise HTTPException(status_code=400, detail="That PostgreSQL URL has an invalid port.") from error
    return f"{parsed.hostname}{port}/{database_name}"


@app.get("/api/auth/discord/start")
async def discord_login():
    require_local_mode()
    return auth_store.oauth_start()


@app.get("/api/auth/discord/callback")
async def discord_callback(request: Request, code: str, state: str):
    require_local_mode()
    return await auth_store.oauth_callback(request, code, state)


@app.get("/api/auth/me")
async def auth_me(request: Request):
    require_local_mode()
    user = auth_store.current_user(request)
    databases = auth_store.database_choices_for(user)
    runtime_connection = runtime_store.connection(user.discord_id) if runtime_store else None
    if runtime_connection:
        databases.append({"id": "sage-runtime", "label": runtime_connection.label})
    connected = bool(databases)
    label = databases[0]["label"] if databases else user.database_label
    return {
        "user": {
            "discord_id": user.discord_id,
            "username": user.username,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
        },
        "database": {"connected": connected, "label": label},
        "databases": databases,
    }


@app.post("/api/auth/logout")
async def logout(request: Request):
    require_local_mode()
    return auth_store.logout(request)


@app.post("/api/runtime/pair/start")
async def start_runtime_pairing(request: Request, payload: RuntimeStartRequest):
    require_local_mode()
    user = auth_store.current_user(request)
    if not runtime_store:
        raise HTTPException(status_code=503, detail="Runtime pairing is unavailable.")
    return await runtime_store.start(user.discord_id, payload.endpoint)


@app.get("/api/runtime/pair/status")
async def runtime_pairing_status(request: Request, id: str):
    require_local_mode()
    user = auth_store.current_user(request)
    if not runtime_store:
        raise HTTPException(status_code=503, detail="Runtime pairing is unavailable.")
    return runtime_store.status(user.discord_id, id)


@app.post("/api/runtime/pair")
async def claim_runtime_pairing(payload: RuntimeClaimRequest):
    require_local_mode()
    if payload.action != "claim" or not runtime_store:
        raise HTTPException(status_code=400, detail="That runtime pairing action is invalid.")
    return await runtime_store.claim(payload.code, payload.token)


@app.delete("/api/account/runtime")
async def disconnect_runtime(request: Request):
    require_local_mode()
    user = auth_store.current_user(request)
    if runtime_store:
        runtime_store.disconnect(user.discord_id)
    return {"success": True}


@app.put("/api/account/database")
async def save_database_connection(request: Request, payload: ConnectRequest):
    require_local_mode()
    require_self_service_databases()
    user = auth_store.current_user(request)
    db_url = payload.db_url.strip()
    label = await database_label(db_url)
    conn = await connect_database(db_url)
    try:
        rows = await conn.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
    finally:
        await conn.close()
    auth_store.save_database_url(user, db_url, label)
    return {"tables": [row["table_name"] for row in rows], "database": {"label": label}}


@app.delete("/api/account/database")
async def clear_database_connection(request: Request):
    require_local_mode()
    require_self_service_databases()
    user = auth_store.current_user(request)
    auth_store.clear_database_url(user)
    return {"success": True}


@app.post("/api/database/tables")
async def list_tables(request: Request, payload: DatabaseRequest):
    require_local_mode()
    runtime = current_runtime(request, payload.database_id)
    if runtime:
        return await runtime_store.proxy(runtime, "/v1/recallibrate/tables", "POST", {})
    conn = await connect_database(current_database_url(request, payload.database_id))
    try:
        rows = await conn.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        return {"tables": [row["table_name"] for row in rows]}
    finally:
        await conn.close()


@app.post("/api/database/columns")
async def list_columns(request: Request, payload: TableRequest):
    require_local_mode()
    runtime = current_runtime(request, payload.database_id)
    if runtime:
        return await runtime_store.proxy(runtime, "/v1/recallibrate/columns", "POST", request_payload(payload))
    conn = await connect_database(current_database_url(request, payload.database_id))
    try:
        columns = await table_schema(conn, payload.table_name)
        quoted_table = quote_identifier(payload.table_name)
        result = []

        for column in columns:
            name = column["column_name"]
            quoted_column = quote_identifier(name)
            distinct_count = await conn.fetchval(
                f"""
                SELECT COUNT(*) FROM (
                    SELECT DISTINCT {quoted_column}
                    FROM {quoted_table}
                    LIMIT {LOW_CARDINALITY_LIMIT + 1}
                ) AS recallibrate_values
                """
            )
            options = None
            if distinct_count <= LOW_CARDINALITY_LIMIT:
                option_rows = await conn.fetch(
                    f"""
                    SELECT DISTINCT {quoted_column}::text AS value
                    FROM {quoted_table}
                    ORDER BY value NULLS LAST
                    LIMIT {LOW_CARDINALITY_LIMIT}
                    """
                )
                options = [row["value"] for row in option_rows]

            result.append({
                "name": name,
                "type": column["data_type"],
                "database_type": column["udt_name"],
                "options": options,
            })

        return {"columns": result}
    finally:
        await conn.close()


@app.post("/api/database/search")
async def search_entries(request: Request, payload: SearchRequest):
    require_local_mode()
    runtime = current_runtime(request, payload.database_id)
    if runtime:
        return await runtime_store.proxy(runtime, "/v1/recallibrate/search", "POST", request_payload(payload))
    conn = await connect_database(current_database_url(request, payload.database_id))
    try:
        columns = await table_schema(conn, payload.table_name)
        column_types = {column["column_name"]: column["data_type"] for column in columns}
        text_columns = [name for name, data_type in column_types.items() if data_type in TEXT_TYPES]
        quoted_table = quote_identifier(payload.table_name)
        conditions: list[str] = []
        args: list[object] = []

        if payload.query:
            if not text_columns:
                raise HTTPException(status_code=400, detail="This table has no searchable text columns.")
            args.append(payload.query if payload.fuzzy else f"%{payload.query}%")
            placeholder = f"${len(args)}"
            if payload.fuzzy:
                search_parts = [
                    f"similarity(COALESCE({quote_identifier(column)}, ''), {placeholder}) > 0.2"
                    for column in text_columns
                ]
            else:
                search_parts = [
                    f"COALESCE({quote_identifier(column)}, '') ILIKE {placeholder}"
                    for column in text_columns
                ]
            conditions.append(f"({' OR '.join(search_parts)})")

        for column, values in (payload.filters or {}).items():
            if column not in column_types or not values:
                continue
            args.append(values)
            conditions.append(f"{quote_identifier(column)}::text = ANY(${len(args)}::text[])")

        if payload.date_from and "created_at" in column_types:
            args.append(payload.date_from)
            conditions.append(f"{quote_identifier('created_at')} >= ${len(args)}")

        if payload.date_to and "created_at" in column_types:
            args.append(payload.date_to)
            conditions.append(f"{quote_identifier('created_at')} <= ${len(args)}")

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = await conn.fetch(
            f"SELECT * FROM {quoted_table} {where_clause} LIMIT {MAX_RESULTS}",
            *args,
        )
        return {"results": [dict(row) for row in rows], "limit": MAX_RESULTS}
    finally:
        await conn.close()


@app.get("/api/portfolio/tables")
async def portfolio_tables():
    conn = await connect_database(portfolio_database_url())
    try:
        rows = await conn.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        return {"tables": [row["table_name"] for row in rows if row["table_name"] in PORTFOLIO_TABLES]}
    finally:
        await conn.close()


@app.get("/api/portfolio/tables/{table_name}/columns")
async def portfolio_columns(table_name: str):
    require_portfolio_table(table_name)
    conn = await connect_database(portfolio_database_url())
    try:
        columns = await table_schema(conn, table_name)
        quoted_table = quote_identifier(table_name)
        result = []
        for column in columns:
            name = column["column_name"]
            quoted_column = quote_identifier(name)
            distinct_count = await conn.fetchval(
                f"""
                SELECT COUNT(*) FROM (
                    SELECT DISTINCT {quoted_column} FROM {quoted_table}
                    LIMIT {LOW_CARDINALITY_LIMIT + 1}
                ) AS recallibrate_values
                """
            )
            options = None
            if distinct_count <= LOW_CARDINALITY_LIMIT:
                option_rows = await conn.fetch(
                    f"SELECT DISTINCT {quoted_column}::text AS value FROM {quoted_table} ORDER BY value NULLS LAST LIMIT {LOW_CARDINALITY_LIMIT}"
                )
                options = [row["value"] for row in option_rows]
            result.append({"name": name, "type": column["data_type"], "database_type": column["udt_name"], "options": options})
        return {"columns": result}
    finally:
        await conn.close()


@app.post("/api/portfolio/search")
async def portfolio_search(payload: PortfolioSearchRequest):
    require_portfolio_table(payload.table_name)
    conn = await connect_database(portfolio_database_url())
    try:
        columns = await table_schema(conn, payload.table_name)
        column_types = {column["column_name"]: column["data_type"] for column in columns}
        text_columns = [name for name, data_type in column_types.items() if data_type in TEXT_TYPES]
        conditions: list[str] = []
        args: list[object] = []

        if payload.query:
            args.append(payload.query if payload.fuzzy else f"%{payload.query}%")
            placeholder = f"${len(args)}"
            if payload.fuzzy:
                parts = [f"similarity(COALESCE({quote_identifier(column)}, ''), {placeholder}) > 0.2" for column in text_columns]
            else:
                parts = [f"COALESCE({quote_identifier(column)}, '') ILIKE {placeholder}" for column in text_columns]
            if parts:
                conditions.append(f"({' OR '.join(parts)})")

        for column, values in (payload.filters or {}).items():
            if column not in column_types or not values:
                continue
            args.append(values)
            conditions.append(f"{quote_identifier(column)}::text = ANY(${len(args)}::text[])")

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = await conn.fetch(
            f"SELECT * FROM {quote_identifier(payload.table_name)} {where_clause} ORDER BY id LIMIT {MAX_RESULTS}",
            *args,
        )
        return {"results": [dict(row) for row in rows], "read_only": True}
    finally:
        await conn.close()


@app.put("/api/database/record")
async def update_entry(request: Request, payload: UpdateEntryRequest):
    require_local_mode()
    runtime = current_runtime(request, payload.database_id)
    if runtime:
        return await runtime_store.proxy(runtime, "/v1/recallibrate/record", "PUT", request_payload(payload))
    conn = await connect_database(current_database_url(request, payload.database_id))
    try:
        columns = await table_schema(conn, payload.table_name)
        column_types = {column["column_name"]: column["data_type"] for column in columns}
        if "id" not in column_types:
            raise HTTPException(status_code=400, detail="Inline editing requires an id column.")
        if payload.column_name not in column_types:
            raise HTTPException(status_code=400, detail="That column does not exist.")
        selected_column = next(column for column in columns if column["column_name"] == payload.column_name)
        data_type = selected_column["data_type"]
        if data_type in TEXT_TYPES:
            value_expression = "$1"
        elif data_type in CAST_TYPES:
            value_expression = f"$1::{CAST_TYPES[data_type]}"
        elif data_type == "USER-DEFINED":
            value_expression = f"$1::{quote_identifier(selected_column['udt_name'])}"
        else:
            raise HTTPException(status_code=400, detail="That column type cannot be edited inline.")

        status = await conn.execute(
            f"""
            UPDATE {quote_identifier(payload.table_name)}
            SET {quote_identifier(payload.column_name)} = {value_expression}
            WHERE {quote_identifier('id')}::text = $2
            """,
            payload.new_text,
            payload.record_id,
        )
        if status == "UPDATE 0":
            raise HTTPException(status_code=404, detail="That record no longer exists.")
        return {"success": True}
    finally:
        await conn.close()


@app.delete("/api/database/record")
async def delete_entry(request: Request, payload: DeleteEntryRequest):
    require_local_mode()
    runtime = current_runtime(request, payload.database_id)
    if runtime:
        return await runtime_store.proxy(runtime, "/v1/recallibrate/record", "DELETE", request_payload(payload))
    conn = await connect_database(current_database_url(request, payload.database_id))
    try:
        columns = await table_schema(conn, payload.table_name)
        if "id" not in {column["column_name"] for column in columns}:
            raise HTTPException(status_code=400, detail="Deleting requires an id column.")
        status = await conn.execute(
            f"""
            DELETE FROM {quote_identifier(payload.table_name)}
            WHERE {quote_identifier('id')}::text = $1
            """,
            payload.record_id,
        )
        if status == "DELETE 0":
            raise HTTPException(status_code=404, detail="That record no longer exists.")
        return {"success": True}
    finally:
        await conn.close()


@app.get("/")
def read_root():
    if PORTFOLIO_ONLY:
        return RedirectResponse("/portfolio", status_code=302)
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/portfolio")
def read_portfolio():
    return FileResponse(FRONTEND_DIR / "portfolio.html")


app.mount("/portfolio-assets", StaticFiles(directory=FRONTEND_DIR), name="portfolio-assets")
app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="static")
