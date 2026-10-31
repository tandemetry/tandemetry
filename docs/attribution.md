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
contributions). Week 1 task: build the initial catalog from agent PRs in ~20 popular public repos.

## Known limitations

- IDE agents that leave no trace are counted as `human` → report an honest "unknown/human" cohort.
- Recommend teams adopt git trailers for agent commits to improve accuracy.
