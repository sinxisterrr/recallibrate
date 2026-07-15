# *Recall*ibrate

A local-first PostgreSQL database workbench for bringing machine memory back into focus.

Connect with a database URL, move through its tables, search exact or fuzzy text matches, filter low-cardinality columns, and edit text records inline. Recallibrate keeps the connection URL in the active local session only; it is never persisted by the interface.

The name is deliberate: **recall** + calibrate.

## Portfolio demo

[`recallibrate.app/portfolio`](https://recallibrate.app/portfolio) is a public, electric-purple demonstration backed by an isolated PostgreSQL database containing Sam's projects, skills, opinions, favorites, and tiny lore.

The hosted application connects with a database role that has `SELECT` permission only. Pencil edits are intentionally simulated in the current browser tab and never write to the canonical database. The generic database-URL API is disabled in portfolio-only deployments.
