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
    monkeypatch.setenv("TANDEMETRY_KAFKA__CONSUMER_GROUP", "custom-group")
    monkeypatch.setenv("TANDEMETRY_KAFKA__MAX_BATCH_RECORDS", "50")
    monkeypatch.setenv("TANDEMETRY_KAFKA__POLL_TIMEOUT_MS", "250")
    kafka = Settings().kafka
    assert kafka.bootstrap_servers == "kafka:9092"
    assert kafka.events_topic == "custom.events"
    assert kafka.consumer_group == "custom-group"
    assert kafka.max_batch_records == 50
    assert kafka.poll_timeout_ms == 250


def test_github_and_api_settings_are_read_from_nested_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TANDEMETRY_GITHUB__WEBHOOK_SECRET", "hook-key")
    monkeypatch.setenv("TANDEMETRY_GITHUB__CLIENT_ID", "Iv1.client")
    monkeypatch.setenv("TANDEMETRY_GITHUB__PRIVATE_KEY", "-----BEGIN PRIVATE KEY-----\nabc")
    monkeypatch.setenv("TANDEMETRY_API__PORT", "9000")
    settings = Settings()
    assert settings.github.webhook_secret.get_secret_value() == "hook-key"
    assert settings.github.client_id == "Iv1.client"
    assert settings.github.private_key.get_secret_value().endswith("\nabc")
    assert settings.api.port == 9000
    assert "hook-key" not in repr(settings.github)
    assert "abc" not in repr(settings.github)
