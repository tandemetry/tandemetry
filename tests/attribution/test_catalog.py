from pathlib import Path

import pytest

from tandemetry.attribution.catalog import (
    RULE_CONFIDENCE,
    CatalogError,
    SignalKind,
    SignatureCatalog,
    SignatureCatalogLoader,
)

REQUIRED_AGENTS = {"Claude Code", "GitHub Copilot coding agent", "Devin", "Cursor", "OpenAI Codex"}
VALID_ENTRY = """
agents:
  - name: Agent
    signals:
      - {kind: bot_account, value: "agent[bot]", confidence: high}
"""


def load(tmp_path: Path, content: str) -> SignatureCatalog:
    path = tmp_path / "signatures.yaml"
    path.write_text(content, encoding="utf-8")
    return SignatureCatalogLoader(path).load()


def test_packaged_catalog_covers_required_agents() -> None:
    catalog = SignatureCatalogLoader().load()

    assert {agent.name for agent in catalog.agents} >= REQUIRED_AGENTS


def test_packaged_catalog_confidence_follows_rules_table() -> None:
    catalog = SignatureCatalogLoader().load()

    signals = [signal for agent in catalog.agents for signal in agent.signals]
    assert all(signal.confidence == RULE_CONFIDENCE[signal.kind] for signal in signals)


def test_valid_catalog_is_loaded(tmp_path: Path) -> None:
    catalog = load(tmp_path, VALID_ENTRY)

    assert catalog.agents[0].signals[0].kind is SignalKind.BOT_ACCOUNT


@pytest.mark.parametrize(
    "content",
    [
        "agents: [unclosed",
        "agents: []",
        "agents:\n  - name: Agent\n    signals: []",
        "agents:\n  - signals:\n      - {kind: label, value: ai, confidence: medium}",
        VALID_ENTRY + "    extra: nope\n",
        VALID_ENTRY.replace("bot_account", "unknown_kind"),
        VALID_ENTRY.replace("confidence: high", "confidence: certain"),
        VALID_ENTRY.replace("confidence: high", "confidence: medium"),
        VALID_ENTRY + VALID_ENTRY.split("agents:\n")[1],
    ],
    ids=[
        "broken-yaml",
        "no-agents",
        "no-signals",
        "missing-name",
        "unknown-field",
        "unknown-kind",
        "unknown-confidence",
        "confidence-contradicts-rules",
        "duplicate-agent",
    ],
)
def test_invalid_catalog_is_rejected(tmp_path: Path, content: str) -> None:
    with pytest.raises(CatalogError):
        load(tmp_path, content)


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CatalogError):
        SignatureCatalogLoader(tmp_path / "absent.yaml").load()
