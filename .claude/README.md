# .claude/

Claude Code configuration for Tandemetry. The development process is described in
[`docs/process.md`](../docs/process.md).

| Path | What |
| --- | --- |
| `settings.json` | Shared permissions: what the agent may run freely, what needs confirmation, what is forbidden |
| `agents/planner.md` | Read-only subagent: issue → implementation plan |
| `agents/reviewer.md` | Read-only subagent: independent pre-PR review |
| `skills/ponytail*` | Coding style, change review and repo audit |
| `skills/new-adr` | Create an Architecture Decision Record |

Personal overrides go in `.claude/settings.local.json` (git-ignored).

## Third-party skills

`skills/ponytail`, `skills/ponytail-review` and `skills/ponytail-audit` are vendored from
[dietrichgebert/ponytail](https://github.com/dietrichgebert/ponytail) under the MIT license,
with a short Tandemetry-specific note appended to each.
