import argparse
import asyncio
import sys
from collections.abc import Mapping, Sequence
from importlib.metadata import version
from typing import Protocol

from clickhouse_connect.driver.exceptions import Error as ClickHouseError

from tandemetry.settings import ClickHouseSettings, Settings
from tandemetry.storage.clickhouse import ClickHouseMigrator, clickhouse_client


class VersionProvider(Protocol):
    def get(self) -> str: ...


class CommandError(Exception):
    """A command failure reported to the user as one line, without a traceback."""


class Command(Protocol):
    help: str

    async def run(self) -> None: ...


class PackageVersionProvider:
    def __init__(self, package: str = "tandemetry") -> None:
        self._package = package

    def get(self) -> str:
        return version(self._package)


class MigrateCommand:
    help = "apply ClickHouse schema migrations"

    def __init__(self, settings: ClickHouseSettings) -> None:
        self._settings = settings

    async def run(self) -> None:
        try:
            async with clickhouse_client(self._settings) as client:
                applied = await ClickHouseMigrator(client).apply()
        except ClickHouseError as error:
            address = f"{self._settings.host}:{self._settings.port}"
            raise CommandError(f"ClickHouse at {address}: {error}") from error
        print(f"applied: {', '.join(applied) or 'nothing'}")


class Cli:
    def __init__(
        self,
        version_provider: VersionProvider,
        settings: Settings,
        commands: Mapping[str, Command],
    ) -> None:
        self._commands = commands
        self._parser = argparse.ArgumentParser(prog=settings.app_name)
        self._parser.add_argument(
            "--version",
            action="version",
            version=f"{settings.app_name} {version_provider.get()}",
        )
        subparsers = self._parser.add_subparsers(dest="command")
        for name, command in commands.items():
            subparsers.add_parser(name, help=command.help)

    def run(self, argv: Sequence[str] | None = None) -> int:
        try:
            arguments = self._parser.parse_args(argv)
        except SystemExit as exit_request:
            return exit_request.code if isinstance(exit_request.code, int) else 0
        if arguments.command is None:
            self._parser.print_help()
            return 0
        try:
            asyncio.run(self._commands[arguments.command].run())
        except CommandError as error:
            print(f"{self._parser.prog} {arguments.command}: {error}", file=sys.stderr)
            return 1
        return 0


def main() -> None:
    settings = Settings()
    commands: dict[str, Command] = {"migrate": MigrateCommand(settings.clickhouse)}
    cli = Cli(PackageVersionProvider(), settings, commands)
    raise SystemExit(cli.run())
