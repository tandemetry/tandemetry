# Agent signatures research

Collected on 2026-11-07 with `scripts/collect_agent_prs.py` (read-only GitHub API through `gh api`).
Raw aggregates: `docs/research/data/signatures-2026-11-07.json` (counts and URLs only).
The result is the catalog in `src/tandemetry/attribution/signatures.yaml`.

## Method

1. **Repository sample.** 22 popular public repositories, chosen up front for size and for
   being known to use AI tooling: `microsoft/{vscode,TypeScript,playwright}`,
   `dotnet/{runtime,aspnetcore}`, `vercel/next.js`, `facebook/react`, `denoland/deno`,
   `oven-sh/bun`, `astral-sh/{ruff,uv}`, `python/cpython`, `rust-lang/rust`, `golang/go`,
   `pytorch/pytorch`, `huggingface/transformers`, `langchain-ai/langchain`,
   `home-assistant/core`, `ollama/ollama`, `openai/codex`, `google-gemini/gemini-cli`,
   `anthropics/claude-code`.
2. **Per repository.** The 100 most recently updated closed PRs (author type, branch prefix,
   labels, description phrases) and the 100 latest commits on the default branch (`Co-Authored-By`
   trailers).
3. **Global search.** For rare agents, GitHub issue search by bot author, branch prefix and
   description phrase, with the first 30 results sampled for bot logins.
4. **Privacy.** Only bot logins are stored; human logins and names are dropped. Trailers are kept
   only when their email belongs to a known agent identity. No diffs, file contents or PR bodies
   are stored.

## Findings

Trailer counts are trailer occurrences in the 100 latest commits; a squash commit can carry
several, so a count can exceed 100.

| Repository | PRs | Commits | Agent trailers | Other agent signals |
| --- | --- | --- | --- | --- |
| microsoft/vscode | 100 | 100 | 204 | 0 |
| dotnet/aspnetcore | 100 | 100 | 177 | 0 |
| huggingface/transformers | 100 | 100 | 149 | 0 |
| dotnet/runtime | 100 | 100 | 70 | 0 |
| oven-sh/bun | 100 | 100 | 48 | 0 |
| home-assistant/core | 100 | 100 | 21 | 0 |
| langchain-ai/langchain | 100 | 100 | 20 | 0 |
| python/cpython | 100 | 100 | 17 | 0 |
| microsoft/TypeScript | 100 | 100 | 16 | 0 |
| pytorch/pytorch | 100 | 100 | 13 | 0 |
| vercel/next.js | 100 | 100 | 12 | 0 |
| facebook/react | 100 | 100 | 12 | 0 |
| google-gemini/gemini-cli | 100 | 100 | 9 | 0 |
| anthropics/claude-code | 100 | 100 | 3 | 41 |
| astral-sh/ruff | 100 | 100 | 1 | 0 |
| denoland/deno, golang/go, ollama/ollama, openai/codex, astral-sh/uv, microsoft/playwright, rust-lang/rust | 100 each | 100 each | 0 | 0 |

| Agent | Strongest signal observed | Evidence |
| --- | --- | --- |
| GitHub Copilot coding agent | Bot author `Copilot` / `copilot-swe-agent[bot]`; trailers with `…+Copilot@users.noreply.github.com` | 2.1M PRs by `app/copilot-swe-agent`; 5 of 22 repos with trailers |
| Claude Code | Trailer `Co-Authored-By: Claude … <noreply@anthropic.com>`; description "Generated with Claude Code"; branch `claude/` | trailers in 7 of 22 repos; 22M PR bodies mention the phrase |
| Devin | Bot author `devin-ai-integration[bot]` | 333K PRs |
| Cursor | Bot author `cursor[bot]`; trailer `cursoragent@cursor.com`; branch `cursor/` | 187K PRs by the bot; 4 repos with trailers |
| Google Jules | Bot author `google-labs-jules[bot]` | 338K PRs |
| OpenAI Codex | Trailer `noreply@openai.com` / `codex@openai.com`; branch `codex/` | 8.9M PRs on `codex/` branches; only 2 trailers in the sample |
| Open SWE | Trailer `open-swe@users.noreply.github.com` | 20 trailers in one repo |

Claude Code trailers carry a model name in the display name (`Claude Opus 5.5`,
`Claude Sonnet 4.6`, `Claude Code (…)`), so matching must use the stable email, not the name.

## Conclusion for the 2026-11-07 criterion

**Signatures were found in real PRs: yes.** Five of the six target agents (Claude Code, Copilot
coding agent, Devin, Cursor, Codex) plus Jules and Open SWE have at least one high-confidence,
machine-readable signature, and agent trailers appear in 15 of 22 sampled repositories. The
"signatures found" half of the criterion holds. The other half (DevLake and Middleware lacking
agent attribution) is a separate item and is not covered here.

## Limitations

- **No trace.** IDE completions and in-editor edits leave nothing and count as `human`.
- **Squash merges** keep trailers only if the commit message is edited to include them, and some
  teams strip them; trailer rates are a lower bound.
- **Sampling bias.** The repositories were chosen for size and AI relevance, not at random, and
  the PR sample is the most recently updated closed PRs, which contained no bot-authored PRs;
  bot-authored PRs were found only through the global search.
- **Branch prefixes and phrases** (`codex/`, `claude/`, "Generated with Claude Code") are
  convention-based and can be copied by humans, hence medium confidence.
- **Search totals** are all of public GitHub and include duplicates, forks and abandoned
  repositories; treat them as an order of magnitude.
- **Copilot** appears as `Copilot` and as `copilot-swe-agent[bot]` depending on the API; both
  are in the catalog.
- **Automation noise.** Dependabot, Renovate and `github-actions[bot]` appear in trailers and
  are deliberately excluded from the catalog.
- Not observed, so not in the catalog: Copilot branch prefix, labels for any agent, Aider and
  Windsurf.

## Reproducing

```bash
gh auth login
uv run python scripts/collect_agent_prs.py docs/research/data/signatures-$(date +%F).json
```

About 22 × 2 REST requests plus 9 search requests (3 s apart; the search limit is 30 per minute),
well inside the authenticated limit of 5000 REST requests per hour.
