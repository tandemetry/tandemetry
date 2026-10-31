# Product

## One-liner

Open-source, self-hosted analytics for AI coding agents: see how agents vs humans ship code —
merge rate, reverts, rework, CI failures, review load, cost per PR.

## Problem

- AI agents now open a large and fast-growing share of pull requests (GitHub Octoverse 2026:
  40%+ of PRs started by agents in September 2026, up from 17% six months earlier).
- Teams pay for several agents but cannot answer: is agent code merged, reverted, rewritten?
  Which agent works best *in our codebase*? Is review load growing?
- Existing tools: paid engineering-intelligence platforms (LinearB, Swarmia, Jellyfish, DX, Faros)
  are expensive and built for human activity; GitHub's own metrics cover only Copilot;
  Apache DevLake is heavy and Copilot-only for AI; Faros Community Edition was removed.

## Users

- **Primary:** engineering managers, tech leads, CTOs of teams with 10–300 developers.
- **Operator:** platform/DevOps engineer who deploys it.

## Positioning

Free, self-hosted, agent-agnostic, outcome-focused (reverts/rework, not just activity),
no Jira dependency, no individual rankings, no LLM required.

## v0.1 metrics (per cohort: agent / human / mixed, and per agent)

| Metric | Definition |
| --- | --- |
| Agent PR share | agent PRs / all PRs per week |
| Merge rate | merged / closed PRs |
| Autonomy | PRs merged without human commits after open |
| Revert within 14 days | merged PRs whose commits were reverted within 14 days |
| Rework within 2 weeks | lines of a PR changed by another PR within 14 days |
| CI failure rate | PRs with ≥1 failed check run / all PRs |
| Review time | open → first review, open → merge |
| Cost per merged PR (optional) | agent tokens (OTel) / merged PRs |

## Non-goals (v0.1)

- Individual developer productivity scores.
- Non-GitHub platforms (GitLab, Azure DevOps, Bitbucket come later via adapters).
- Own UI (Grafana first).
- LLM features.

## Business model (later)

Open-core: OSS self-hosted core (Apache-2.0) → hosted SaaS → enterprise features (SSO, RBAC,
long retention, support). Annual public report "Agent Code Census" as top-of-funnel.
