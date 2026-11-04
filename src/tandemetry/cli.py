import argparse
from collections.abc import Sequence
from importlib.metadata import version
from typing import Protocol

from tandemetry.settings import Settings


class VersionProvider(Protocol):
    def get(self) -> str: ...


class PackageVersionProvider:
    def __init__(self, package: str = "tandemetry") -> None:
        self._package = package

    def get(self) -> str:
        return version(self._package)


class Cli:
    def __init__(self, version_provider: VersionProvider, settings: Settings) -> None:
        self._parser = argparse.ArgumentParser(prog=settings.app_name)
        self._parser.add_argument(
            "--version",
            action="version",
            version=f"{settings.app_name} {version_provider.get()}",
        )

    def run(self, argv: Sequence[str] | None = None) -> int:
        try:
            self._parser.parse_args(argv)
        except SystemExit as exit_request:
            return exit_request.code if isinstance(exit_request.code, int) else 0
        return 0


def main() -> None:
    cli = Cli(PackageVersionProvider(), Settings())
    raise SystemExit(cli.run())
