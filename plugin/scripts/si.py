#!/usr/bin/env python3
"""Dispatcher for every hook and skill invocation.

One entry point means one place that parses hook input and one place that
enforces the fail-open rule of spec section 11: a capture or gating failure must
never disturb the completed task, so an unexpected exception is recorded as a
bounded error class and the process still exits 0.
"""

import argparse
import contextlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from selfimprove import commands, config, journal, redact

# Subcommands whose failure must never surface to the user. Everything here runs
# from a lifecycle hook during, or immediately after, the user's real work.
FAIL_OPEN = {
    "capture-prompt",
    "capture-expansion",
    "capture-tool-failure",
    "capture-tool-success",
    "review-turn",
    "session-start",
    "session-end",
}


def build_parser():
    parser = argparse.ArgumentParser(
        prog="si",
        description="Self-improve plugin dispatcher.",
    )
    parser.add_argument("subcommand", choices=sorted(commands.HANDLERS))
    parser.add_argument("args", nargs=argparse.REMAINDER)
    return parser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        build_parser().print_help()
        return 0

    subcommand = argv[0]
    handler = commands.HANDLERS.get(subcommand)
    if handler is None:
        build_parser().parse_args(argv)
        return 2

    if config.disabled():
        return 0

    try:
        return handler(argv[1:]) or 0
    except SystemExit:
        raise
    except BaseException as exc:
        # Deliberate catch-all: recording why is worth more than propagating.
        with contextlib.suppress(Exception):
            journal.diagnostic(subcommand, redact.error_class(str(exc)),
                               exception=type(exc).__name__)
        if subcommand in FAIL_OPEN:
            return 0
        sys.stderr.write("self-improve: %s failed (%s)\n"
                         % (subcommand, type(exc).__name__))
        return 1


if __name__ == "__main__":
    sys.exit(main())
