"""Reading hook input and emitting hook output.

One place parses the JSON Claude Code sends on standard input, and one place
formats what goes back, so no individual subcommand has to remember the
protocol or the fail-open rule.
"""

import json
import sys


def read_event(stream=None):
    """Parse the hook payload from standard input.

    Returns an empty mapping when input is absent or malformed. A subcommand
    invoked by hand, with no piped payload, is a normal case rather than an
    error.
    """
    stream = stream if stream is not None else sys.stdin
    try:
        raw = stream.read()
    except (OSError, ValueError):
        return {}
    if not raw or not raw.strip():
        return {}
    try:
        event = json.loads(raw)
    except ValueError:
        return {}
    return event if isinstance(event, dict) else {}


def additional_context(event_name, text, out=None):
    """Emit context for Claude alongside the current turn.

    ``additionalContext`` is injected as a system reminder rather than a visible
    transcript entry, which is what the capture hooks want: they should be
    invisible unless they have something to say.
    """
    payload = {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": text,
        }
    }
    json.dump(payload, out if out is not None else sys.stdout)
    return payload


def wake(message, err=None):
    """Wake an idle session from an ``asyncRewake`` hook.

    The documented contract is exit code 2 with the message on stderr, which
    Claude Code shows to Claude as a system reminder. The caller is responsible
    for exiting 2; this only writes the message.
    """
    stream = err if err is not None else sys.stderr
    stream.write(message if message.endswith("\n") else message + "\n")
    return 2
