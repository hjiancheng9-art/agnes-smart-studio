"""Test: _log_activity posts ActivityLogged event instead of direct state mutation.

OBSOLETE — event queue architecture removed in v3 game-console refactor.
The invariant is now enforced by tests/test_v3_architecture.py.
"""

import pytest


@pytest.mark.skip(reason="Event queue removed — invariant enforced by test_v3_architecture.py")
class TestLogActivityPostsEvent:
    def test_log_activity_should_post_event_not_mutate_state(self):
        pass
