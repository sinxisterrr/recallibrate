from fastapi import FastAPI
import asyncpg
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from datetime import date
from typing import Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"]
)

class SearchRequest(BaseModel):
    db_url: str
    query: str
    table_name: Optional[str] = None
    filters: Optional[dict[str, list[str]]] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    fuzzy: bool = False

class UpdateMemoryRequest(BaseModel):
    db_url: str
    table_name: str
    record_id: str
    new_text: str

class DeleteMemoryRequest(BaseModel):
    db_url: str
    table_name: str
    memory_id: str

@app.post("/api/database/search")
async def search_memories(payload: SearchRequest):
    conn = await asyncpg.connect(payload.db_url)

    valid_tables = await conn.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    )
    valid_table_names = [row["table_name"] for row in valid_tables]

    if payload.table_name not in valid_table_names:
        await conn.close()
        return {"error": "invalid table name"}

@app.get("/")
def read_root():
    return {"message": "something"}