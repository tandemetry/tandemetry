from datetime import UTC, datetime

from tandemetry.events.envelope import Event, Source
from tandemetry.events.payloads import PullRequest, PullRequestAction

SAMPLE_EVENT = Event.create(
    Source.GITHUB,
    1296269,
    "acme/widgets",
    datetime(2026, 11, 13, 10, 0, 0, 123456, tzinfo=UTC),
    PullRequest(
        number=7,
        action=PullRequestAction.OPENED,
        author="copilot-swe-agent[bot]",
        body="Generated with Claude Code",
        head_branch="codex/fix-login",
        labels=("ai-generated",),
    ),
)
