# CLAUDE.md — Tandemetry

Context for Claude Code. Read this first in every session.

## What this project is

Tandemetry is an open-source, self-hosted analytics service that shows how AI coding agents
(Claude Code, Codex, Copilot coding agent, Devin, Cursor, …) affect a company's codebase,
compared with human-authored work: share of PRs, merge rate, reverts, rework, CI failures,
review load and cost per merged PR.

- Product spec: `docs/product.md`
- Architecture: `docs/architecture.md`
- Agent attribution rules: `docs/attribution.md`
- Roadmap: `docs/roadmap.md`
- Decisions: `docs/adr/` — do not propose alternatives to accepted ADRs without saying so explicitly.

## Hard rules

1. **No LLM calls in the core.** All metrics and attribution are deterministic (rules + SQL).
   Optional LLM features live behind a flag and use the user's own key (ADR-003).
2. **No individual developer rankings.** Aggregate by team, repository and agent only.
3. **Customer code never leaves their infrastructure.** No telemetry home, no external calls
   except GitHub API and explicitly configured exporters.
4. **Every change ships with tests.** No merge with failing CI.
5. **Read-only GitHub permissions.** The GitHub App never writes to customer repos.

## Stack

- Python 3.13, uv, FastAPI, Pydantic v2
- PostgreSQL 17 + SQLAlchemy 2 (async) + Alembic — configuration state
- Kafka (KRaft) + aiokafka — event stream (ADR-001)
- ClickHouse — events and metric aggregations (ADR-002)
- Redis — optional, rate limiting / caching
- OpenTelemetry, Prometheus, Grafana — observability and dashboards
- Docker Compose (local), Kubernetes + Helm + KEDA (deploy)
- pytest, testcontainers, ruff, mypy (strict), pre-commit, gitleaks

## Repository layout (target)

```
src/tandemetry/
  api/            # FastAPI: webhooks, metrics API
  ingest/         # GitHub webhook handling, backfill worker
  events/         # unified event model (pydantic), Kafka producers/consumers
  attribution/    # rule engine: agent vs human
  storage/        # Postgres (SQLAlchemy) and ClickHouse clients, migrations
  metrics/        # metric definitions, ClickHouse SQL / materialized views
  cli.py          # `tandemetry` CLI
tests/            # unit + integration (testcontainers)
deploy/           # docker-compose, helm chart, grafana dashboards
docs/
```

## Commands

```bash
uv sync                       # install deps
uv run pytest                 # tests
uv run ruff check . && uv run ruff format --check .
uv run mypy src
docker compose -f deploy/docker-compose.yml up -d   # local stack
```

(Commands become valid as the skeleton lands in PR #2.)

## Conventions

- Branches: `feat/…`, `fix/…`, `docs/…`, `chore/…`. One issue → one PR. Squash merge.
- Commits: Conventional Commits (`feat: …`, `fix: …`, `docs: …`).
- Typing everywhere; mypy strict. Pydantic models for every event and API payload.
- Async I/O. No blocking calls in the event loop.
- Kafka consumers must be idempotent (events carry a stable `event_id`).
- New architectural decision → add an ADR in `docs/adr/`.

## Working agreement (human + agent)

- Start non-trivial tasks in plan mode: read the issue and relevant docs, propose a plan, wait for approval.
- The maintainer writes the core learning areas himself (Kafka consumers, attribution rules,
  ClickHouse SQL, KEDA/OTel config); the agent scaffolds, writes tests, reviews and documents.
- Keep PRs small (< ~400 changed lines where possible).
