import pytest

from tandemetry.settings import Settings


def test_app_name_defaults_to_tandemetry() -> None:
    assert Settings().app_name == "tandemetry"


def test_app_name_can_be_overridden_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TANDEMETRY_APP_NAME", "custom")
    assert Settings().app_name == "custom"
