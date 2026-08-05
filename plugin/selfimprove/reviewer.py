"""The isolated review call (spec section 7).

The reviewer runs as a separate Claude process with a reviewer-only system
prompt, hooks disabled, and no tools at all. It receives its entire evidence
bundle on standard input, so it has nothing to read, write, or execute with:
stronger than a read-only allowlist, and simpler to reason about.

Every failure path here is silent by design (spec section 11). A review that
times out, fails to authenticate, or returns nonsense records an error class and
produces no candidate.
"""

import json
import os
import re
import subprocess

from . import config, journal, schema

# HTTP statuses the CLI reports as ``api_error_status``. Naming these separately
# from a generic failure is what makes a smoke run diagnosable: a review that
# never happened because the provider was busy is a transient condition, not the
# reviewer declining to propose anything.
_STATUS_CLASSES = {
    401: "unauthenticated",
    403: "unauthenticated",
    429: "rate_limited",
    500: "provider_error",
    502: "provider_error",
    503: "overloaded",
    529: "overloaded",
}

# Phrases, most specific first, for the failures that arrive as text rather than
# as a status. Bare status numbers are deliberately absent: they collide with the
# durations and token counts in the same envelope.
_PHRASE_CLASSES = [
    ("usage_limited", re.compile(r"(?i)credit|quota|usage limit")),
    ("rate_limited", re.compile(r"(?i)rate[ _-]?limit|too many requests")),
    ("overloaded", re.compile(r"(?i)overloaded|service unavailable")),
    ("model_unavailable", re.compile(
        r"(?i)(unknown|invalid|unsupported) model|model_not_found|"
        r"model .{0,40}(does not exist|may not exist|access to it)")),
    ("unauthenticated", re.compile(r"(?i)auth|login|api key")),
    ("provider_error", re.compile(
        r"(?i)internal server error|bad gateway|api error")),
]


class ReviewUnavailable(Exception):
    """The reviewer could not be consulted. Carries a bounded reason class."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def build_command(prompt_path, model=None):
    """The exact argument vector committed in spec section 7.3.

    ``--tools ""`` removes every built-in tool and ``--disallowedTools "*"``
    removes MCP tools, so the reviewer holds no capability to act. Hooks are
    disabled so this plugin's own Stop hook cannot fire inside the review.
    """
    return [
        config.reviewer_command(),
        "-p",
        "--model", model or config.review_model(),
        "--system-prompt-file", prompt_path,
        "--tools", "",
        "--disallowedTools", "*",
        "--strict-mcp-config",
        "--settings", json.dumps({"disableAllHooks": True}),
        "--output-format", "json",
        "--max-turns", "1",
    ]


def build_environment():
    """The reviewer's environment.

    ``SELF_IMPROVE_REVIEWER`` marks the child so that any session it originates
    suppresses reflection, which is the recursion guard of section 5.5. The
    state directory override is removed so a reviewer cannot be pointed at, or
    write to, the state it is being asked to reason about.

    Effort is set here rather than as a ``--effort`` flag on purpose. Review
    failure is silent by design: a candidate simply never appears. A CLI too old
    to know the flag would abort on an unknown option and take every review with
    it, with nothing on screen to say why; an environment variable it does not
    know is ignored and the review still happens, at the default level. Losing
    the saving is the acceptable failure here, losing the review is not.
    """
    environment = dict(os.environ)
    environment["SELF_IMPROVE_REVIEWER"] = "1"
    effort = config.review_effort()
    if effort:
        environment["CLAUDE_CODE_EFFORT_LEVEL"] = effort
    else:
        # An empty setting asks for the CLI's own default, so an effort level
        # inherited from the session that launched us has to go with it.
        environment.pop("CLAUDE_CODE_EFFORT_LEVEL", None)
    environment.pop("SELF_IMPROVE_STATE_DIR", None)
    environment.pop("CLAUDE_PLUGIN_DATA", None)
    return environment


def prompt_path():
    from . import paths
    return os.path.join(paths.plugin_root(), "reviewer", "prompt.md")


def invoke(bundle, timeout=None, model=None):
    """Run the reviewer over ``bundle`` and return its raw text response."""
    path = prompt_path()
    if not os.path.exists(path):
        raise ReviewUnavailable("missing_prompt")

    command = build_command(path, model=model)
    payload = json.dumps(bundle, sort_keys=True, indent=2)
    try:
        result = subprocess.run(
            command,
            input=payload,
            capture_output=True,
            text=True,
            env=build_environment(),
            timeout=timeout or config.review_timeout(),
        )
    except subprocess.TimeoutExpired as exc:
        raise ReviewUnavailable("timeout") from exc
    except FileNotFoundError as exc:
        raise ReviewUnavailable("cli_not_found") from exc
    except OSError as exc:
        raise ReviewUnavailable("spawn_failed") from exc

    if result.returncode != 0:
        raise ReviewUnavailable(_failure_class(result))
    return _response_text(result.stdout)


def _failure_class(result):
    """Classify a non-zero reviewer exit without keeping its output."""
    from . import redact

    combined = "%s\n%s" % (result.stderr or "", result.stdout or "")
    status = _api_error_status(result.stdout)
    if status in _STATUS_CLASSES:
        return _STATUS_CLASSES[status]
    return _phrase_class(combined) or redact.error_class(combined)


def _phrase_class(text):
    """The failure class implied by ``text``, or None if nothing matches."""
    for name, pattern in _PHRASE_CLASSES:
        if pattern.search(text or ""):
            return name
    return None


def _api_error_status(stdout):
    """The CLI's ``api_error_status``, when the envelope carries one."""
    try:
        envelope = json.loads(stdout or "")
    except ValueError:
        return None
    if not isinstance(envelope, dict):
        return None
    status = envelope.get("api_error_status")
    return status if isinstance(status, int) else None


def _response_text(stdout):
    """Pull the assistant's text out of the ``--output-format json`` envelope."""
    if not stdout or not stdout.strip():
        raise ReviewUnavailable("empty_output")
    try:
        envelope = json.loads(stdout)
    except ValueError:
        # An older or differently configured CLI may print bare text. The schema
        # layer is what decides whether the content is usable.
        return stdout
    if isinstance(envelope, dict):
        if envelope.get("is_error") or envelope.get("terminal_reason") == "api_error":
            # A provider error can arrive with a zero exit status: the CLI ran
            # fine, the call inside it did not. Classify it the same way.
            raise ReviewUnavailable(_envelope_failure_class(envelope))
        for key in ("result", "text", "content"):
            value = envelope.get(key)
            if isinstance(value, str):
                return value
    raise ReviewUnavailable("unrecognized_envelope")


def _envelope_failure_class(envelope):
    """Classify a failed review the CLI reported inside its own envelope."""
    status = envelope.get("api_error_status")
    if isinstance(status, int) and status in _STATUS_CLASSES:
        return _STATUS_CLASSES[status]
    text = envelope.get("result")
    return _phrase_class(text if isinstance(text, str) else "") or "reviewer_error"


def review(bundle, timeout=None, model=None):
    """Consult the reviewer and return a validated result.

    Returns a ``discard`` result rather than raising for every failure mode, so
    callers have exactly one shape to handle. The reason is recorded as a class
    in the diagnostics journal.
    """
    try:
        text = invoke(bundle, timeout=timeout, model=model)
    except ReviewUnavailable as exc:
        journal.diagnostic("reviewer", exc.reason)
        return {"decision": schema.DISCARD, "discard_reason": exc.reason}

    try:
        payload = schema.extract_json(text)
        return schema.validate(payload)
    except schema.SchemaError as exc:
        journal.diagnostic("reviewer_schema", exc.reason)
        return {"decision": schema.DISCARD, "discard_reason": exc.reason}
