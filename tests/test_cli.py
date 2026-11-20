import asyncio
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import pytest
from pydantic import SecretStr

from tandemetry.cli import (
    Cli,
    CommandError,
    MigrateCommand,
    PackageVersionProvider,
    PublishSampleCommand,
)
from tandemetry.events.envelope import Event
from tandemetry.events.sample import SAMPLE_EVENT
from tandemetry.settings import ClickHouseSettings, KafkaSettings, Settings


class FakeVersionProvider:
    def get(self) -> str:
        return "9.9.9"


class FakeCommand:
    help = "do the thing"

    def __init__(self) -> None:
        self.runs = 0

    async def run(self) -> None:
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


class FailingCommand:
    help = "always fails"

    async def run(self) -> None:
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
        asyncio.run(MigrateCommand(settings).run())
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

    asyncio.run(PublishSampleCommand(KafkaSettings(), open_publisher).run())

    assert publisher.published == [SAMPLE_EVENT]
    assert capsys.readouterr().out.strip() == (
        f"published {SAMPLE_EVENT.event_id} to events.normalized"
    )


def test_sample_event_id_is_stable() -> None:
    assert SAMPLE_EVENT.event_id == UUID("f9976cac-b4f9-5486-9348-4aa78a1ffc73")


def test_publish_sample_reports_unreachable_kafka(unused_tcp_port: int) -> None:
    settings = KafkaSettings(bootstrap_servers=f"localhost:{unused_tcp_port}")
    with pytest.raises(CommandError, match=f"Kafka at localhost:{unused_tcp_port}"):
        asyncio.run(PublishSampleCommand(settings).run())


def test_package_version_provider_reads_installed_metadata() -> None:
    assert PackageVersionProvider().get()
