from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt, model_validator

Sha = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
Login = Annotated[str, Field(min_length=1)]


class DomainModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Payload(DomainModel, ABC):
    type: str

    @property
    @abstractmethod
    def natural_key(self) -> str:
        """Identity of the fact within its type and repository."""


class PullRequestAction(StrEnum):
    OPENED = "opened"
    EDITED = "edited"
    CLOSED = "closed"
    REOPENED = "reopened"


class CheckConclusion(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    NEUTRAL = "neutral"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"
    ACTION_REQUIRED = "action_required"
    STALE = "stale"


class FileChange(DomainModel):
    path: str = Field(min_length=1)
    additions: NonNegativeInt
    deletions: NonNegativeInt


class PullRequest(Payload):
    type: Literal["pull_request"] = "pull_request"
    number: PositiveInt
    action: PullRequestAction
    author: Login
    body: str
    head_branch: str
    labels: tuple[str, ...]

    @property
    def natural_key(self) -> str:
        return f"{self.number}:{self.action}"


class Commit(Payload):
    type: Literal["commit"] = "commit"
    sha: Sha
    pull_request: PositiveInt | None
    author_login: Login | None
    author_email: str
    message: str

    @property
    def natural_key(self) -> str:
        return f"{self.sha}:{self.pull_request or ''}"


class Review(Payload):
    type: Literal["review"] = "review"
    review_id: PositiveInt
    pull_request: PositiveInt
    reviewer: Login

    @property
    def natural_key(self) -> str:
        return str(self.review_id)


class CheckRun(Payload):
    type: Literal["check_run"] = "check_run"
    check_run_id: PositiveInt
    name: str
    head_sha: Sha
    conclusion: CheckConclusion

    @property
    def natural_key(self) -> str:
        return str(self.check_run_id)


class Merge(Payload):
    type: Literal["merge"] = "merge"
    pull_request: PositiveInt
    merge_commit_sha: Sha
    files: tuple[FileChange, ...]

    @property
    def natural_key(self) -> str:
        return str(self.pull_request)


class Revert(Payload):
    type: Literal["revert"] = "revert"
    sha: Sha
    reverted_shas: tuple[Sha, ...]
    reverted_pull_request: PositiveInt | None

    @property
    def natural_key(self) -> str:
        return self.sha

    @model_validator(mode="after")
    def _has_a_target(self) -> Self:
        if not self.reverted_shas and self.reverted_pull_request is None:
            raise ValueError("a revert must name reverted commits or a reverted pull request")
        return self
