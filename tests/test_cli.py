import argparse
import asyncio
import re
import socket
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi import FastAPI
from pydantic import SecretStr

from tandemetry.cli import (
    BackfillCommand,
    Cli,
    Command,
    CommandError,
    ConsumeCommand,
    MigrateCommand,
    NormalizeCommand,
    PackageVersionProvider,
    PublishSampleCommand,
    ServeCommand,
)
from tandemetry.events.envelope import Event
from tandemetry.events.ports import Record
from tandemetry.events.sample import SAMPLE_EVENT
from tandemetry.ingest.github.ports import GitHubApiError
from tandemetry.ingest.github.raw import RawWebhook
from tandemetry.ingest.github.rest import PullRequestCommit, PullRequestFile
from tandemetry.ingest.github.webhooks import (
    CheckRunData,
    PullRequestData,
    Repository,
    ReviewData,
)
from tandemetry.settings import (
    ApiSettings,
    ClickHouseSettings,
    GitHubSettings,
    KafkaSettings,
    Settings,
)

NO_ARGUMENTS = argparse.Namespace()


class FakeVersionProvider:
    def get(self) -> str:
        return "9.9.9"


class FakeCommand(Command):
    help = "do the thing"

    def __init__(self) -> None:
        self.runs = 0

    async def run(self, arguments: argparse.Namespace) -> None:
        self.runs += 1


@pytest.fixture
def unused_tcp_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


@pytest.fixture
def command() -> FakeCommand:
    return FakeCommand()


@pytest.fixture
def cli(command: FakeCommand) -> Cli:
    return Cli(FakeVersionProvider(), Settings(), {"thing": command})


def test_version_flag_prints_name_and_version(cli: Cli, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.run(["--version"]) == 0
    assert capsys.readouterr().out.strip() == "tandemetry 9.9.9"


def test_unknown_flag_returns_non_zero(cli: Cli) -> None:
    assert cli.run(["--unknown"]) != 0


def test_subcommand_runs_its_command(cli: Cli, command: FakeCommand) -> None:
    assert cli.run(["thing"]) == 0
    assert command.runs == 1


def test_unknown_subcommand_returns_non_zero(cli: Cli, command: FakeCommand) -> None:
    assert cli.run(["other"]) != 0
    assert command.runs == 0


def test_no_subcommand_prints_help(cli: Cli, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.run([]) == 0
    assert "do the thing" in capsys.readouterr().out


class FailingCommand(Command):
    help = "always fails"

    async def run(self, arguments: argparse.Namespace) -> None:
        raise CommandError("service unreachable")


def test_command_error_is_reported_on_stderr_without_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = Cli(FakeVersionProvider(), Settings(), {"fail": FailingCommand()})
    assert cli.run(["fail"]) == 1
    assert capsys.readouterr().err.strip() == "tandemetry fail: service unreachable"


def test_migrate_reports_unreachable_clickhouse(unused_tcp_port: int) -> None:
    settings = ClickHouseSettings(port=unused_tcp_port, password=SecretStr("secret"))
    with pytest.raises(CommandError, match=f"ClickHouse at localhost:{unused_tcp_port}") as error:
        asyncio.run(MigrateCommand(settings).run(NO_ARGUMENTS))
    assert "secret" not in str(error.value)


class FakePublisher:
    def __init__(self) -> None:
        self.published: list[Event] = []

    async def publish(self, event: Event) -> None:
        self.published.append(event)


def test_publish_sample_publishes_the_sample_event(capsys: pytest.CaptureFixture[str]) -> None:
    publisher = FakePublisher()

    @asynccontextmanager
    async def open_publisher(settings: KafkaSettings) -> AsyncIterator[FakePublisher]:
        yield publisher

    asyncio.run(PublishSampleCommand(KafkaSettings(), open_publisher).run(NO_ARGUMENTS))

    assert publisher.published == [SAMPLE_EVENT]
    assert capsys.readouterr().out.strip() == (
        f"published {SAMPLE_EVENT.event_id} to events.normalized"
    )


def test_sample_event_id_is_stable() -> None:
    assert SAMPLE_EVENT.event_id == UUID("f9976cac-b4f9-5486-9348-4aa78a1ffc73")


def test_publish_sample_reports_unreachable_kafka(unused_tcp_port: int) -> None:
    settings = KafkaSettings(bootstrap_servers=f"localhost:{unused_tcp_port}")
    with pytest.raises(CommandError, match=f"Kafka at localhost:{unused_tcp_port}"):
        asyncio.run(PublishSampleCommand(settings).run(NO_ARGUMENTS))


class InterruptedCommand(Command):
    help = "interrupted by the user"

    async def run(self, arguments: argparse.Namespace) -> None:
        raise KeyboardInterrupt


def test_interrupted_command_exits_with_130() -> None:
    cli = Cli(FakeVersionProvider(), Settings(), {"wait": InterruptedCommand()})
    assert cli.run(["wait"]) == 130


class NullSink:
    async def write(self, events: Sequence[Event]) -> None:
        return None


@asynccontextmanager
async def open_null_sink(settings: ClickHouseSettings) -> AsyncIterator[NullSink]:
    yield NullSink()


def test_consume_reports_unreachable_clickhouse(unused_tcp_port: int) -> None:
    clickhouse = ClickHouseSettings(port=unused_tcp_port, password=SecretStr("secret"))
    with pytest.raises(CommandError, match=f"ClickHouse at localhost:{unused_tcp_port}") as error:
        asyncio.run(ConsumeCommand(KafkaSettings(), clickhouse).run(NO_ARGUMENTS))
    assert "secret" not in str(error.value)


def test_consume_reports_unreachable_kafka(unused_tcp_port: int) -> None:
    kafka = KafkaSettings(bootstrap_servers=f"localhost:{unused_tcp_port}")
    command = ConsumeCommand(kafka, ClickHouseSettings(), open_sink=open_null_sink)
    with pytest.raises(CommandError, match=f"Kafka at localhost:{unused_tcp_port}"):
        asyncio.run(command.run(NO_ARGUMENTS))


def test_package_version_provider_reads_installed_metadata() -> None:
    assert PackageVersionProvider().get()


GITHUB = GitHubSettings(
    webhook_secret=SecretStr("hook-key"),
    client_id="Iv1.client",
    private_key=SecretStr("pem"),
)


class FakeRawPublisher:
    async def publish(self, webhook: RawWebhook) -> None:
        return None


@asynccontextmanager
async def open_fake_raw_publisher(settings: KafkaSettings) -> AsyncIterator[FakeRawPublisher]:
    yield FakeRawPublisher()


def test_serve_requires_the_webhook_secret() -> None:
    command = ServeCommand(ApiSettings(), GitHubSettings(), KafkaSettings())
    with pytest.raises(CommandError, match="TANDEMETRY_GITHUB__WEBHOOK_SECRET"):
        asyncio.run(command.run(NO_ARGUMENTS))


def test_serve_runs_the_api_on_the_configured_address() -> None:
    served: list[tuple[FastAPI, ApiSettings]] = []

    async def serve(app: FastAPI, settings: ApiSettings) -> None:
        served.append((app, settings))

    api = ApiSettings(port=8123)
    asyncio.run(
        ServeCommand(api, GITHUB, KafkaSettings(), open_fake_raw_publisher, serve).run(NO_ARGUMENTS)
    )
    [(app, settings)] = served
    assert isinstance(app, FastAPI)
    assert settings == api


def test_serve_reports_unreachable_kafka(unused_tcp_port: int) -> None:
    kafka = KafkaSettings(bootstrap_servers=f"localhost:{unused_tcp_port}")
    with pytest.raises(CommandError, match=f"Kafka at localhost:{unused_tcp_port}"):
        asyncio.run(ServeCommand(ApiSettings(), GITHUB, kafka).run(NO_ARGUMENTS))


def test_normalize_requires_app_credentials() -> None:
    command = NormalizeCommand(KafkaSettings(), GitHubSettings())
    with pytest.raises(CommandError, match="TANDEMETRY_GITHUB__CLIENT_ID"):
        asyncio.run(command.run(NO_ARGUMENTS))


class FailingGitHubApi:
    async def pull_request_files(
        self, installation_id: int, repo: str, number: int
    ) -> Sequence[PullRequestFile]:
        raise GitHubApiError("HTTP 401")

    async def pull_request_commits(
        self, installation_id: int, repo: str, number: int
    ) -> Sequence[PullRequestCommit]:
        raise GitHubApiError("HTTP 401")


class OneRecordSource:
    def __init__(self, value: bytes) -> None:
        self._value = value

    async def next_batch(self) -> Sequence[Record]:
        return [Record("raw.github", 0, 0, self._value)]

    async def commit(self) -> None:
        return None


def test_normalize_reports_a_github_failure() -> None:
    body = (
        '{"action": "opened", "repository": {"id": 1, "full_name": "a/b"},'
        ' "installation": {"id": 1}, "pull_request": {"number": 1, "user": null, "body": null,'
        ' "head": {"ref": "x", "sha": "abc"}, "labels": [], "created_at": "2026-01-01T00:00:00Z",'
        ' "updated_at": "2026-01-01T00:00:00Z", "closed_at": null, "merged_at": null,'
        ' "merge_commit_sha": null}}'
    )
    raw = RawWebhook(delivery_id="d", event="pull_request", repo_id=1, body=body)

    @asynccontextmanager
    async def open_source(settings: KafkaSettings) -> AsyncIterator[OneRecordSource]:
        yield OneRecordSource(raw.model_dump_json().encode())

    @asynccontextmanager
    async def open_api(settings: GitHubSettings) -> AsyncIterator[FailingGitHubApi]:
        yield FailingGitHubApi()

    @asynccontextmanager
    async def open_publisher(settings: KafkaSettings) -> AsyncIterator[FakePublisher]:
        yield FakePublisher()

    command = NormalizeCommand(KafkaSettings(), GITHUB, open_source, open_publisher, open_api)
    failure = re.escape("GitHub API at https://api.github.com: HTTP 401")
    with pytest.raises(CommandError, match=failure):
        asyncio.run(command.run(NO_ARGUMENTS))


class EmptyHistoryApi(FailingGitHubApi):
    def __init__(self, failure: GitHubApiError | None = None) -> None:
        self._failure = failure
        self.since: list[datetime | None] = []

    async def repository(self, installation_id: int, repo: str) -> Repository:
        if self._failure is not None:
            raise self._failure
        return Repository(id=1, full_name=repo)

    async def pull_requests(
        self, installation_id: int, repo: str, since: datetime | None
    ) -> Sequence[PullRequestData]:
        self.since.append(since)
        return []

    async def pull_request_reviews(
        self, installation_id: int, repo: str, number: int
    ) -> Sequence[ReviewData]:
        return []

    async def check_runs(self, installation_id: int, repo: str, sha: str) -> Sequence[CheckRunData]:
        return []


def backfill_cli(api: EmptyHistoryApi, github: GitHubSettings = GITHUB) -> Cli:
    @asynccontextmanager
    async def open_api(settings: GitHubSettings) -> AsyncIterator[EmptyHistoryApi]:
        yield api

    @asynccontextmanager
    async def open_publisher(settings: KafkaSettings) -> AsyncIterator[FakePublisher]:
        yield FakePublisher()

    command = BackfillCommand(KafkaSettings(), github, open_publisher, open_api)
    return Cli(FakeVersionProvider(), Settings(), {"backfill": command})


@pytest.mark.parametrize(
    ("since", "expected"),
    [
        ("2026-11-01", datetime(2026, 11, 1, tzinfo=UTC)),
        ("2026-11-01T10:30:00", datetime(2026, 11, 1, 10, 30, tzinfo=UTC)),
        ("2026-11-01T10:30:00+02:00", datetime(2026, 11, 1, 8, 30, tzinfo=UTC)),
    ],
)
def test_backfill_reads_since_as_utc_unless_a_zone_is_given(
    since: str, expected: datetime, capsys: pytest.CaptureFixture[str]
) -> None:
    api = EmptyHistoryApi()
    argv = ["backfill", "--installation", "1", "--repo", "a/b", "--since", since]
    assert backfill_cli(api).run(argv) == 0
    assert api.since == [expected]
    assert capsys.readouterr().out.strip() == "backfill of a/b done"


def test_backfill_without_since_reads_every_pull_request() -> None:
    api = EmptyHistoryApi()
    assert backfill_cli(api).run(["backfill", "--installation", "1", "--repo", "a/b"]) == 0
    assert api.since == [None]


@pytest.mark.parametrize(
    "argv",
    [
        ["backfill", "--repo", "a/b"],
        ["backfill", "--installation", "1"],
        ["backfill", "--installation", "1", "--repo", "a/b", "--since", "yesterday"],
    ],
)
def test_backfill_rejects_incomplete_arguments(argv: list[str]) -> None:
    api = EmptyHistoryApi()
    assert backfill_cli(api).run(argv) != 0
    assert api.since == []


def test_backfill_requires_app_credentials(capsys: pytest.CaptureFixture[str]) -> None:
    cli = backfill_cli(EmptyHistoryApi(), GitHubSettings())
    assert cli.run(["backfill", "--installation", "1", "--repo", "a/b"]) == 1
    assert "TANDEMETRY_GITHUB__CLIENT_ID" in capsys.readouterr().err


def test_backfill_reports_a_github_failure(capsys: pytest.CaptureFixture[str]) -> None:
    cli = backfill_cli(EmptyHistoryApi(GitHubApiError("HTTP 401")))
    assert cli.run(["backfill", "--installation", "1", "--repo", "a/b"]) == 1
    assert capsys.readouterr().err.strip() == (
        "tandemetry backfill: GitHub API at https://api.github.com: HTTP 401"
    )
