"""One-time authorization derived from a literal user command (spec section 5.2).

A candidate is inert until the user types a command naming it and its displayed
hash prefix. That typing is observed by the ``UserPromptExpansion`` hook, which
is the only path that creates a record here.

The distinction this module exists to enforce: Claude invoking the same skill
through the ``Skill`` tool produces no ``UserPromptExpansion`` event, so it
cannot authorize anything. Neither can a generic "looks good" in conversation.
"""

import time
import uuid

from . import config, store

APPLY = "apply"
REJECT = "reject"
ROLLBACK = "rollback"
OPERATIONS = (APPLY, REJECT, ROLLBACK)

SLASH_COMMAND = "slash_command"
PLUGIN_SOURCE = "plugin"


class AuthorizationError(Exception):
    """Raised with a bounded reason category."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def operation_from_command_name(command_name):
    """Map a command name to one of our operations, or ``None``.

    Accepts both the bare and namespaced spellings because the exact form Claude
    Code reports for a plugin skill is not guaranteed across versions. Matching
    in code rather than in a hook matcher is what keeps a version difference
    from silently discarding the user's authorization.
    """
    if not command_name or not isinstance(command_name, str):
        return None
    name = command_name.strip().lower()
    if ":" in name:
        prefix, _, tail = name.rpartition(":")
        if prefix not in ("self-improve", "self_improve", ""):
            return None
        name = tail
    name = name.lstrip("/")
    return name if name in OPERATIONS else None


def parse_arguments(operation, command_args):
    """Extract the identifiers a command carries.

    ``apply`` needs a proposal and a hash prefix; ``reject`` a proposal;
    ``rollback`` a mutation. Extra words are refused rather than ignored, since
    a malformed authorization should fail visibly.
    """
    tokens = (command_args or "").split()
    if operation == APPLY:
        if len(tokens) != 2:
            raise AuthorizationError("apply_needs_id_and_hash_prefix")
        return {"proposal_id": tokens[0], "hash_prefix": tokens[1].lower()}
    if operation == REJECT:
        if len(tokens) != 1:
            raise AuthorizationError("reject_needs_proposal_id")
        return {"proposal_id": tokens[0]}
    if operation == ROLLBACK:
        if len(tokens) != 1:
            raise AuthorizationError("rollback_needs_mutation_id")
        return {"mutation_id": tokens[0]}
    raise AuthorizationError("unknown_operation")


def accepts(event):
    """Whether a ``UserPromptExpansion`` event may create an authorization.

    All three conditions are required by section 5.2: the expansion came from a
    typed slash command, the command belongs to this plugin, and it names one of
    the authorizing operations.
    """
    if event.get("expansion_type") != SLASH_COMMAND:
        return None
    if event.get("command_source") != PLUGIN_SOURCE:
        return None
    return operation_from_command_name(event.get("command_name"))


def grant(event, operation, arguments):
    """Record a single-use authorization bound to this exact invocation."""
    nonce = uuid.uuid4().hex
    record = {
        "nonce": nonce,
        "operation": operation,
        "session_id": event.get("session_id"),
        "prompt_id": event.get("prompt_id"),
        "granted_at": int(time.time()),
        "consumed": False,
    }
    record.update(arguments)
    store.write_record(store.AUTHORIZATIONS, nonce, record, ttl=config.AUTHORIZATION_TTL)
    return record


def consume(operation, session_id=None, **match):
    """Find, atomically claim, and return a matching authorization.

    Claiming is a delete: the record is removed before the operation it
    authorizes begins, so a crash mid-mutation cannot leave a token that would
    authorize a second attempt. Section 9 requires exactly-once consumption, and
    losing an authorization is the safe direction to fail.
    """
    for record in store.list_records(store.AUTHORIZATIONS):
        if record.get("operation") != operation:
            continue
        if session_id and record.get("session_id") != session_id:
            continue
        if any(record.get(key) != value for key, value in match.items()):
            continue
        if not store.delete_record(store.AUTHORIZATIONS, record["nonce"]):
            # Another process claimed it first.
            continue
        return record
    raise AuthorizationError("no_matching_authorization")
