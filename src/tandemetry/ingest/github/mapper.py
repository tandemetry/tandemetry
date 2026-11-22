from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from functools import wraps

from pydantic import ValidationError

from tandemetry.events.envelope import Event, EventPayload, Source
from tandemetry.events.payloads import (
    CheckRun,
    Commit,
    FileChange,
    Merge,
    PullRequest,
    PullRequestAction,
    Review,
)
from tandemetry.events.validation import describe
from tandemetry.ingest.github.raw import RawWebhook
from tandemetry.ingest.github.rest import PullRequestCommit, PullRequestFile
from tandemetry.ingest.github.webhooks import (
    CheckRunData,
    CheckRunWebhook,
    PullRequestData,
    PullRequestWebhook,
    Repository,
    ReviewData,
    ReviewWebhook,
)

Webhook = PullRequestWebhook | ReviewWebhook | CheckRunWebhook

WEBHOOK_MODELS: Mapping[str, type[Webhook]] = {
    "pull_request": PullRequestWebhook,
    "pull_request_review": ReviewWebhook,
    "check_run": CheckRunWebhook,
}


class InvalidWebhookError(Exception):
    """A delivery that does not have the shape or data its event requires."""


def _validated[**P, R](mapper: Callable[P, R]) -> Callable[P, R]:
    @wraps(mapper)
    def guarded(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return mapper(*args, **kwargs)
        except ValidationError as error:
            raise InvalidWebhookError(describe(error)) from None

    return guarded


@_validated
def parse_webhook(raw: RawWebhook) -> Webhook | None:
    """The typed webhook of a supported event; `None` for any other event."""
    model = WEBHOOK_MODELS.get(raw.event)
    return None if model is None else model.model_validate_json(raw.body)


@_validated
def pull_request_event(
    repository: Repository, pull_request: PullRequestData, action: PullRequestAction
) -> Event | None:
    """The pull request fact for an action; `None` for a deleted author."""
    if pull_request.user is None:
        return None
    return _event(
        repository,
        _pull_request_time(pull_request, action),
        PullRequest(
            number=pull_request.number,
            action=action,
            author=pull_request.user.login,
            body=pull_request.body or "",
            head_branch=pull_request.head.ref,
            labels=tuple(label.name for label in pull_request.labels),
        ),
    )


@_validated
def merge_event(
    repository: Repository, pull_request: PullRequestData, files: Sequence[PullRequestFile]
) -> Event:
    """The merge fact of a merged pull request with its changed files."""
    if pull_request.merged_at is None or pull_request.merge_commit_sha is None:
        raise InvalidWebhookError("pull_request: merged_at and merge_commit_sha are required")
    return _event(
        repository,
        pull_request.merged_at,
        Merge(
            pull_request=pull_request.number,
            merge_commit_sha=pull_request.merge_commit_sha,
            files=tuple(
                FileChange(path=file.filename, additions=file.additions, deletions=file.deletions)
                for file in files
            ),
        ),
    )


@_validated
def commit_events(
    repository: Repository, pull_request: int, commits: Sequence[PullRequestCommit]
) -> list[Event]:
    """One commit fact per pull request commit, timed by the git committer date."""
    return [
        _event(
            repository,
            commit.commit.committer.date,
            Commit(
                sha=commit.sha,
                pull_request=pull_request,
                author_login=commit.author.login if commit.author else None,
                author_email=commit.commit.author.email,
                message=commit.commit.message,
            ),
        )
        for commit in commits
    ]


@_validated
def review_event(repository: Repository, pull_request: int, review: ReviewData) -> Event | None:
    """The review fact of a submitted review; `None` for a deleted reviewer."""
    if review.user is None:
        return None
    if review.submitted_at is None:
        raise InvalidWebhookError("review.submitted_at is required")
    return _event(
        repository,
        review.submitted_at,
        Review(review_id=review.id, pull_request=pull_request, reviewer=review.user.login),
    )


@_validated
def check_run_event(repository: Repository, check_run: CheckRunData) -> Event:
    """The check run fact of a completed check run."""
    if check_run.conclusion is None or check_run.completed_at is None:
        raise InvalidWebhookError("check_run: conclusion and completed_at are required")
    return _event(
        repository,
        check_run.completed_at,
        CheckRun(
            check_run_id=check_run.id,
            name=check_run.name,
            head_sha=check_run.head_sha,
            conclusion=check_run.conclusion,
        ),
    )


def pull_request_action(action: str) -> PullRequestAction | None:
    """The tracked pull request action of a webhook action; `None` for untracked ones."""
    try:
        return PullRequestAction(action)
    except ValueError:
        return None


def _pull_request_time(pull_request: PullRequestData, action: PullRequestAction) -> datetime:
    match action:
        case PullRequestAction.OPENED:
            return pull_request.created_at
        case PullRequestAction.CLOSED if pull_request.closed_at is not None:
            return pull_request.closed_at
        case PullRequestAction.CLOSED:
            raise InvalidWebhookError("pull_request.closed_at is required")
        case PullRequestAction.EDITED | PullRequestAction.REOPENED:
            return pull_request.updated_at


def _event(repository: Repository, occurred_at: datetime, payload: EventPayload) -> Event:
    try:
        return Event.create(
            Source.GITHUB, repository.id, repository.full_name, occurred_at, payload
        )
    except ValidationError as error:
        raise InvalidWebhookError(describe(error)) from None
