# ABOUTME: Tests that ensure each engine controller reports a status string.
# ABOUTME: Verifies tooltip refactor by calling get_status_string() on factory-created controllers.

from __future__ import annotations

from typing import List

import pytest

from eloGraf.stt_factory import create_stt_engine


STATUS_CASES: List = [
    ("whisper-docker", {}, ["Whisper Docker", "Model:", "Lang:"]),
    ("google-cloud-speech", {}, ["Google Cloud", "Model:", "Lang:"]),
    ("openai-realtime", {"api_key": "sk-test"}, ["OpenAI Realtime", "Model:", "Lang:"]),
]


@pytest.mark.parametrize("engine_id, extra_kwargs, expected_tokens", STATUS_CASES)
def test_controller_status_strings(
    engine_id: str, extra_kwargs: dict, expected_tokens: List[str]
):
    """Ensure controllers expose a meaningful status string for tooltip usage."""
    controller, _ = create_stt_engine(engine_id, **extra_kwargs)
    status = controller.get_status_string()

    assert isinstance(status, str)
    assert status.strip()
    for token in expected_tokens:
        assert token in status
