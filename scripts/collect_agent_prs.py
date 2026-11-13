"""One-off collector of agent signatures from public PRs. Usage: collect_agent_prs.py OUT.json."""

import json
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from typing import Any

REPOS = [
    "microsoft/vscode",
    "microsoft/TypeScript",
    "microsoft/playwright",
    "dotnet/runtime",
    "dotnet/aspnetcore",
    "vercel/next.js",
    "facebook/react",
    "denoland/deno",
    "oven-sh/bun",
    "astral-sh/ruff",
    "astral-sh/uv",
    "python/cpython",
    "rust-lang/rust",
    "golang/go",
    "pytorch/pytorch",
    "huggingface/transformers",
    "langchain-ai/langchain",
    "home-assistant/core",
    "ollama/ollama",
    "openai/codex",
    "google-gemini/gemini-cli",
    "anthropics/claude-code",
]
PRS_PER_REPO = 100
COMMITS_PER_REPO = 100
EXAMPLES_PER_SIGNAL = 3
SEARCH_PAUSE_SECONDS = 3
SEARCH_SAMPLE = 30

AGENT_HINT = re.compile(
    r"claude|anthropic|codex|openai|copilot|devin|cognition|cursor|gemini|jules|aider|"
    r"windsurf|codeium|cline|continue|sweep|\bai\b|\bbot\b|\[bot\]|🤖",
    re.IGNORECASE,
)
DESCRIPTION_MARKERS = re.compile(
    r"generated (?:with|by)[^\n]{0,60}|created (?:with|by)[^\n]{0,40}(?:ai|agent|claude|codex|"
    r"copilot|cursor|devin)[^\n]{0,20}|🤖[^\n]{0,60}|co-authored-by:[^\n]*(?:claude|codex|copilot|"
    r"devin|cursor|gemini)[^\n]*",
    re.IGNORECASE,
)
AGENT_TRAILER_EMAIL = re.compile(
    r"noreply@anthropic\.com|noreply@openai\.com|codex@openai\.com|cursoragent@cursor\.com|"
    r"\+copilot@users\.noreply|devin|gemini|jules|aider|open-swe",
    re.IGNORECASE,
)
TRAILER = re.compile(r"^co-authored-by:\s*(.+?)\s*<([^>]+)>", re.IGNORECASE | re.MULTILINE)
SEARCH_QUERIES = {
    "author:app/copilot-swe-agent": "is:pr author:app/copilot-swe-agent",
    "author:app/devin-ai-integration": "is:pr author:app/devin-ai-integration",
    "author:app/cursor": "is:pr author:app/cursor",
    "author:app/google-labs-jules": "is:pr author:app/google-labs-jules",
    "head:codex/": "is:pr head:codex/",
    "head:claude/": "is:pr head:claude/",
    "head:cursor/": "is:pr head:cursor/",
    "body:Generated with Claude Code": 'is:pr "Generated with Claude Code" in:body',
    "body:Co-Authored-By Claude": 'is:pr "noreply@anthropic.com" in:body',
}


def gh_api(path: str, **params: str | int) -> Any:  # noqa: ANN401
    command = ["gh", "api", "-X", "GET", path]
    for key, value in params.items():
        command += ["-f", f"{key}={value}"]
    result = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        print(f"gh api {path} failed: {result.stderr.strip()}", file=sys.stderr)
        return None
    return json.loads(result.stdout)


def pull_signals(pr: dict[str, Any]) -> list[tuple[str, str]]:
    signals: list[tuple[str, str]] = []
    user = pr.get("user") or {}
    if user.get("type") == "Bot":
        signals.append(("bot_author", user["login"]))
    head_ref = pr["head"]["ref"]
    if "/" in head_ref and AGENT_HINT.search(head_ref.split("/", 1)[0]):
        signals.append(("branch_prefix", head_ref.split("/", 1)[0] + "/"))
    for label in pr.get("labels", []):
        if AGENT_HINT.search(label["name"]):
            signals.append(("label", label["name"]))
    body = pr.get("body") or ""
    for match in DESCRIPTION_MARKERS.finditer(body):
        signals.append(("description_phrase", match.group(0).strip().lower()))
    return signals


def commit_signals(commit: dict[str, Any]) -> list[tuple[str, str]]:
    message = commit["commit"]["message"]
    return [
        ("commit_trailer", f"{name} <{email}>")
        for name, email in TRAILER.findall(message)
        if AGENT_TRAILER_EMAIL.search(email)
    ]


def collect_repo(repo: str) -> dict[str, Any]:
    counts: Counter[tuple[str, str]] = Counter()
    examples: dict[tuple[str, str], list[str]] = defaultdict(list)
    pulls = (
        gh_api(f"repos/{repo}/pulls", state="closed", per_page=PRS_PER_REPO, sort="updated") or []
    )
    for pr in pulls:
        for signal in pull_signals(pr):
            counts[signal] += 1
            if len(examples[signal]) < EXAMPLES_PER_SIGNAL:
                examples[signal].append(pr["html_url"])
    commits = gh_api(f"repos/{repo}/commits", per_page=COMMITS_PER_REPO) or []
    for commit in commits:
        for signal in commit_signals(commit):
            counts[signal] += 1
            if len(examples[signal]) < EXAMPLES_PER_SIGNAL:
                examples[signal].append(commit["html_url"])
    return {
        "prs_reviewed": len(pulls),
        "commits_reviewed": len(commits),
        "signals": [
            {"kind": kind, "value": value, "count": count, "examples": examples[(kind, value)]}
            for (kind, value), count in counts.most_common()
        ],
    }


def search_totals() -> dict[str, dict[str, Any]]:
    totals: dict[str, dict[str, Any]] = {}
    for name, query in SEARCH_QUERIES.items():
        response = gh_api("search/issues", q=query, per_page=SEARCH_SAMPLE)
        items = response["items"] if response else []
        authors = Counter(item["user"]["login"] for item in items if item["user"]["type"] == "Bot")
        totals[name] = {
            "total_count": response["total_count"] if response else None,
            "sampled": len(items),
            "bot_authors_in_sample": dict(authors),
            "examples": [item["html_url"] for item in items[:EXAMPLES_PER_SIGNAL]],
        }
        time.sleep(SEARCH_PAUSE_SECONDS)
    return totals


def main() -> None:
    output_path = sys.argv[1]
    report = {
        "repos": {repo: collect_repo(repo) for repo in REPOS},
        "global_search_totals": search_totals(),
    }
    with open(output_path, "w", encoding="utf-8") as output:
        json.dump(report, output, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
