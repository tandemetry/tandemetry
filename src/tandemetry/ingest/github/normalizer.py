from tandemetry.events.envelope import Event
from tandemetry.ingest.github.mapper import (
    check_run_event,
    commit_events,
    merge_event,
    parse_webhook,
    pull_request_event,
    review_event,
)
from tandemetry.ingest.github.ports import GitHubApi
from tandemetry.ingest.github.raw import RawWebhook
from tandemetry.ingest.github.webhooks import CheckRunWebhook, PullRequestWebhook, ReviewWebhook

COMMIT_ACTIONS = frozenset(("opened", "synchronize"))


class WebhookNormalizer:
    """Turns a raw delivery into events, fetching from the GitHub API what the webhook lacks."""

    def __init__(self, api: GitHubApi) -> None:
        self._api = api

    async def normalize(self, raw: RawWebhook) -> list[Event]:
        match parse_webhook(raw):
            case PullRequestWebhook() as webhook:
                return await self._pull_request(webhook)
            case ReviewWebhook() as webhook:
                return _present(review_event(webhook))
            case CheckRunWebhook() as webhook:
                return _present(check_run_event(webhook))
            case None:
                return []

    async def _pull_request(self, webhook: PullRequestWebhook) -> list[Event]:
        events = _present(pull_request_event(webhook))
        installation, repo = webhook.installation.id, webhook.repository.full_name
        number = webhook.pull_request.number
        if webhook.action in COMMIT_ACTIONS:
            commits = await self._api.pull_request_commits(installation, repo, number)
            events.extend(commit_events(webhook, commits))
        if webhook.action == "closed" and webhook.pull_request.merged_at is not None:
            files = await self._api.pull_request_files(installation, repo, number)
            events.append(merge_event(webhook, files))
        return events


def _present(event: Event | None) -> list[Event]:
    return [] if event is None else [event]
