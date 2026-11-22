from tandemetry.events.envelope import Event
from tandemetry.ingest.github.mapper import (
    check_run_event,
    commit_events,
    merge_event,
    parse_webhook,
    pull_request_action,
    pull_request_event,
    review_event,
)
from tandemetry.ingest.github.ports import GitHubApi
from tandemetry.ingest.github.raw import RawWebhook
from tandemetry.ingest.github.webhooks import CheckRunWebhook, PullRequestWebhook, ReviewWebhook

COMMIT_ACTIONS = frozenset(("opened", "synchronize"))
MERGE_ACTION = "closed"
REVIEW_ACTION = "submitted"
CHECK_RUN_ACTION = "completed"


class WebhookNormalizer:
    """Turns a raw delivery into events, fetching from the GitHub API what the webhook lacks."""

    def __init__(self, api: GitHubApi) -> None:
        self._api = api

    async def normalize(self, raw: RawWebhook) -> list[Event]:
        match parse_webhook(raw):
            case PullRequestWebhook() as webhook:
                return await self._pull_request(webhook)
            case ReviewWebhook(action=action) as webhook if action == REVIEW_ACTION:
                number = webhook.pull_request.number
                return _present(review_event(webhook.repository, number, webhook.review))
            case CheckRunWebhook(action=action) as webhook if action == CHECK_RUN_ACTION:
                return [check_run_event(webhook.repository, webhook.check_run)]
            case _:
                return []

    async def _pull_request(self, webhook: PullRequestWebhook) -> list[Event]:
        repository, pull_request = webhook.repository, webhook.pull_request
        installation = webhook.installation.id
        events = _pull_request_fact(webhook)
        if webhook.action in COMMIT_ACTIONS:
            commits = await self._api.pull_request_commits(
                installation, repository.full_name, pull_request.number
            )
            events.extend(commit_events(repository, pull_request.number, commits))
        if webhook.action == MERGE_ACTION and pull_request.merged_at is not None:
            files = await self._api.pull_request_files(
                installation, repository.full_name, pull_request.number
            )
            events.append(merge_event(repository, pull_request, files))
        return events


def _pull_request_fact(webhook: PullRequestWebhook) -> list[Event]:
    action = pull_request_action(webhook.action)
    if action is None:
        return []
    return _present(pull_request_event(webhook.repository, webhook.pull_request, action))


def _present(event: Event | None) -> list[Event]:
    return [] if event is None else [event]
