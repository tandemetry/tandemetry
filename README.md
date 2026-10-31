# Tandemetry

**See how humans and AI agents ship code together.**

Open-source, self-hosted analytics for AI coding agents: compare agent vs human work in your
repositories — merge rate, reverts, rework, CI failures, review load and cost per PR.

> Status: early development (v0.1 in progress). Not ready for production use.

## Why

AI agents now open a large share of pull requests, but teams can't tell whether that code is
merged, reverted or rewritten — or which agent works best in their codebase. Tandemetry answers
that from your own Git data, without sending code anywhere and without LLM calls.

## Principles

- **Self-hosted.** Your code and data stay in your infrastructure.
- **Agent-agnostic.** Claude Code, Codex, Copilot coding agent, Devin, Cursor and more.
- **Outcomes, not activity.** Reverts and rework, not just PR counts.
- **No individual rankings.** Teams, repositories and agents only.
- **Deterministic.** Transparent attribution rules, no LLM in the core.

## Docs

- [Product](docs/product.md)
- [Architecture](docs/architecture.md)
- [Agent attribution](docs/attribution.md)
- [Roadmap](docs/roadmap.md)
- [Architecture decisions](docs/adr/)

## License

[Apache-2.0](LICENSE)
