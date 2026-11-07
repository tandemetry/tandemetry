from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

DEFAULT_CATALOG_PATH = Path(__file__).with_name("signatures.yaml")


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"


class SignalKind(StrEnum):
    BOT_ACCOUNT = "bot_account"
    COMMIT_TRAILER = "commit_trailer"
    DESCRIPTION_PHRASE = "description_phrase"
    BRANCH_PREFIX = "branch_prefix"
    LABEL = "label"


RULE_CONFIDENCE: Mapping[SignalKind, Confidence] = {
    SignalKind.BOT_ACCOUNT: Confidence.HIGH,
    SignalKind.COMMIT_TRAILER: Confidence.HIGH,
    SignalKind.DESCRIPTION_PHRASE: Confidence.MEDIUM,
    SignalKind.BRANCH_PREFIX: Confidence.MEDIUM,
    SignalKind.LABEL: Confidence.MEDIUM,
}


class CatalogError(Exception):
    """Raised when a signatures catalog cannot be read or is invalid."""


class Signal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: SignalKind
    value: str = Field(min_length=1)
    confidence: Confidence

    @model_validator(mode="after")
    def _confidence_follows_rules_table(self) -> Self:
        expected = RULE_CONFIDENCE[self.kind]
        if self.confidence != expected:
            raise ValueError(f"{self.kind} signals must have {expected} confidence")
        return self


class AgentSignature(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    signals: tuple[Signal, ...] = Field(min_length=1)


class SignatureCatalog(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    agents: tuple[AgentSignature, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _agent_names_are_unique(self) -> Self:
        names = [agent.name for agent in self.agents]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate agent names: {', '.join(duplicates)}")
        return self


class SignatureCatalogLoader:
    """Loads and validates a signatures catalog from a YAML file."""

    def __init__(self, path: Path = DEFAULT_CATALOG_PATH) -> None:
        self._path = path

    def load(self) -> SignatureCatalog:
        try:
            raw = yaml.safe_load(self._path.read_text(encoding="utf-8"))
            return SignatureCatalog.model_validate(raw)
        except (OSError, yaml.YAMLError, ValidationError) as error:
            raise CatalogError(f"invalid signatures catalog {self._path}: {error}") from error
