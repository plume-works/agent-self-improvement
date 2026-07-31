"""Tunable limits and the environment surface.

The defaults implement the bounds spec section 6 requires: one reviewer
invocation per completed turn, a cooldown between invocations, and a daily cap.
"""

import os

# Reviewer.
DEFAULT_REVIEW_MODEL = "sonnet"
REVIEW_TIMEOUT_SECONDS = 120

# Gate limits (spec section 6).
COOLDOWN_SECONDS = 120
DAILY_REVIEW_LIMIT = 20
REPEATED_FRICTION_THRESHOLD = 3

# Lifetimes in seconds (spec section 10.1).
TURN_TTL = 60 * 60
CANDIDATE_TTL = 24 * 60 * 60
PROPOSAL_TTL = 24 * 60 * 60
AUTHORIZATION_TTL = 10 * 60

# Presentation.
HASH_PREFIX_LENGTH = 12

# Redaction bounds (spec section 10).
MAX_FIELD_LENGTH = 200
MAX_EVENTS_PER_TURN = 200


def review_model():
    return os.environ.get("SELF_IMPROVE_REVIEW_MODEL") or DEFAULT_REVIEW_MODEL


def review_timeout():
    """Seconds to wait for the reviewer before giving up silently."""
    raw = os.environ.get("SELF_IMPROVE_REVIEW_TIMEOUT")
    if raw:
        try:
            value = float(raw)
        except ValueError:
            return REVIEW_TIMEOUT_SECONDS
        if value > 0:
            return value
    return REVIEW_TIMEOUT_SECONDS


def reviewer_command():
    """The binary used for the isolated review call.

    Tests override this to substitute a deterministic fake reviewer.
    """
    return os.environ.get("SELF_IMPROVE_REVIEWER_CMD") or "claude"


def in_reviewer_session():
    """True inside a session the reviewer itself originated.

    This is the recursion guard required by spec section 5.5 step 4.
    """
    return os.environ.get("SELF_IMPROVE_REVIEWER") == "1"


def disabled():
    """Allow a user to turn the plugin off without uninstalling it."""
    return os.environ.get("SELF_IMPROVE_DISABLE") == "1"
