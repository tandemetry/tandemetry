import json
from pathlib import Path

from tandemetry.ingest.github.mapper import WEBHOOK_MODELS

MANIFEST = Path(__file__).parents[2] / "deploy" / "github-app" / "manifest.json"


def test_app_only_reads() -> None:
    permissions = json.loads(MANIFEST.read_text())["default_permissions"]
    assert set(permissions.values()) == {"read"}


def test_app_subscribes_to_exactly_the_events_we_normalize() -> None:
    assert set(json.loads(MANIFEST.read_text())["default_events"]) == set(WEBHOOK_MODELS)
