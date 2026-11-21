from pydantic import AwareDatetime, BaseModel, ConfigDict, PositiveInt

from tandemetry.events.payloads import CheckConclusion


class GitHubModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class Repository(GitHubModel):
    id: PositiveInt
    full_name: str


class RepositoryWebhook(GitHubModel):
    repository: Repository


class Installation(GitHubModel):
    id: PositiveInt


class Account(GitHubModel):
    login: str


class Label(GitHubModel):
    name: str


class Head(GitHubModel):
    ref: str


class PullRequestData(GitHubModel):
    number: PositiveInt
    user: Account | None
    body: str | None
    head: Head
    labels: tuple[Label, ...]
    created_at: AwareDatetime
    updated_at: AwareDatetime
    closed_at: AwareDatetime | None
    merged_at: AwareDatetime | None
    merge_commit_sha: str | None


class PullRequestWebhook(GitHubModel):
    action: str
    pull_request: PullRequestData
    repository: Repository
    installation: Installation


class ReviewData(GitHubModel):
    id: PositiveInt
    user: Account | None
    submitted_at: AwareDatetime | None


class PullRequestNumber(GitHubModel):
    number: PositiveInt


class ReviewWebhook(GitHubModel):
    action: str
    review: ReviewData
    pull_request: PullRequestNumber
    repository: Repository


class CheckRunData(GitHubModel):
    id: PositiveInt
    name: str
    head_sha: str
    conclusion: CheckConclusion | None
    completed_at: AwareDatetime | None


class CheckRunWebhook(GitHubModel):
    action: str
    check_run: CheckRunData
    repository: Repository
