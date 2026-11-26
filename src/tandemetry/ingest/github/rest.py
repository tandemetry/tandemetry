from pydantic import AwareDatetime, NonNegativeInt

from tandemetry.ingest.github.webhooks import Account, CheckRunData, GitHubModel


class PullRequestFile(GitHubModel):
    filename: str
    additions: NonNegativeInt
    deletions: NonNegativeInt


class GitAuthor(GitHubModel):
    email: str


class GitCommitter(GitHubModel):
    date: AwareDatetime


class GitCommit(GitHubModel):
    author: GitAuthor
    committer: GitCommitter
    message: str


class PullRequestCommit(GitHubModel):
    sha: str
    author: Account | None
    commit: GitCommit


class InstallationToken(GitHubModel):
    token: str
    expires_at: AwareDatetime


class CheckRunsPage(GitHubModel):
    check_runs: tuple[CheckRunData, ...]
