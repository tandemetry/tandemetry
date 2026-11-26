from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).parents[2]
COMPOSE = ROOT / "deploy" / "docker-compose.yml"
INFRASTRUCTURE = {"kafka", "kafka-init", "clickhouse", "postgres"}
APPLICATION = {"migrate", "serve", "normalize", "consume"}
GITHUB_CLIENTS = {"serve", "normalize"}


def services() -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, dict[str, Any]]] = yaml.safe_load(COMPOSE.read_text())
    return loaded["services"]


def test_plain_up_starts_only_infrastructure() -> None:
    without_profile = {name for name, spec in services().items() if "profiles" not in spec}
    assert without_profile == INFRASTRUCTURE
    assert all(services()[name]["profiles"] == ["app"] for name in APPLICATION)


def test_published_ports_bind_localhost() -> None:
    ports = [port for spec in services().values() for port in spec.get("ports", [])]
    assert ports
    assert all(port.startswith("127.0.0.1:") for port in ports)


def test_github_secrets_come_only_from_the_env_file() -> None:
    for name, spec in services().items():
        assert not any(key.startswith("TANDEMETRY_GITHUB__") for key in spec.get("environment", {}))
        env_files = [entry["path"] for entry in spec.get("env_file", [])]
        assert env_files == (["app.env"] if name in GITHUB_CLIENTS else [])


def test_consume_waits_for_the_schema() -> None:
    assert services()["consume"]["depends_on"]["migrate"]["condition"] == (
        "service_completed_successfully"
    )
    assert services()["migrate"]["depends_on"]["clickhouse"]["condition"] == "service_healthy"


def test_build_context_excludes_secrets_and_local_state() -> None:
    ignored = set((ROOT / ".dockerignore").read_text().split())
    assert {".git", ".venv", "**/*.env", "**/*.pem"} <= ignored
