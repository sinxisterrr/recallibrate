"""Server-owned Discord-to-database assignment configuration."""

from dataclasses import dataclass
import json
import os


@dataclass(frozen=True)
class AssignedDatabase:
    id: str
    label: str
    url: str


def database_assignments() -> dict[str, tuple[AssignedDatabase, ...]]:
    """Resolve safe assignment metadata to separately configured secret URLs."""
    raw = os.getenv("RECALLIBRATE_DATABASE_ASSIGNMENTS", "").strip()
    if not raw:
        return {}
    try:
        configured = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError("RECALLIBRATE_DATABASE_ASSIGNMENTS must be valid JSON.") from error
    if not isinstance(configured, dict):
        raise RuntimeError("RECALLIBRATE_DATABASE_ASSIGNMENTS must be a JSON object.")

    assignments: dict[str, tuple[AssignedDatabase, ...]] = {}
    for discord_id, settings in configured.items():
        if not isinstance(settings, dict):
            raise RuntimeError(f"Database assignment for {discord_id} must be an object.")
        entries = settings.get("databases")
        if entries is None:
            entries = [settings]
        if not isinstance(entries, list) or not entries:
            raise RuntimeError(f"Database assignment for {discord_id} needs at least one database.")
        resolved: list[AssignedDatabase] = []
        seen_ids: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise RuntimeError(f"Each database assignment for {discord_id} must be an object.")
            database_id = str(entry.get("id") or "").strip()
            label = str(entry.get("label") or "").strip()
            database_env = str(entry.get("database_env") or "").strip()
            if not database_id or not label or not database_env:
                raise RuntimeError(f"Database assignment for {discord_id} needs id, label, and database_env.")
            if database_id in seen_ids:
                raise RuntimeError(f"Database assignment for {discord_id} repeats id {database_id}.")
            database_url = os.getenv(database_env, "").strip()
            if not database_url:
                raise RuntimeError(f"Database assignment {discord_id} references unset {database_env}.")
            seen_ids.add(database_id)
            resolved.append(AssignedDatabase(id=database_id, label=label, url=database_url))
        assignments[str(discord_id)] = tuple(resolved)
    return assignments
