# *Recall*ibrate

A private PostgreSQL database workbench for bringing machine memory back into focus.

Sign in with an invited Discord account, open the database assigned to that account, move through its tables, search exact or fuzzy text matches, filter low-cardinality columns, and edit records inline.

Each verified Discord account is mapped server-side to its own database URL. The browser receives only a random HTTP-only session cookie; database hostnames, roles, and passwords remain server-side. The PostgreSQL role inside each assigned connection determines what that person can read, edit, or delete.

The name is deliberate: **recall** + calibrate.

## Authenticated workbench

1. Create a Discord application in the Developer Portal.
2. Add an OAuth2 redirect URI ending in `/api/auth/discord/callback`.
3. Copy `.env.example` to `.env` and configure the Discord client ID, client secret, redirect URI, invited Discord IDs, and a Fernet credential key.
4. Set `RECALLIBRATE_DATABASE_ASSIGNMENTS` to a JSON mapping of Discord IDs to labels and secret environment-variable names.
5. Configure each referenced secret variable with that owner's private PostgreSQL URL.
6. Set `RECALLIBRATE_ALLOWED_DB_HOSTS` to the exact private database hostnames Recallibrate may contact. Connections are refused when this allowlist is empty.
7. Persist `RECALLIBRATE_STATE_PATH` with a private container volume. This SQLite control store contains user records and session hashes.

Recallibrate requests only Discord's `identify` scope. By default, `RECALLIBRATE_ALLOWED_DISCORD_IDS` limits access to named accounts. Set `RECALLIBRATE_ALLOW_ANY_DISCORD_USER=true` to admit any successfully authenticated Discord account. Sessions last 14 days and can be revoked by signing out.

For local HTTP development, use `RECALLIBRATE_SECURE_COOKIES=false`. Keep it `true` behind production HTTPS.

The generic database API is authenticated and never accepts a database URL on table, search, edit, or delete requests. With `RECALLIBRATE_ALLOW_SELF_SERVICE_DATABASES=true`, users without an assigned database can save an encrypted PostgreSQL URL through the connection screen. Assigned databases remain server-owned. Unapproved private or local network hosts are blocked; trusted private hosts must be listed in `RECALLIBRATE_ALLOWED_DB_HOSTS`.

Users with a Sage deployment can instead enter its public HTTPS runtime URL. Recallibrate generates a short-lived code; the owner runs `/connect-recallibrate code:...` through that Sage bot. Sage then issues a dedicated, revocable Recallibrate token and keeps its PostgreSQL credentials inside the runtime boundary. The token cannot access Studio, conversation, model, or general memory-management APIs.

Example assignment:

```env
RECALLIBRATE_DATABASE_ASSIGNMENTS={"123456789012345678":{"id":"ash","label":"Ash Memory","database_env":"ASH_DATABASE_URL"}}
ASH_DATABASE_URL=postgresql://dystopian_owner:secret@ash-database:5432/postgres
```

An owner with multiple AIs gets a database picker:

```env
RECALLIBRATE_DATABASE_ASSIGNMENTS={"222864273762680842":{"databases":[{"id":"aeron","label":"Aeron Memory","database_env":"AERON_DATABASE_URL"},{"id":"kai","label":"Kai Memory","database_env":"KAI_DATABASE_URL"}]}}
```

## Portfolio demo

[`recallibrate.app/portfolio`](https://recallibrate.app/portfolio) is a public, electric-purple demonstration backed by an isolated PostgreSQL database containing Sam's projects, skills, opinions, favorites, and tiny lore.

The hosted portfolio connects with a database role that has `SELECT` permission only. Pencil edits are intentionally simulated in the current browser tab and never write to the canonical database. The authenticated workbench and generic database API remain disabled in portfolio-only deployments.
