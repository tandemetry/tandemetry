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
- Decisions: `docs/adr/` — accepted ADRs define scope (see rule 6).
- Development process: `docs/process.md` — follow it for every task.

## Hard rules

1. **No LLM calls in the core.** All metrics and attribution are deterministic (rules + SQL).
   Optional LLM features live behind a flag and use the user's own key (ADR-003).
2. **No individual developer rankings.** Aggregate by team, repository and agent only.
3. **Customer code never leaves their infrastructure.** No telemetry home, no external calls
   except GitHub API and explicitly configured exporters.
4. **Every change ships with tests.** No merge with failing CI.
5. **Read-only GitHub permissions.** The GitHub App never writes to customer repos.
6. **Accepted ADRs define scope.** Kafka, ClickHouse, PostgreSQL, Kubernetes, KEDA and
   OpenTelemetry are deliberate choices. Minimalism (ponytail) applies inside them, never
   against them. To challenge one, propose a new ADR (`/new-adr`).
7. **Agents never merge, force-push or commit to `main`.** The maintainer merges.

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

## How we work (details in `docs/process.md`)

1. **Plan:** non-trivial task → `planner` agent turns the issue into a plan → maintainer approves.
2. **Implement:** `ponytail` mode (smallest complete change) + tests for non-trivial logic.
3. **Review:** `reviewer` agent (uses `ponytail-review`) before every PR → fix Must/Should findings.
4. **PR → CI → maintainer squash-merges.**
5. **Milestone end:** `ponytail-audit` → save to `docs/audits/YYYY-MM-DD.md`.

- Agents write the code. When a change touches technology new to the maintainer
  (Kafka, ClickHouse, Kubernetes/Helm, KEDA, OpenTelemetry, Prometheus/Grafana), add an
  **Explain** section to the reply: what was configured, why, how it works, how to verify it
  locally (exact commands), and common pitfalls.
- List **Maintainer actions** explicitly: anything the agent cannot or must not do (UI settings
  on GitHub, accounts/tokens, installing local tools, approving a ruleset change).
- Keep PRs small (< ~400 changed lines where possible).
- Keep the `Co-Authored-By` trailer on agent-assisted commits (we dogfood attribution).

## Claude Code setup

| Tool | Use |
| --- | --- |
| `planner` agent | plan an issue (read-only) |
| `reviewer` agent | independent pre-PR review (read-only) |
| `/ponytail [lite\|full\|ultra]` | coding mode (default: full) |
| `/ponytail-review` | review a change |
| `/ponytail-audit` | audit the repo |
| `/new-adr <title>` | record an architectural decision |

Permissions: `.claude/settings.json`. Personal overrides: `.claude/settings.local.json`.
