"""A pseudo-terminal driver for a real interactive Claude Code session.

Spec-0002. This exists for one observation that no headless session can make:
an ``asyncRewake`` hook waking a session that is sitting idle. A ``-p`` session
finishes at ``result`` and has no idle state to wake into, so the wake has to be
watched in a terminal — either by a person, or by this.

The rules the spec sets for what may be believed here are followed strictly:

- everything that can be asserted from plugin state is asserted from plugin
  state, not from the screen;
- exactly one thing is matched on screen, the candidate identifier, which the
  plugin generates and this harness reads from disk before looking for it; and
- nothing the interface owns — prose, boxes, spinners, colors — is matched at
  all, including to decide when a turn has ended.

Turn boundaries come from quiescence rather than from recognizing a prompt:
while Claude works, the renderer emits continuously; when it stops, the stream
goes quiet. That is a property of a terminal program redrawing, not of any
particular version's layout.
"""

import contextlib
import errno
import fcntl
import os
import pty
import re
import select
import signal
import struct
import subprocess
import termios
import time

# Escape sequences, then every whitespace character, are removed before the one
# on-screen match. A 17-character candidate id is wrapped across lines whenever
# it lands near the right margin, and a match that failed for that reason would
# report a missing wake that in fact arrived.
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[]P^_].*?(?:\x1b\\|\x07)|\x1b[@-Z\\-_]",
                  re.DOTALL)
WHITESPACE = re.compile(r"\s+")

COLUMNS = 120
LINES = 40

# Anything marking this process as living inside a Claude Code session. Running
# the harness from one is the normal case — a developer debugging it is in a
# session — and inheriting these makes the child a nested session: transcript
# saving switches off, the interface reports an inherited child marker, and the
# session under test is no longer the ordinary one the wake is claimed to reach.
# ``CLAUDE_CONFIG_DIR`` is deliberately not in here; it carries authentication.
NESTED_SESSION_VARIABLES = {"CLAUDECODE", "CLAUDE_PLUGIN_DATA"}

# Every wait is bounded, and all of them together are bounded again by a single
# per-check budget. A scripted exchange takes well under a minute when it works;
# when it does not, the useful outcome is a failure with the screen attached,
# not a harness sitting on a dead session until someone notices. Nothing here
# may block without a deadline.
QUIET_SECONDS = 4.0
TURN_TIMEOUT = 60.0
STARTUP_TIMEOUT = 30.0
CHECK_BUDGET = 180.0
EXIT_TIMEOUT = 10.0


class Expired(Exception):
    """The budget for this check ran out. Carries no state; the caller reports."""


class Deadline:
    """One wall-clock budget shared by every wait in a check.

    Individual timeouts stop any single wait from running away. This stops the
    sum of them from doing so, which is the failure that actually happened: each
    wait was within its own limit and the check still ran for eighteen minutes.
    """

    def __init__(self, budget=CHECK_BUDGET):
        self.budget = budget
        self.started = time.time()

    def remaining(self):
        return max(0.0, self.budget - (time.time() - self.started))

    def elapsed(self):
        return time.time() - self.started

    def expired(self):
        return self.remaining() <= 0.0

    def bound(self, timeout):
        """The smaller of a step's own timeout and what is left overall."""
        return min(timeout, self.remaining())

    def check(self, what):
        if self.expired():
            raise Expired("%s: the %.0fs budget for this check ran out"
                          % (what, self.budget))


def flatten(text):
    """The screen with everything the renderer owns taken out of it."""
    return WHITESPACE.sub("", ANSI.sub("", text))


class PtySession:
    """One interactive session on a pty, driven a line at a time."""

    def __init__(self, command, cwd, env, deadline=None):
        self.command = list(command)
        # Shared with the caller, so a wait started here can never outlive the
        # check's budget even if its own timeout is generous.
        self.deadline = deadline
        self.cwd = str(cwd)
        self.env = dict(env)
        self.env.update({
            # Pinned: dimensions, terminal type, and color support all change
            # what is emitted, and an unpinned one turns a timing failure here
            # into a mystery about someone's shell.
            "TERM": "xterm-256color",
            "COLUMNS": str(COLUMNS),
            "LINES": str(LINES),
            "NO_COLOR": "1",
            "CI": "1",
        })
        self.env.pop("FORCE_COLOR", None)
        for name in list(self.env):
            if name in NESTED_SESSION_VARIABLES or name.startswith("CLAUDE_CODE"):
                del self.env[name]
        self.master = None
        self.process = None
        self.buffer = ""

    # Lifecycle ------------------------------------------------------------

    def start(self):
        master, slave = pty.openpty()
        fcntl.ioctl(master, termios.TIOCSWINSZ,
                    struct.pack("HHHH", LINES, COLUMNS, 0, 0))
        self.process = subprocess.Popen(
            self.command, cwd=self.cwd, env=self.env,
            stdin=slave, stdout=slave, stderr=slave,
            close_fds=True, preexec_fn=_become_controlling_terminal,
        )
        os.close(slave)
        self.master = master
        return self

    def _bound(self, timeout):
        """A step's timeout, never exceeding what is left of the check's budget.

        Exit is deliberately not bounded this way: shutting the session down is
        what runs *after* the budget is gone, and it has its own short limit.
        """
        if self.deadline is None:
            return timeout
        return max(0.0, self.deadline.bound(timeout))

    def close(self, timeout=EXIT_TIMEOUT):
        """Ask the session to exit, and report how it went.

        Returns the exit status, or None if it had to be killed. The caller
        asserts on that: a session that had to be killed did not exit cleanly,
        whatever else the run showed.
        """
        if self.process is None:
            return None
        status = None
        try:
            if self.process.poll() is None:
                self.send_line("/exit")
                status = self._wait(timeout)
            else:
                status = self.process.returncode
        finally:
            if self.process.poll() is None:
                self._terminate()
                status = None
            if self.master is not None:
                os.close(self.master)
                self.master = None
        return status

    def _wait(self, timeout):
        deadline = time.time() + timeout
        while time.time() < deadline:
            # Keep draining: a process whose output nobody reads can block in
            # write and never reach its own exit.
            self._read_available(0.2)
            if self.process.poll() is not None:
                return self.process.returncode
        return None

    def _terminate(self):
        for send in (self.process.terminate, self.process.kill):
            try:
                send()
            except OSError:
                return
            try:
                self.process.wait(timeout=5)
                return
            except subprocess.TimeoutExpired:
                continue

    # Input ----------------------------------------------------------------

    def send_line(self, text):
        self.write(text + "\r")

    def write(self, data):
        if self.master is None:
            raise RuntimeError("session is not running")
        payload = data.encode("utf-8")
        while payload:
            written = os.write(self.master, payload)
            payload = payload[written:]

    # Output ---------------------------------------------------------------

    def _read_available(self, timeout):
        if self.master is None:
            return ""
        try:
            ready, _, _ = select.select([self.master], [], [], timeout)
        except (OSError, ValueError):
            return ""
        if not ready:
            return ""
        try:
            chunk = os.read(self.master, 65536)
        except OSError as error:
            # The child closed its end: EIO on Linux, EBADF once we have too.
            if error.errno in (errno.EIO, errno.EBADF):
                return ""
            raise
        text = chunk.decode("utf-8", errors="replace")
        self.buffer += text
        return text

    def wait_until_quiet(self, quiet=QUIET_SECONDS, timeout=TURN_TIMEOUT):
        """Block until the session stops emitting for ``quiet`` seconds.

        This is the turn boundary. It is deliberately not "a prompt appeared":
        the prompt is the interface's, and recognizing it would couple this to a
        renderer with no compatibility contract.

        Returns True if the stream went quiet, False if it never did.
        """
        deadline = time.time() + self._bound(timeout)
        last = time.time()
        while time.time() < deadline:
            if self._read_available(0.5):
                last = time.time()
                continue
            if self.process is not None and self.process.poll() is not None:
                return True
            if time.time() - last >= quiet:
                return True
        return False

    def watch(self, predicate, timeout, poll=0.5):
        """Read until ``predicate()`` holds, or the timeout expires.

        ``predicate`` takes no arguments and is re-checked after every read, so
        a caller can wait on disk state, on the screen, or on both at once.
        """
        deadline = time.time() + self._bound(timeout)
        while True:
            if predicate():
                return True
            if time.time() >= deadline:
                return False
            self._read_available(poll)

    def screen(self):
        return self.buffer

    def contains(self, needle):
        """Whether a marker is on screen, ignoring wrapping and styling."""
        return flatten(needle) in flatten(self.buffer)

    def tail(self, characters=2000):
        stripped = ANSI.sub("", self.buffer)
        lines = [line.rstrip() for line in stripped.splitlines() if line.strip()]
        return "\n".join(lines)[-characters:]


def _become_controlling_terminal():
    """Make the child a session leader owning the pty (runs in the child)."""
    os.setsid()
    # BSD and macOS attach the terminal on the session leader's first open
    # instead, which has already happened by the time this runs, so the ioctl
    # failing there is expected.
    with contextlib.suppress(OSError):
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
