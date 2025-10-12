"""Tests for StreamingControllerBase shared suspend/resume functionality."""

import unittest
from enum import Enum, auto

from eloGraf.base_controller import StreamingControllerBase


class SampleState(Enum):
    """Sample state enum for controller testing."""
    IDLE = auto()
    RECORDING = auto()
    SUSPENDED = auto()
    FAILED = auto()


STATE_MAP = {
    "idle": SampleState.IDLE,
    "recording": SampleState.RECORDING,
    "suspended": SampleState.SUSPENDED,
    "failed": SampleState.FAILED,
}


class SampleStreamingController(StreamingControllerBase[SampleState]):
    """Concrete sample implementation of StreamingControllerBase for testing."""

    def __init__(self):
        super().__init__(
            initial_state=SampleState.IDLE,
            state_map=STATE_MAP,
            engine_name="SampleEngine",
        )
        self._stop_requested = False

    def start(self) -> None:
        """Start the test controller."""
        self._stop_requested = False
        self.transition_to("idle")

    def stop_requested(self) -> None:
        """Signal stop requested."""
        self._stop_requested = True

    def handle_output(self, line: str) -> None:
        """Handle output line."""
        self._emit_output(line)

    def handle_exit(self, return_code: int) -> None:
        """Handle process exit."""
        if return_code == 0:
            self.transition_to("idle")
        else:
            self.transition_to("failed")
        self._emit_exit(return_code)

    def get_status_string(self) -> str:
        return "SampleEngine | Test"


class TestStreamingControllerBase(unittest.TestCase):
    """Test suite for StreamingControllerBase."""

    def test_initial_suspended_state_is_false(self):
        """Controller should start with is_suspended = False."""
        controller = SampleStreamingController()
        self.assertFalse(controller.is_suspended)

    def test_suspend_requested_sets_suspended_flag(self):
        """suspend_requested() should set _suspended to True."""
        controller = SampleStreamingController()
        controller.suspend_requested()
        self.assertTrue(controller.is_suspended)

    def test_suspend_requested_transitions_to_suspended_state(self):
        """suspend_requested() should transition to 'suspended' state."""
        controller = SampleStreamingController()
        states = []
        controller.add_state_listener(lambda s: states.append(s))

        controller.suspend_requested()

        self.assertEqual(controller.state, SampleState.SUSPENDED)
        self.assertIn(SampleState.SUSPENDED, states)

    def test_resume_requested_clears_suspended_flag(self):
        """resume_requested() should set _suspended to False."""
        controller = SampleStreamingController()
        controller.suspend_requested()  # First suspend
        controller.resume_requested()    # Then resume

        self.assertFalse(controller.is_suspended)

    def test_resume_requested_transitions_to_recording_state(self):
        """resume_requested() should transition to 'recording' state."""
        controller = SampleStreamingController()
        states = []
        controller.add_state_listener(lambda s: states.append(s))

        controller.suspend_requested()  # First suspend
        controller.resume_requested()    # Then resume

        self.assertEqual(controller.state, SampleState.RECORDING)
        self.assertIn(SampleState.RECORDING, states)

    def test_suspend_resume_cycle(self):
        """Multiple suspend/resume cycles should work correctly."""
        controller = SampleStreamingController()

        # First cycle
        controller.suspend_requested()
        self.assertTrue(controller.is_suspended)
        self.assertEqual(controller.state, SampleState.SUSPENDED)

        controller.resume_requested()
        self.assertFalse(controller.is_suspended)
        self.assertEqual(controller.state, SampleState.RECORDING)

        # Second cycle
        controller.suspend_requested()
        self.assertTrue(controller.is_suspended)
        self.assertEqual(controller.state, SampleState.SUSPENDED)

        controller.resume_requested()
        self.assertFalse(controller.is_suspended)
        self.assertEqual(controller.state, SampleState.RECORDING)


if __name__ == "__main__":
    unittest.main()
