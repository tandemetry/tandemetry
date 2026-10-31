# Roadmap

## Week 1 (Nov 1–7): validation & skeleton
- [ ] Run Apache DevLake and Middleware; document gaps for agent analytics
- [ ] Collect agent PRs from ~20 popular repos via GitHub API; draft signatures catalog
- [ ] Project skeleton: uv, ruff, mypy, pytest, pre-commit (gitleaks), CI, docker compose
- [ ] README with product promise and dashboard mockup
- [ ] Publish `tandemetry` 0.0.1 to PyPI (minimal working CLI)

## Week 2 (Nov 8–14): ingestion
- [ ] GitHub App manifest (read-only) + webhook receiver with signature verification
- [ ] Unified event model
- [ ] Kafka producers; ClickHouse consumer
- [ ] Backfill via GitHub API with rate-limit handling

## Week 3 (Nov 15–21): core
- [ ] Attribution engine with YAML rules + tests on real PRs
- [ ] 8 v0.1 metrics as ClickHouse materialized views
- [ ] Revert and rework detection
- [ ] Metrics API

## Week 4 (Nov 22–30): showcase & infra
- [ ] Grafana dashboards: agents vs humans, agent comparison
- [ ] OpenTelemetry in the service, Prometheus metrics
- [ ] Helm chart, k3d, KEDA on consumer lag
- [ ] Weekly Slack report

## December: launch
- [ ] Public report "Agent Code Census" on OSS repos
- [ ] Public demo; Show HN, Reddit, LinkedIn; architecture blog post
- [ ] First 5 teams installing it

## After January 2027 (only with traction)
GitLab → Azure DevOps → Bitbucket adapters; own UI; optional LLM features (BYOK); hosted version.

## Kill / continue criteria
| Date | Continue if | Otherwise |
| --- | --- | --- |
| Nov 7 | DevLake/Middleware lack agent attribution; signatures found in real PRs | refocus or fallback idea |
| Dec 31 | report published, measurable reaction | rethink positioning |
| Jan 31, 2027 | 5+ teams installed or 3+ issues from strangers | finish as portfolio case |
