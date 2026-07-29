"""Subcommand implementations.

The dispatcher owns argument routing and the fail-open rule; each function here
owns one operation. Handlers are registered in :data:`HANDLERS` as they are
implemented, so an unimplemented subcommand is a parser error rather than a stub
that silently succeeds.
"""

import contextlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys

from . import config, hookio, paths, store


def session_end(argv):
    """Expire ephemeral state (spec section 5.6).

    Deliberately does no model work: the session is already terminating, and
    Claude Code gives ``SessionEnd`` hooks a shared budget of about 1.5 seconds.
    """
    hookio.read_event()
    store.sweep()
    return 0


def status(argv):
    """Report live state. Used by the skills and by the smoke test."""
    root = paths.state_root()
    report = {
        "state_root": root,
        "claude_home": paths.claude_home(),
        "plugin_root": paths.plugin_root(),
        "candidates": len(store.list_records(store.CANDIDATES)),
        "proposals": len(store.list_records(store.PROPOSALS)),
        "authorizations": len(store.list_records(store.AUTHORIZATIONS)),
        "disabled": config.disabled(),
        "review_model": config.review_model(),
    }
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def self_test(argv):
    """Verify install-time invariants and report what is wrong.

    Run from the smoke test and usable by hand. Unlike the hook paths this is
    allowed to fail loudly, because a person asked it a direct question.
    """
    failures = []

    # Reachable only when scripts/si.py is run directly, bypassing the shell
    # shim that guarantees a 3.9+ interpreter. Worth reporting rather than
    # failing with an obscure syntax or attribute error further along.
    if sys.version_info < (3, 9):  # noqa: UP036
        failures.append("interpreter is %s; 3.9 or later is required"
                        % platform.python_version())

    root = paths.state_root()
    try:
        paths.ensure_dir(root)
    except OSError as exc:
        failures.append("cannot create state root %s (%s)" % (root, exc.strerror))
    else:
        mode = os.stat(root).st_mode & 0o777
        if mode != paths.DIR_MODE:
            failures.append("state root %s has mode %o, expected %o"
                            % (root, mode, paths.DIR_MODE))
        probe = os.path.join(root, ".self-test")
        try:
            paths.atomic_write(probe, b"ok")
            if os.stat(probe).st_mode & 0o777 != paths.FILE_MODE:
                failures.append("state files are not created mode 600")
        except OSError as exc:
            failures.append("state root is not writable (%s)" % exc.strerror)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(probe)

    plugin = paths.plugin_root()
    for relative in ("hooks/hooks.json", ".claude-plugin/plugin.json", "scripts/si"):
        candidate = os.path.join(plugin, relative)
        if not os.path.exists(candidate):
            failures.append("missing plugin file %s" % relative)

    hooks_json = os.path.join(plugin, "hooks", "hooks.json")
    if os.path.exists(hooks_json):
        try:
            with open(hooks_json, encoding="utf-8") as handle:
                json.load(handle)
        except ValueError as exc:
            failures.append("hooks.json is not valid JSON (%s)" % exc)

    for line in failures:
        sys.stderr.write("self-test: %s\n" % line)
    for line in cli_capability_warnings():
        sys.stderr.write("self-test: warning: %s\n" % line)
    if failures:
        return 1
    sys.stdout.write("self-test: ok (python %s, state root %s)\n"
                     % (platform.python_version(), root))
    return 0


# The floor is set by the highest documented requirement among the hook fields
# this plugin reads: prompt_id on the common input fields, which the hooks
# reference states requires v2.1.196. background_tasks and session_crons on Stop
# require v2.1.145. UserPromptExpansion carries the authorization path of spec
# section 5.2 and is absent from v2.1.81; the reference states no introduction
# version for it, so it is covered by the same floor rather than guessed at.
MINIMUM_CLI_VERSION = (2, 1, 196)

CLI_FEATURES_AT_FLOOR = (
    "UserPromptExpansion (mutation authorization), prompt_id (turn identity), "
    "and background_tasks/session_crons on Stop (skipping review while "
    "background work is in flight)"
)


def _format_version(version):
    return ".".join(str(part) for part in version)


def cli_version():
    """The installed Claude Code version as a tuple, or ``None``.

    ``None`` when the CLI is absent or does not answer, which is normal in
    tests and during offline development.
    """
    executable = shutil.which("claude")
    if not executable:
        return None
    try:
        result = subprocess.run([executable, "--version"], capture_output=True,
                                text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", result.stdout or "")
    return tuple(int(part) for part in match.groups()) if match else None


def cli_capability_warnings():
    """Report an installed CLI too old for the hook contract this plugin uses.

    A warning rather than a failure: capture and review still work, and the
    package may be validated on one machine and run on another. What stops
    working is authorization, so the message says so plainly.
    """
    version = cli_version()
    if version is None or version >= MINIMUM_CLI_VERSION:
        return []
    return [
        "Claude Code %s is older than %s. Without an upgrade, %s are "
        "unavailable, so proposals cannot be authorized or applied."
        % (_format_version(version), _format_version(MINIMUM_CLI_VERSION),
           CLI_FEATURES_AT_FLOOR)
    ]


HANDLERS = {
    "session-end": session_end,
    "status": status,
    "self-test": self_test,
}
