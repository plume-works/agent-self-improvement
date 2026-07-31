"""A fake interactive session, for debugging the harness rather than the plugin.

The pty harness types blind: it never reads the screen to decide anything, so
when a live check stalls there are two very different explanations and no way to
tell them apart from the trace alone. Either the session under test did not do
what was asked, or the harness never delivered the input in the first place —
wrong line ending, a turn that swallowed the next prompt, a dialog nobody
answered.

This program answers the second question on its own. It behaves like an
interactive program on a terminal and nothing else: it draws a banner, echoes
every line it captures with a visible marker, redraws for a moment so the
quiescence detector has something to detect, and exits on ``/exit``. Drive it
with the same script that drives a real session and every step of the harness —
line endings, turn boundaries, the on-screen match, clean exit — is exercised
with no model, no cost, and no interface that can change underneath it.

It can also be told to emit a marker some seconds after a turn ends, with
nothing typed, which is the shape of the wake itself.

Usage::

    python -m tests.smoke.echo_terminal [--wake-after SECONDS] [--wake-text TEXT]
"""

import argparse
import sys
import threading
import time

BANNER = "echo-terminal ready"
PROMPT = "> "

# Long enough for the harness's quiescence detector to see output arriving and
# then stopping, short enough that a scripted exchange stays quick. A turn that
# emitted a single line and stopped instantly would not exercise the detector at
# all, which is the part most likely to be wrong.
REDRAW_SECONDS = 1.0
REDRAW_INTERVAL = 0.1


def emit(text):
    sys.stdout.write(text)
    sys.stdout.flush()


def redraw(index):
    """Imitate a terminal program working: repeated output, then silence."""
    finish = time.time() + REDRAW_SECONDS
    frames = "|/-\\"
    step = 0
    while time.time() < finish:
        emit("\r\x1b[2K%s working on turn %d " % (frames[step % 4], index))
        step += 1
        time.sleep(REDRAW_INTERVAL)
    emit("\r\x1b[2K")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wake-after", type=float, default=None,
                        help="seconds after the first turn to emit --wake-text "
                             "with nothing typed, imitating an async wake")
    parser.add_argument("--wake-text", default="self-improve: candidate cand-echo",
                        help="what the imitated wake writes to the terminal")
    options = parser.parse_args(argv)

    emit(BANNER + "\r\n" + PROMPT)
    turn = 0
    woken = threading.Event()

    while True:
        # readline rather than iteration: iterating a text stream may read ahead
        # for a whole buffer, and on a terminal that means the echo appears only
        # after the next line arrives — exactly the confusion this exists to end.
        line = sys.stdin.readline()
        if not line:
            return 0
        captured = line.rstrip("\r\n")
        turn += 1
        # The echo is the point: it is proof the bytes the harness wrote were
        # received as one line, at the moment they were received.
        emit("captured[%d]: %s\r\n" % (turn, captured))
        if captured.strip() in ("/exit", "/quit"):
            emit("bye\r\n")
            return 0
        redraw(turn)
        emit("done[%d]\r\n%s" % (turn, PROMPT))

        if options.wake_after is not None and not woken.is_set():
            woken.set()
            # A daemon thread, so an exit while the wake is pending is still an
            # exit — the harness asserts on the status and must not be made to
            # wait for this.
            waking = threading.Thread(
                target=_wake_later, args=(options.wake_after, options.wake_text),
                daemon=True)
            waking.start()


def _wake_later(delay, text):
    time.sleep(delay)
    emit("\r\n%s\r\n%s" % (text, PROMPT))


if __name__ == "__main__":
    sys.exit(main())
