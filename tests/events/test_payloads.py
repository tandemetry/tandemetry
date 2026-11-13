from typing import Any

import pytest
from pydantic import ValidationError

from tandemetry.events.payloads import CheckConclusion, CheckRun, FileChange, Revert

SHA = "a" * 40


@pytest.mark.parametrize(
    "target",
    [
        {"reverted_shas": (SHA,), "reverted_pull_request": None},
        {"reverted_shas": (), "reverted_pull_request": 7},
    ],
    ids=["commits", "pull-request"],
)
def test_revert_with_a_target_is_accepted(target: dict[str, Any]) -> None:
    assert Revert(sha=SHA, **target).sha == SHA


def test_revert_requires_a_target() -> None:
    with pytest.raises(ValidationError, match="must name"):
        Revert(sha=SHA, reverted_shas=(), reverted_pull_request=None)


@pytest.mark.parametrize("sha", ["a" * 39, "A" * 40, "g" * 40], ids=["short", "upper", "non-hex"])
def test_malformed_sha_is_rejected(sha: str) -> None:
    with pytest.raises(ValidationError):
        CheckRun(check_run_id=1, name="ci", head_sha=sha, conclusion=CheckConclusion.SUCCESS)


def test_unknown_conclusion_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CheckRun.model_validate(
            {"check_run_id": 1, "name": "ci", "head_sha": SHA, "conclusion": "exploded"}
        )


def test_negative_line_counts_are_rejected() -> None:
    with pytest.raises(ValidationError):
        FileChange(path="a.py", additions=-1, deletions=0)
