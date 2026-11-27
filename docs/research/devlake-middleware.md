# Apache DevLake and Middleware: gaps for agent analytics

Checked on 2026-11-27 from documentation, release notes and source code (read-only: `gh api` and
shallow clones; neither tool was installed or run). The kill/continue criterion is dated
2026-11-07; this check closes it 20 days later and reflects the tools as of 2026-11-27.

| Tool | Repository | Version checked |
| --- | --- | --- |
| Apache DevLake | [`apache/devlake`][dl-repo] (renamed from `apache/incubator-devlake`) | `main` at [`6282a42`][dl-sha] (2026-11-27); latest release `v1.0.2` (2025-07-02), pre-release `v1.0.3-beta19` (2026-11-02) |
| Middleware | [`middlewarehq/middleware`][mw-repo] | `main` at [`844eb42`][mw-sha] (2026-08-03, last commit); latest release `0.3.1` (2025-05-30) |

## Method

1. Listed each repository tree and read the plugin, model and task files linked below.
2. Searched the code (`*.go`, `*.py`, `*.sql`, dashboard JSON; tests and fixtures excluded) for
   `copilot-swe-agent`, `copilot-swe`, `devin`, `codex`, `openai`, `jules`, `cursoragent`,
   `noreply@anthropic.com`, `co-authored-by`, `[bot]`, `is_bot`, `revert`, `rework`, `copilot`,
   `claude`, `cursor`. A term not found means
   "not found by this search", not "impossible to configure".
3. Read the setup and metrics documentation of both projects.

## Comparison

| | DevLake | Middleware | Tandemetry |
| --- | --- | --- | --- |
| GitHub data | PRs, PR commits, reviews, review comments, commits, issues, Actions runs and jobs, deployments [^dl-gh] | PRs, PR commits, reviews, timeline events, Actions workflow runs [^mw-gh] | PRs, commits, reviews, check runs (any CI), merges [^tm-gh] |
| Collection | Scheduled API polling with incremental state; the incoming webhook accepts only deployments, incidents and PRs pushed by your own scripts [^dl-wh] | Cron sync every 30 minutes [^mw-cron] | GitHub App webhooks plus resumable backfill [^tm-gh] |
| AI support | Four vendor-telemetry plugins: GitHub Copilot, Cursor, Claude Code, Kiro (adoption, usage, cost, acceptance) [^dl-ai] | LLM summary of DORA metrics with the user's OpenAI or Fireworks key [^mw-ai]; no AI-tool data | Agent attribution of PRs and commits from repository signals [^tm-attr] (planned, week 5) |
| Agent vs human per PR | Cursor Enterprise only: per-commit AI line counts from Cursor's API, joined to PRs in one dashboard [^dl-cursor]; no rules for other agents | No | Core feature: bot author, trailer, branch and description signals for 7 agents [^tm-sig] (planned) |
| Agent-vs-human cohorts | Team-level adoption tiers correlated with DORA and PR cycle time (Copilot) [^dl-corr] | No | Every metric per cohort and per agent [^tm-prod] (planned) |
| Revert metric | Not found | Revert PRs matched by branch `revert-<n>-…`, used as incidents for change failure rate [^mw-rev] | Revert within 14 days, per cohort [^tm-prod] (planned) |
| Rework metric | Not found | "Rework time" and "rework cycles": first blocking review to approval inside one PR [^mw-rew] | Files of a merged PR changed again within 14 days [^tm-prod] (planned) |
| CI failure metric | Build success rate on Actions and other CI plugins [^dl-metrics] | None found; workflow runs are used only as deployments [^mw-deploys] | PRs with a failed check run [^tm-prod] (planned) |
| Review time | PR pickup, review, cycle time; bot reviews excluded from first review [^dl-bot] | First response, rework, merge time; bot events excluded by name regex [^mw-bot] | Open to first review, open to merge [^tm-prod] (planned) |
| Footprint | 4 services: MySQL 8, backend, config UI, Grafana; Helm chart [^dl-deploy] | 1 container bundling PostgreSQL, Redis, API, sync server, web app [^mw-deploy] | Kafka, ClickHouse, PostgreSQL, app services; Helm planned [^tm-arch] |
| License | Apache-2.0 [^dl-repo] | Apache-2.0 [^mw-repo] | Apache-2.0 |

## DevLake

DevLake has moved fast on AI since the product note was written: four plugins (`gh-copilot`,
`cursor`, `claude_code`, `kiro`) and 21 AI dashboards, including a
"Multi-AI Tool Comparison" [^dl-ai] [^dl-dash]. All four read the **vendor's admin or usage API**:

- **Copilot:** org and enterprise usage metrics, seats, AI credits [^dl-copilot].
- **Claude Code:** per-user daily counts from the Claude analytics API, including commits, PRs
  and lines produced by Claude Code [^dl-claude].
- **Cursor:** usage, spend and, with an Enterprise key, per-commit AI line attribution [^dl-cursor].
- **Kiro:** usage reports and logs from S3.

This is *usage telemetry*: who used the tool, how much, at what cost. It is not attribution of
the repository's own history:

- Data stays in tool-layer tables (`_tool_cursor_*`, `_tool_claude_code_*`); the README says
  there is no domain-layer converter [^dl-cursor]. Only the Cursor Enterprise dashboard joins
  vendor data to `pull_requests` through commit hashes.
- Agents without such an API are invisible: the search found no rules for Copilot coding agent
  (`copilot-swe-agent`), Devin, Codex, Jules, Cursor's agent or `Co-Authored-By` trailers. GitHub accounts get a
  generic `is_bot` flag (`Type == "Bot"` or `[bot]` suffix), used only to drop bot reviews from
  lead time [^dl-bot].
- The correlation dashboards compare weeks of high and low Copilot adoption with DORA metrics
  [^dl-corr]; they do not split PRs into agent and human cohorts.
- Several dashboards break AI use down by person ("Top Contributors by AI-Assisted Lines" in
  `cursor-enterprise.json`, `github-copilot-adoption-by-team-and-user.json`,
  `ClaudeCodeAdoptionByUser.json`) [^dl-dash], which Tandemetry rules out ([CLAUDE.md](../../CLAUDE.md), rule 2).
- Each vendor plugin needs an admin key and, for Cursor attribution, an Enterprise plan.

## Middleware

Middleware is a DORA tool: deployment frequency, lead time with a breakdown (first response,
rework, merge, deploy), change failure rate and MTTR [^mw-readme]. It has no AI-tool data and
no notion of agents; its only AI feature is an LLM summary of the DORA numbers [^mw-ai]. Two
details are useful:

- **Revert detection** by GitHub's default revert branch name `revert-<n>-<branch>` [^mw-rev].
  It misses reverts made from other branches or by direct commit.
- **Bot filtering** by a login regex before computing PR timings [^mw-bot].

Activity has slowed: no release since 2025-05-30 and no commit since 2026-08-03.

## Gaps

What neither tool covers for agent analytics:

1. **Mapping a PR to a specific agent from the repository.** Both tools can tell a bot account
   from a person, but neither was found to map a PR or commit to a named agent by bot login,
   `Co-Authored-By` trailer or branch prefix. Copilot coding agent, Devin, Codex and Jules PRs
   count as generic bots or humans; Claude Code appears only as per-user usage counts, not on
   PRs. Our signatures catalog covers seven agents with no vendor key [^tm-sig].
2. **Outcomes per cohort.** No merge rate, revert rate, rework or CI failure rate split by
   agent vs human or by agent. DevLake correlates adoption with team metrics; Middleware has no
   cohorts.
3. **Post-merge rework.** No metric for code changed again after merge was found in either. Middleware's "rework"
   is review iterations inside a PR.
4. **Revert per PR in time.** No revert metric was found in DevLake's code or metrics docs; Middleware links revert PRs but uses
   them only as incidents.
5. **Aggregate-only views.** DevLake's AI dashboards go down to individual users [^dl-dash].

### Reuse instead of rebuilding

Recommendations, not commitments:

- **Middleware's revert branch rule** as one input of our revert detection, next to the
  `This reverts commit <sha>` message line.
- **DevLake's metric definitions** (PR pickup, review, cycle time [^dl-metrics]) as the naming
  reference for review-time metrics, so users comparing both tools see the same terms.
- **Vendor usage data as an optional source for cost per merged PR.** DevLake already collects
  Cursor spend and Kiro credits; a later exporter or adapter could read it instead of us writing
  vendor clients. Out of scope for v0.1.

## Conclusion for the 2026-11-07 criterion

**Continue, with sharper positioning.** The criterion holds in a refined form. DevLake does
track AI usage for four tools through their vendor APIs, and line-level for Cursor Enterprise,
so "no AI support" would be wrong. But neither tool attributes PRs to agents from repository
signals or reports outcomes (merge, revert, rework, CI failures) per agent. That gap is
Tandemetry's core.

So Tandemetry should be positioned as **"outcomes of agent work, read from the repository, for
any agent, without vendor admin keys"**, not as the only AI analytics in open source. With the
signatures research ([`signatures.md`](signatures.md)), both halves of the refined criterion hold.

## Limitations

- Code and docs, not running instances: dashboards may compute more than the SQL read here, and
  configuration (DevLake's customize plugin, regex scope configs) could add rules per installation.
- Code search covers each `main` at the pinned commit; DevLake changes weekly, so recheck before
  quoting this publicly.
- Middleware's hosted product may differ from the open-source repository.

[dl-repo]: https://github.com/apache/devlake
[dl-sha]: https://github.com/apache/devlake/tree/6282a4229b045c53584e19c2ab3489c778f0bcfa
[mw-repo]: https://github.com/middlewarehq/middleware
[mw-sha]: https://github.com/middlewarehq/middleware/tree/844eb425ff95fcd408e408d78f21b8df860503fc

[^dl-repo]: [apache/devlake `LICENSE`](https://github.com/apache/devlake/blob/6282a4229b045c53584e19c2ab3489c778f0bcfa/LICENSE), checked 2026-11-27.
[^dl-gh]: [`backend/plugins/github/tasks/`](https://github.com/apache/devlake/tree/6282a4229b045c53584e19c2ab3489c778f0bcfa/backend/plugins/github/tasks): `pr_collector`, `pr_commit_collector`, `pr_review_collector`, `pr_review_comment_collector`, `commit_collector`, `cicd_run_collector`, `cicd_job_collector`.
[^dl-wh]: [Webhook plugin docs](https://devlake.apache.org/docs/Plugins/webhook) (checked 2026-11-27) and [`backend/plugins/webhook/api/`](https://github.com/apache/devlake/tree/6282a4229b045c53584e19c2ab3489c778f0bcfa/backend/plugins/webhook/api) (`deployments.go`, `issues.go`, `pull_requests.go`).
[^dl-ai]: [`backend/plugins/`](https://github.com/apache/devlake/tree/6282a4229b045c53584e19c2ab3489c778f0bcfa/backend/plugins) (`gh-copilot`, `cursor`, `claude_code`, `kiro`) and [`grafana/dashboards/mysql/multi-ai-comparison.json`](https://github.com/apache/devlake/blob/6282a4229b045c53584e19c2ab3489c778f0bcfa/grafana/dashboards/mysql/multi-ai-comparison.json).
[^dl-copilot]: [`backend/plugins/gh-copilot/README.md`](https://github.com/apache/devlake/blob/6282a4229b045c53584e19c2ab3489c778f0bcfa/backend/plugins/gh-copilot/README.md).
[^dl-claude]: [`backend/plugins/claude_code/models/user_activity.go`](https://github.com/apache/devlake/blob/6282a4229b045c53584e19c2ab3489c778f0bcfa/backend/plugins/claude_code/models/user_activity.go) (`/v1/organizations/analytics/users`).
[^dl-cursor]: [`backend/plugins/cursor/README.md`](https://github.com/apache/devlake/blob/6282a4229b045c53584e19c2ab3489c778f0bcfa/backend/plugins/cursor/README.md), [`models/ai_code_commit.go`](https://github.com/apache/devlake/blob/6282a4229b045c53584e19c2ab3489c778f0bcfa/backend/plugins/cursor/models/ai_code_commit.go), panel "PR AI Lines & Cost" in [`grafana/dashboards/mysql/cursor-enterprise.json`](https://github.com/apache/devlake/blob/6282a4229b045c53584e19c2ab3489c778f0bcfa/grafana/dashboards/mysql/cursor-enterprise.json).
[^dl-corr]: [`grafana/dashboards/mysql/github-copilot-dora-correlation.json`](https://github.com/apache/devlake/blob/6282a4229b045c53584e19c2ab3489c778f0bcfa/grafana/dashboards/mysql/github-copilot-dora-correlation.json).
[^dl-bot]: [`backend/plugins/github/tasks/account_convertor.go`](https://github.com/apache/devlake/blob/6282a4229b045c53584e19c2ab3489c778f0bcfa/backend/plugins/github/tasks/account_convertor.go) and [`backend/plugins/dora/tasks/change_lead_time_calculator.go`](https://github.com/apache/devlake/blob/6282a4229b045c53584e19c2ab3489c778f0bcfa/backend/plugins/dora/tasks/change_lead_time_calculator.go).
[^dl-metrics]: [DevLake metrics docs](https://devlake.apache.org/docs/Metrics/PRCycleTime) and the [metrics docs source](https://github.com/apache/devlake-website/tree/main/docs/Metrics): no revert or rework page, checked 2026-11-27.
[^dl-deploy]: [`docker-compose.yml` of release v1.0.2](https://github.com/apache/devlake/releases/tag/v1.0.2) (`mysql`, `devlake`, `config-ui`, `grafana`), [Docker Compose setup](https://devlake.apache.org/docs/GettingStarted/DockerComposeSetup), [Helm setup](https://devlake.apache.org/docs/GettingStarted/HelmSetup), chart in [`apache/devlake-helm-chart`](https://github.com/apache/devlake-helm-chart); docs and chart checked 2026-11-27.
[^dl-dash]: [`grafana/dashboards/mysql/`](https://github.com/apache/devlake/tree/6282a4229b045c53584e19c2ab3489c778f0bcfa/grafana/dashboards/mysql) (19 AI dashboards: `ai-*`, `cursor-*`, `github-copilot-*`, `kiro*`, `language-ai-heatmap`, `multi-ai-comparison`) plus 2 in `grafana/dashboards/ClaudeCode*.json`.
[^mw-repo]: [middlewarehq/middleware `LICENSE`](https://github.com/middlewarehq/middleware/blob/844eb425ff95fcd408e408d78f21b8df860503fc/LICENSE), checked 2026-11-27.
[^mw-readme]: [`README.md`](https://github.com/middlewarehq/middleware/blob/844eb425ff95fcd408e408d78f21b8df860503fc/README.md).
[^mw-gh]: [`backend/analytics_server/mhq/exapi/github.py`](https://github.com/middlewarehq/middleware/blob/844eb425ff95fcd408e408d78f21b8df860503fc/backend/analytics_server/mhq/exapi/github.py).
[^mw-deploys]: [`mhq/service/deployments/workflow_deployments_service.py`](https://github.com/middlewarehq/middleware/blob/844eb425ff95fcd408e408d78f21b8df860503fc/backend/analytics_server/mhq/service/deployments/workflow_deployments_service.py).
[^mw-cron]: [`setup_utils/cronjob.txt`](https://github.com/middlewarehq/middleware/blob/844eb425ff95fcd408e408d78f21b8df860503fc/setup_utils/cronjob.txt).
[^mw-ai]: [`backend/analytics_server/mhq/service/ai/ai_analytics_service.py`](https://github.com/middlewarehq/middleware/blob/844eb425ff95fcd408e408d78f21b8df860503fc/backend/analytics_server/mhq/service/ai/ai_analytics_service.py), used by `mhq/api/ai/dora_ai.py`.
[^mw-rev]: [`mhq/service/code/sync/revert_prs_github_sync.py`](https://github.com/middlewarehq/middleware/blob/844eb425ff95fcd408e408d78f21b8df860503fc/backend/analytics_server/mhq/service/code/sync/revert_prs_github_sync.py) and `mhq/exapi/git_incidents.py`.
[^mw-rew]: [`mhq/service/code/sync/etl_code_analytics.py`](https://github.com/middlewarehq/middleware/blob/844eb425ff95fcd408e408d78f21b8df860503fc/backend/analytics_server/mhq/service/code/sync/etl_code_analytics.py) (`get_rework_cycles`) and `mhq/service/code/models/lead_time.py` (`rework_time`).
[^mw-bot]: [`mhq/utils/string.py`](https://github.com/middlewarehq/middleware/blob/844eb425ff95fcd408e408d78f21b8df860503fc/backend/analytics_server/mhq/utils/string.py) (`is_bot_name`), applied in `etl_code_analytics.py`.
[^mw-deploy]: [`Dockerfile`](https://github.com/middlewarehq/middleware/blob/844eb425ff95fcd408e408d78f21b8df860503fc/Dockerfile) (`POSTGRES_DB_ENABLED`, `REDIS_ENABLED`) and the `docker run` quick start in the README.
[^tm-gh]: [docs/github-app.md](../github-app.md) and [docs/architecture.md](../architecture.md#github-ingestion).
[^tm-attr]: [docs/attribution.md](../attribution.md).
[^tm-sig]: [docs/research/signatures.md](signatures.md) and `src/tandemetry/attribution/signatures.yaml`.
[^tm-prod]: [docs/product.md](../product.md#v01-metrics-per-cohort-agent--human--mixed-and-per-agent).
[^tm-arch]: [docs/architecture.md](../architecture.md#deployment), [ADR-001](../adr/001-kafka-over-rabbitmq.md), [ADR-002](../adr/002-clickhouse-for-events.md).
