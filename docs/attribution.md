# Agent attribution

Goal: label every PR and commit as `agent`, `human` or `mixed`, plus the agent name, using
transparent deterministic rules. Each label stores the rule that matched and a confidence level,
so every number in a dashboard is explainable.

## Rules (evaluated in priority order, first match wins)

| # | Signal | Example | Confidence |
| --- | --- | --- | --- |
| 1 | PR author is a known agent bot account | Copilot coding agent, Devin bot | high |
| 2 | Commit git trailer | `Co-Authored-By: Claude <noreply@anthropic.com>` | high |
| 3 | Signature in PR description | "Generated with Claude Code" | medium |
| 4 | Branch name / label | `codex/…`, `ai-generated` | medium |
| 5 | Custom rules (YAML, per installation) | company conventions | configurable |
| 6 | Otherwise | — | `human` |

A PR with both agent-attributed and human commits is `mixed`.

## Signatures catalog

Known signatures live in `src/tandemetry/attribution/signatures.yaml` (open for community
contributions). The initial catalog was built from agent PRs in 22 popular public repos; method
and findings are in [research/signatures.md](research/signatures.md).

Each agent lists `signals` of a `kind` (`bot_account`, `commit_trailer`, `description_phrase`,
`branch_prefix`, `label`), a `value` and a `confidence`. The confidence is fixed per kind by the
rules table above (bot account and trailer: high; the rest: medium) and the loader rejects
entries that disagree; `src/tandemetry/attribution/catalog.py` is the source of truth.
Trailers are matched by their stable email, not the display name. To contribute, add a signal
you observed in real PRs and include example PR URLs in the pull request.

## Known limitations

- IDE agents that leave no trace are counted as `human` → report an honest "unknown/human" cohort.
- Recommend teams adopt git trailers for agent commits to improve accuracy.
