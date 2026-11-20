import pytest

from tandemetry.events.envelope import Event
from tandemetry.events.sample import SAMPLE_EVENT


@pytest.fixture
def event() -> Event:
    return SAMPLE_EVENT
