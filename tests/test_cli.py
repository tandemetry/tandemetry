import pytest

from tandemetry.cli import Cli, PackageVersionProvider
from tandemetry.settings import Settings


class FakeVersionProvider:
    def get(self) -> str:
        return "9.9.9"


@pytest.fixture
def cli() -> Cli:
    return Cli(FakeVersionProvider(), Settings())


def test_version_flag_prints_name_and_version(cli: Cli, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.run(["--version"]) == 0
    assert capsys.readouterr().out.strip() == "tandemetry 9.9.9"


def test_unknown_flag_returns_non_zero(cli: Cli) -> None:
    assert cli.run(["--unknown"]) != 0


def test_package_version_provider_reads_installed_metadata() -> None:
    assert PackageVersionProvider().get()
