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
import subprocess

from . import config, journal, schema


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
    """
    environment = dict(os.environ)
    environment["SELF_IMPROVE_REVIEWER"] = "1"
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
            timeout=timeout or config.REVIEW_TIMEOUT_SECONDS,
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
    lowered = combined.lower()
    if "credit" in lowered or "quota" in lowered or "usage limit" in lowered:
        return "usage_limited"
    if "auth" in lowered or "login" in lowered or "api key" in lowered:
        return "unauthenticated"
    return redact.error_class(combined)


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
        if envelope.get("is_error"):
            raise ReviewUnavailable("reviewer_error")
        for key in ("result", "text", "content"):
            value = envelope.get(key)
            if isinstance(value, str):
                return value
    raise ReviewUnavailable("unrecognized_envelope")


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
