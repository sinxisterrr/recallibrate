"""Recallibrate's local PostgreSQL API and static frontend."""

from datetime import date
import os
from pathlib import Path
from typing import Optional

import asyncpg
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
MAX_RESULTS = 500
LOW_CARDINALITY_LIMIT = 20
TEXT_TYPES = {"text", "character varying", "varchar", "character", "char"}
PORTFOLIO_TABLES = {"sam_lore", "projects", "opinions", "skills", "favorites"}

PORTFOLIO_ONLY = os.getenv("RECALLIBRATE_PORTFOLIO_ONLY", "").lower() in {"1", "true", "yes"}

app = FastAPI(
    title="Recallibrate",
    docs_url=None if PORTFOLIO_ONLY else "/api/docs",
    openapi_url=None if PORTFOLIO_ONLY else "/api/openapi.json",
    redoc_url=None,
)


class ConnectRequest(BaseModel):
    db_url: str


class TableRequest(ConnectRequest):
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
        SELECT column_name, data_type, ordinal_position
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        ORDER BY ordinal_position
        """,
        table_name,
    )
    if not columns:
        raise HTTPException(status_code=404, detail="That table does not exist in the public schema.")
    return columns


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


@app.post("/api/database/tables")
async def list_tables(payload: ConnectRequest):
    require_local_mode()
    conn = await asyncpg.connect(payload.db_url)
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
async def list_columns(payload: TableRequest):
    require_local_mode()
    conn = await asyncpg.connect(payload.db_url)
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
                "options": options,
            })

        return {"columns": result}
    finally:
        await conn.close()


@app.post("/api/database/search")
async def search_entries(payload: SearchRequest):
    require_local_mode()
    conn = await asyncpg.connect(payload.db_url)
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
    conn = await asyncpg.connect(portfolio_database_url())
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
    conn = await asyncpg.connect(portfolio_database_url())
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
            result.append({"name": name, "type": column["data_type"], "options": options})
        return {"columns": result}
    finally:
        await conn.close()


@app.post("/api/portfolio/search")
async def portfolio_search(payload: PortfolioSearchRequest):
    require_portfolio_table(payload.table_name)
    conn = await asyncpg.connect(portfolio_database_url())
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
async def update_entry(payload: UpdateEntryRequest):
    require_local_mode()
    conn = await asyncpg.connect(payload.db_url)
    try:
        columns = await table_schema(conn, payload.table_name)
        column_types = {column["column_name"]: column["data_type"] for column in columns}
        if "id" not in column_types:
            raise HTTPException(status_code=400, detail="Inline editing requires an id column.")
        if payload.column_name not in column_types:
            raise HTTPException(status_code=400, detail="That column does not exist.")
        if column_types[payload.column_name] not in TEXT_TYPES:
            raise HTTPException(status_code=400, detail="Only text columns can be edited inline.")

        status = await conn.execute(
            f"""
            UPDATE {quote_identifier(payload.table_name)}
            SET {quote_identifier(payload.column_name)} = $1
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
async def delete_entry(payload: DeleteEntryRequest):
    require_local_mode()
    conn = await asyncpg.connect(payload.db_url)
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
