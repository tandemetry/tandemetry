# Roadmap

## Week 1 (Nov 1–7): validation & skeleton
- [x] Collect agent PRs from 22 popular repos via GitHub API; signatures catalog (#9)
- [x] Project skeleton: uv, ruff, mypy, pytest, pre-commit (gitleaks), CI (#6)
- [x] Docker compose: Kafka (KRaft), ClickHouse, PostgreSQL (#12)
- [x] README with product promise and dashboard mockup
- [x] Publish `tandemetry` 0.0.1 to PyPI (minimal working CLI) (#15)

## Week 2 (Nov 8–14): ingestion
- [x] Unified event model (#18)
- Open items moved to weeks 3–4.

## Week 3 (Nov 15–21): event pipeline
- [ ] Kafka producer; ClickHouse consumer (#20: #21 ClickHouse store, #22 publisher, #23 consumer)

## Week 4 (Nov 22–28): ingestion
- [ ] GitHub App manifest (read-only) + webhook receiver with signature verification
- [ ] Backfill via GitHub API with rate-limit handling
- [ ] Dockerfile and application services in `deploy/docker-compose.yml` (profile `app`)
- [ ] Apache DevLake and Middleware: document gaps for agent analytics from their docs
  (closes the Nov 7 kill/continue criterion)

## Week 5 (Nov 29–Dec 5): core
- [ ] Attribution engine with YAML rules + tests on real PRs
- [ ] 8 v0.1 metrics as ClickHouse materialized views
- [ ] Revert and rework detection
- [ ] Metrics API

## Week 6 (Dec 6–12): showcase & infra
- [ ] Grafana dashboards: agents vs humans, agent comparison
- [ ] OpenTelemetry in the service, Prometheus metrics
- [ ] Helm chart, k3d, KEDA on consumer lag
- [ ] Weekly Slack report

## Dec 13–31: launch
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
