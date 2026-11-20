import pytest

from tandemetry.settings import Settings


def test_app_name_defaults_to_tandemetry() -> None:
    assert Settings().app_name == "tandemetry"


def test_app_name_can_be_overridden_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TANDEMETRY_APP_NAME", "custom")
    assert Settings().app_name == "custom"


def test_clickhouse_settings_are_read_from_nested_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TANDEMETRY_CLICKHOUSE__PORT", "18123")
    monkeypatch.setenv("TANDEMETRY_CLICKHOUSE__PASSWORD", "secret")
    clickhouse = Settings().clickhouse
    assert clickhouse.port == 18123
    assert clickhouse.password.get_secret_value() == "secret"
    assert "secret" not in repr(clickhouse)


def test_kafka_settings_are_read_from_nested_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TANDEMETRY_KAFKA__BOOTSTRAP_SERVERS", "kafka:9092")
    monkeypatch.setenv("TANDEMETRY_KAFKA__EVENTS_TOPIC", "custom.events")
    kafka = Settings().kafka
    assert kafka.bootstrap_servers == "kafka:9092"
    assert kafka.events_topic == "custom.events"
