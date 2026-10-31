# ADR-002: ClickHouse for events and metrics, PostgreSQL for configuration

- Status: Accepted
- Date: 2026-10-31

## Context
Workload is append-only events (millions of PR/commit/check events) and cohort aggregations
over time. Configuration (installations, repos, rules) is small and relational.

## Decision
- ClickHouse: event tables (MergeTree) + materialized views for metrics.
- PostgreSQL: installations, repositories, attribution rules, settings (SQLAlchemy + Alembic).

## Consequences
- + Fast aggregations, strong compression, cheap long history.
- + Grafana has a native ClickHouse datasource.
- − Two databases to operate; acceptable — each fits its workload.
- Rejected: Postgres-only (aggregation cost at scale), TimescaleDB (less suited to wide event analytics).
