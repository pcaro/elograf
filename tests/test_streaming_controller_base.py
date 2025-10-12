"""Tests for StreamingControllerBase shared suspend/resume functionality."""

import unittest
from enum import Enum, auto

from eloGraf.base_controller import StreamingControllerBase


class TestState(Enum):
    """Test state enum for controller."""
    IDLE = auto()
    RECORDING = auto()
    SUSPENDED = auto()
    FAILED = auto()


STATE_MAP = {
    "idle": TestState.IDLE,
    "recording": TestState.RECORDING,
    "suspended": TestState.SUSPENDED,
    "failed": TestState.FAILED,
}


class TestStreamingController(StreamingControllerBase[TestState]):
    """Concrete test implementation of StreamingControllerBase."""

    def __init__(self):
        super().__init__(
            initial_state=TestState.IDLE,
            state_map=STATE_MAP,
            engine_name="TestEngine",
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


class TestStreamingControllerBase(unittest.TestCase):
    """Test suite for StreamingControllerBase."""

    def test_initial_suspended_state_is_false(self):
        """Controller should start with is_suspended = False."""
        controller = TestStreamingController()
        self.assertFalse(controller.is_suspended)

    def test_suspend_requested_sets_suspended_flag(self):
        """suspend_requested() should set _suspended to True."""
        controller = TestStreamingController()
        controller.suspend_requested()
        self.assertTrue(controller.is_suspended)

    def test_suspend_requested_transitions_to_suspended_state(self):
        """suspend_requested() should transition to 'suspended' state."""
        controller = TestStreamingController()
        states = []
        controller.add_state_listener(lambda s: states.append(s))

        controller.suspend_requested()

        self.assertEqual(controller.state, TestState.SUSPENDED)
        self.assertIn(TestState.SUSPENDED, states)

    def test_resume_requested_clears_suspended_flag(self):
        """resume_requested() should set _suspended to False."""
        controller = TestStreamingController()
        controller.suspend_requested()  # First suspend
        controller.resume_requested()    # Then resume

        self.assertFalse(controller.is_suspended)

    def test_resume_requested_transitions_to_recording_state(self):
        """resume_requested() should transition to 'recording' state."""
        controller = TestStreamingController()
        states = []
        controller.add_state_listener(lambda s: states.append(s))

        controller.suspend_requested()  # First suspend
        controller.resume_requested()    # Then resume

        self.assertEqual(controller.state, TestState.RECORDING)
        self.assertIn(TestState.RECORDING, states)

    def test_suspend_resume_cycle(self):
        """Multiple suspend/resume cycles should work correctly."""
        controller = TestStreamingController()

        # First cycle
        controller.suspend_requested()
        self.assertTrue(controller.is_suspended)
        self.assertEqual(controller.state, TestState.SUSPENDED)

        controller.resume_requested()
        self.assertFalse(controller.is_suspended)
        self.assertEqual(controller.state, TestState.RECORDING)

        # Second cycle
        controller.suspend_requested()
        self.assertTrue(controller.is_suspended)
        self.assertEqual(controller.state, TestState.SUSPENDED)

        controller.resume_requested()
        self.assertFalse(controller.is_suspended)
        self.assertEqual(controller.state, TestState.RECORDING)


if __name__ == "__main__":
    unittest.main()
