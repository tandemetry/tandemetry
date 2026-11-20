# ADR-004: ClickHouse schema migrations as versioned SQL files

- Status: Proposed
- Date: 2026-11-20

## Context
ClickHouse holds the event tables and metric views (ADR-002) and needs schema changes over time.
Its DDL is not transactional, `ALTER … UPDATE/DELETE` run as asynchronous mutations, and engines,
sorting keys and materialized views are poorly modelled by SQLAlchemy, so Alembic autogenerate
and downgrades give little real safety. Alembic remains the tool for PostgreSQL (ADR-002).
Schema changes must be repeatable in CI, local compose and Kubernetes without racing replicas.

## Decision
Keep ClickHouse migrations as numbered SQL files in `src/tandemetry/storage/clickhouse_migrations/`,
one idempotent statement per file (`IF NOT EXISTS`), applied in name order by `tandemetry migrate`
as a separate deploy step (later a Helm pre-install/pre-upgrade Job), never at service startup.
Migrations are forward-only: a mistake is fixed by the next file. Add a `schema_migrations`
tracking table in ClickHouse with the first migration that cannot be safely re-run (data copies,
table swaps).

## Consequences
- + No extra tool or binary; files ship in the wheel and are reviewed as plain SQL.
- + Re-running after a partial failure is safe because every statement is idempotent.
- − Until the tracking table exists every file runs on each `migrate`; acceptable while all
  statements are idempotent.
- − No downgrades; mitigated by forward fixes and ClickHouse backups.
- Rejected: Alembic with a ClickHouse dialect — raw SQL anyway, non-transactional downgrades.
- Rejected: golang-migrate / Atlas — another binary in the image for a handful of files.
