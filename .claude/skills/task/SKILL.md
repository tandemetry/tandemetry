---
name: task
description: >
  Run one task end-to-end through the Tandemetry process: issue → planner →
  maintainer approval → branch → implement (ponytail + tests) → reviewer →
  commit → PR. Use when the user writes /task <what to do> or /task #<issue>.
  Stops for the maintainer's approval after the plan and before any commit,
  push or PR.
argument-hint: "<what to do> | #<issue number>"
disable-model-invocation: true
---

# /task — one task, full process

Input: `$ARGUMENTS` — either a free-text task or an issue number (`#12` / `12`).
Follow `docs/process.md`. Do the steps in order. Never skip a STOP.

## 1. Issue

- If the input is an issue number: `gh issue view <n>` and use it.
- Otherwise draft an issue: Conventional-Commit-style title, short context,
  **Acceptance criteria** as a checklist. Show the draft and create it with
  `gh issue create` (the maintainer confirms the command). Use its number from now on.
- Trivial changes (typo, one-line docs fix): say so and offer to skip the issue and plan.

## 2. Plan

- Delegate to the **planner** agent: "Plan issue #<n>".
- Show the plan exactly as returned, including **Maintainer actions**.
- If the size is **L**, propose a split into smaller issues instead of continuing.

**STOP.** Ask: "Approve the plan? (yes / changes)". Do nothing else until the
maintainer approves. Apply requested changes and ask again.
After approval, offer to post the plan as an issue comment (`gh issue comment`).

## 3. Branch

`git switch -c <type>/<short-kebab-name>` from an up-to-date `main`
(`feat/`, `fix/`, `docs/`, `chore/`, `refactor/`, `test/`). Never work on `main`.

## 4. Implement

- `ponytail` mode (full): the smallest complete change that meets the acceptance criteria.
- Tests for every non-trivial behaviour. Run `uv run pytest`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run mypy src` once they exist; fix until green.
- Respect accepted ADRs and the hard rules in `CLAUDE.md`. A new architectural
  decision → propose `/new-adr`, do not decide silently.

## 5. Review

- Delegate to the **reviewer** agent: "Review the current branch against main for issue #<n>".
- Fix every **Must** and **Should** finding; re-run the checks. Re-run the reviewer
  if fixes were substantial. Report **Could** findings without fixing them unless trivial.
- Continue only when the verdict is **Ship**.

## 6. Hand-off

Reply with, in this order:

1. **Summary** — what changed, in 2–4 bullets.
2. **Explain** — only if Kafka, ClickHouse, Kubernetes/Helm, KEDA, OpenTelemetry or
   Prometheus/Grafana were touched: what, why, how it works, how to verify locally
   (exact commands, expected output), pitfalls.
3. **Maintainer actions** — anything the agent cannot or must not do.
4. **Checks** — the commands run and their result.
5. Proposed commit message (Conventional Commits, with the `Co-Authored-By` trailer)
   and PR title/body (template in `.github/pull_request_template.md`, `Closes #<n>`).

**STOP.** Ask: "Commit, push and open the PR?" On yes: `git commit`, `git push -u origin <branch>`,
`gh pr create`. Each command needs the maintainer's confirmation.

Never merge, force-push or push to `main`. The maintainer squash-merges.
