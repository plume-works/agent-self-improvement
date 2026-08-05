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
import sys
import termios
import time

# Escape sequences, then every whitespace character, are removed before the one
# on-screen match. A 17-character candidate id is wrapped across lines whenever
# it lands near the right margin, and a match that failed for that reason would
# report a missing wake that in fact arrived.
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[]P^_].*?(?:\x1b\\|\x07)|\x1b[@-Z\\-_]", re.DOTALL)
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


# How often a wait that is still running says so. Without this a stalled check
# is indistinguishable from a working one until its budget expires, which is the
# whole difficulty in debugging this harness: everything interesting happens
# between two log lines that are three minutes apart.
HEARTBEAT_SECONDS = 5.0

# How much of the flattened screen an echo line shows. Enough to see whether a
# prompt landed and what came back, short enough to stay readable in a trace.
ECHO_CHARACTERS = 400


class Expired(Exception):
    """The budget for this check ran out. Carries no state; the caller reports."""


class Trace:
    """A timestamped account of what the harness did and what came back.

    The failure this exists for is not a wrong assertion, it is a check that
    sits there. A run that stalls has to say *where* it stalled — which prompt
    was sent, whether anything was read afterwards, which wait it is inside —
    and it has to say it while it is still stalling rather than in a post-mortem
    three minutes later.

    Three streams, each with a different job:

    - ``event`` lines to stdout, the readable narrative of the run;
    - ``echo`` lines, the flattened screen after each step, which is what shows
      whether input the harness typed was actually captured by the session; and
    - a raw transcript file, every byte the pty produced, escape sequences
      included, for when the flattened view is not enough.

    Off by nothing: tracing costs nothing measurable and these checks are opt-in
    already. ``WAKE_TRACE=0`` silences stdout; the transcript is always written
    when a directory is given, since a workspace is kept after a run anyway.
    """

    def __init__(self, name, directory=None, stream=None):
        self.name = name
        self.started = time.time()
        self.stream = stream if stream is not None else sys.stdout
        self.enabled = os.environ.get("WAKE_TRACE", "1") not in ("0", "", "no")
        self.transcript = None
        if directory is not None:
            with contextlib.suppress(OSError):
                os.makedirs(str(directory), exist_ok=True)
                self.transcript = open(  # noqa: SIM115 - closed in close()
                    os.path.join(str(directory), "%s.pty.log" % name), "w", encoding="utf-8"
                )

    def elapsed(self):
        return time.time() - self.started

    def event(self, kind, detail=""):
        line = "[wake %6.1fs] %-22s %s" % (self.elapsed(), kind, detail)
        if self.enabled:
            self.stream.write(line.rstrip() + "\n")
            self.stream.flush()
        if self.transcript is not None:
            self.transcript.write("### " + line.strip() + "\n")
            self.transcript.flush()

    def echo(self, label, text, characters=ECHO_CHARACTERS):
        """What the terminal is showing, with everything the renderer owns gone.

        This is the echo of captured input: the harness types blind — it never
        reads the screen to decide anything — so this is the only place a person
        can see whether what was typed arrived, arrived twice, or landed inside
        the previous turn instead of starting its own.
        """
        visible = ANSI.sub("", text)
        lines = [line.rstrip() for line in visible.splitlines() if line.strip()]
        self.event("echo/" + label, "%d chars" % len(text))
        if not self.enabled:
            return
        for line in "\n".join(lines)[-characters:].splitlines():
            self.stream.write("             | %s\n" % line)
        self.stream.flush()

    def raw(self, text):
        if self.transcript is not None:
            self.transcript.write(text)
            self.transcript.flush()

    def close(self):
        if self.transcript is not None:
            self.transcript.close()
            self.transcript = None


class SilentTrace(Trace):
    """A trace that records nothing, for the self-checks that do not want one."""

    def __init__(self):
        Trace.__init__(self, "silent")
        self.enabled = False


class Deadline:
    """One wall-clock budget shared by every wait in a check.

    Individual timeouts stop any single wait from running away. This stops the
    sum of them from doing so, which is the failure that actually happened: each
    wait was within its own limit and the check still ran for eighteen minutes.
    """

    def __init__(self, budget=None, trace=None):
        # ``WAKE_BUDGET`` exists for debugging, in both directions: a shorter
        # budget to see a stall fail quickly, a longer one to find out whether a
        # check that keeps expiring would ever have finished. It is not a
        # setting — the normative bound in Spec-0002 section 7.1 is the default.
        self.budget = float(os.environ.get("WAKE_BUDGET") or CHECK_BUDGET) if budget is None else budget
        self.started = time.time()
        self.trace = trace if trace is not None else SilentTrace()

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
        self.trace.event(
            "budget", "%s: %.0fs used, %.0fs left of %.0fs" % (what, self.elapsed(), self.remaining(), self.budget)
        )
        if self.expired():
            raise Expired("%s: the %.0fs budget for this check ran out" % (what, self.budget))


def flatten(text):
    """The screen with everything the renderer owns taken out of it."""
    return WHITESPACE.sub("", ANSI.sub("", text))


class PtySession:
    """One interactive session on a pty, driven a line at a time."""

    def __init__(self, command, cwd, env, deadline=None, trace=None, configured=()):
        self.command = list(command)
        # Shared with the caller, so a wait started here can never outlive the
        # check's budget even if its own timeout is generous.
        self.deadline = deadline
        self.trace = trace or (deadline.trace if deadline is not None else SilentTrace())
        self.cwd = str(cwd)
        self.env = dict(env)
        self.env.update(
            {
                # Pinned: dimensions, terminal type, and color support all change
                # what is emitted, and an unpinned one turns a timing failure here
                # into a mystery about someone's shell.
                "TERM": "xterm-256color",
                "COLUMNS": str(COLUMNS),
                "LINES": str(LINES),
                "NO_COLOR": "1",
                "CI": "1",
            }
        )
        self.env.pop("FORCE_COLOR", None)
        # The scrub below is a prefix match, which is right for anything
        # inherited and wrong for anything the caller set on purpose. It
        # silently removed CLAUDE_CODE_DISABLE_AUTO_MEMORY for a whole live run,
        # so the session kept writing its own memory for the lesson the reviewer
        # was about to be asked about — a failure that had already been
        # configured away.
        #
        # `configured` is named by the caller rather than listed here on
        # purpose. A module-level allowlist would be a place to park exemptions,
        # and each one would outlive whatever needed it; naming the variable at
        # the launch site keeps the exemption owned by the code that set it, and
        # a launch site that stops setting it stops exempting it.
        configured = set(configured)
        for name in list(self.env):
            if name in configured:
                continue
            if name in NESTED_SESSION_VARIABLES or name.startswith("CLAUDE_CODE"):
                del self.env[name]
        self.master = None
        self.process = None
        self.buffer = ""

    # Lifecycle ------------------------------------------------------------

    def start(self):
        self.trace.event("start", " ".join(self.command))
        self.trace.event("cwd", self.cwd)
        master, slave = pty.openpty()
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", LINES, COLUMNS, 0, 0))
        self.process = subprocess.Popen(
            self.command,
            cwd=self.cwd,
            env=self.env,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            close_fds=True,
            preexec_fn=_become_controlling_terminal,
        )
        os.close(slave)
        self.master = master
        self.trace.event("started", "pid %d" % self.process.pid)
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
        self.trace.event("close", "asking the session to exit")
        try:
            if self.process.poll() is None:
                self.send_line("/exit")
                status = self._wait(timeout)
            else:
                status = self.process.returncode
        finally:
            if self.process.poll() is None:
                self.trace.event("close/kill", "the session ignored /exit; terminating")
                self._terminate()
                status = None
            if self.master is not None:
                os.close(self.master)
                self.master = None
        self.trace.event("closed", "exit status %r" % (status,))
        self.trace.close()
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
        self.trace.event("send", repr(text))
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
        self.trace.raw(text)
        return text

    def wait_until_quiet(self, quiet=QUIET_SECONDS, timeout=TURN_TIMEOUT, label="turn"):
        """Block until the session stops emitting for ``quiet`` seconds.

        This is the turn boundary. It is deliberately not "a prompt appeared":
        the prompt is the interface's, and recognizing it would couple this to a
        renderer with no compatibility contract.

        Returns True if the stream went quiet, False if it never did.
        """
        allowed = self._bound(timeout)
        deadline = time.time() + allowed
        started = time.time()
        self.trace.event("wait/%s" % label, "quiet for %.1fs, up to %.0fs" % (quiet, allowed))
        received = 0
        last = time.time()
        beat = time.time()
        while time.time() < deadline:
            chunk = self._read_available(0.5)
            if chunk:
                received += len(chunk)
                last = time.time()
            elif self.process is not None and self.process.poll() is not None:
                self.trace.event(
                    "wait/%s exit" % label,
                    "the session ended after %.1fs, %d chars" % (time.time() - started, received),
                )
                return True
            elif time.time() - last >= quiet:
                self.trace.event("wait/%s quiet" % label, "after %.1fs, %d chars" % (time.time() - started, received))
                return True
            if time.time() - beat >= HEARTBEAT_SECONDS:
                beat = time.time()
                self.trace.event(
                    "wait/%s ..." % label,
                    "%.0fs elapsed, %d chars, %.1fs since output, "
                    "%.0fs left" % (time.time() - started, received, time.time() - last, deadline - time.time()),
                )
        self.trace.event(
            "wait/%s TIMEOUT" % label, "still talking after %.1fs, %d chars" % (time.time() - started, received)
        )
        return False

    def watch(self, predicate, timeout, poll=0.5, label="condition"):
        """Read until ``predicate()`` holds, or the timeout expires.

        ``predicate`` takes no arguments and is re-checked after every read, so
        a caller can wait on disk state, on the screen, or on both at once.
        """
        allowed = self._bound(timeout)
        deadline = time.time() + allowed
        started = time.time()
        self.trace.event("watch/%s" % label, "up to %.0fs" % allowed)
        beat = time.time()
        while True:
            if predicate():
                self.trace.event("watch/%s met" % label, "after %.1fs" % (time.time() - started))
                return True
            if time.time() >= deadline:
                self.trace.event("watch/%s TIMEOUT" % label, "never met, %.1fs" % (time.time() - started))
                return False
            self._read_available(poll)
            if time.time() - beat >= HEARTBEAT_SECONDS:
                beat = time.time()
                self.trace.event(
                    "watch/%s ..." % label,
                    "%.0fs elapsed, %.0fs left" % (time.time() - started, deadline - time.time()),
                )

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
