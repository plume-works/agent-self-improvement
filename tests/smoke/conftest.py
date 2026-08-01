"""Fixtures for the smoke suite: a real Claude Code session, real model calls.

Everything here sets itself up. There is no manual preparation step; running
``make smoke`` builds a scratch repository, isolates plugin state, and drives
the packaged plugin exactly as an installed one would run.

Two things are deliberately *not* isolated:

- ``CLAUDE_CONFIG_DIR`` stays as the user's own, because redirecting it would
  take the CLI's authentication with it and every session would fail to start.
  Nothing here proposes a user-scope change, and every assertion checks that
  mutations landed inside the scratch repository.
- The model is the real one. That is the point of this suite: the reviewer
  prompt and the skills have never met a real model anywhere else.

Isolation of plugin state rests on ``SELF_IMPROVE_STATE_DIR`` outranking
``CLAUDE_PLUGIN_DATA`` in :func:`selfimprove.paths.state_root`. Claude Code sets
``CLAUDE_PLUGIN_DATA`` in every hook environment it creates and discards the
inherited value, so unsetting it here is not enough on its own: with the other
precedence every hook inside a real session writes to the user's installed
plugin data directory instead, which is both a leak and a source of false
assertions here.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PLUGIN_ROOT = os.path.join(REPO_ROOT, "plugin")
SI = os.path.join(PLUGIN_ROOT, "scripts", "si")

SEED_CLAUDE_MD = """# Scratch project

## Commands

- Build with `make build`.
"""

# The correction every suite drives, deliberately as terse as a real one.
#
# Shared rather than written per suite so that no check can quietly make itself
# pass by explaining more than a user would. An earlier version stated the
# reason for the rule and asked in so many words for it to be remembered; that
# is not how people correct Claude, and a reviewer tuned against it learns to
# wait for a rationale nobody supplies. Inferring the durable lesson from a few
# words *is* the product, so the prompt under test has to be a few words.
#
# What it does carry is a standing scope ("in this repo") and an `always`, which
# is what separates a rule from an instruction about the turn in hand. Both
# markers fire on it: `correction` from the leading "no,", `retention` from
# "always use".
FIRST_TURN = "run the tests with pytest"
CORRECTION = "no, always use `make test` in this repo, not pytest directly"

# The skill needs to read candidate owners and run the dispatcher. It is granted
# nothing that can write a file: staging goes through si, which is the only
# component allowed to touch a target.
ALLOWED_TOOLS = [
    "Read", "Grep", "Glob", "Bash(%s:*)" % SI,
]

# Check 2 runs interactively, where a permission prompt is not a rejected tool
# call but a halted turn: the session sits waiting, no Stop hook fires, and the
# wake under test can never happen. So the commands its script leads Claude to
# run are allowed up front.
INTERACTIVE_ALLOWED_TOOLS = [
    *ALLOWED_TOOLS,
    "Bash(pytest:*)", "Bash(make:*)", "Bash(git:*)", "Bash(ls:*)", "Bash(cat:*)",
]

MAKEFILE = """\
.PHONY: build test

build:
\t@echo "nothing to build"

# The environment variable is the reason the suite has to go through make.
test:
\t@SCRATCH_SUITE=1 pytest -q
"""

MODULE = """\
def add(left, right):
    return left + right
"""

TEST_MODULE = """\
import unittest

from calculator import add


class AddTest(unittest.TestCase):
    def test_adds(self):
        self.assertEqual(add(2, 3), 5)
"""


def seed_runnable_project(project):
    """Give the scratch repository tests that a test command can actually run.

    Check 2 asks the operator to correct *how* the tests were run, which needs
    there to have been tests. In an empty repository the request cannot be
    carried out at all, and the session goes looking for context outside the
    project — where the first tool call stops on a permission prompt, the turn
    never ends, and no Stop hook fires.
    """
    (project / "Makefile").write_text(MAKEFILE)
    (project / "calculator.py").write_text(MODULE)
    # An empty root conftest.py is what puts the project root on sys.path, so
    # the test module can import what it tests.
    (project / "conftest.py").write_text("")
    tests = project / "tests"
    tests.mkdir(exist_ok=True)
    (tests / "test_calculator.py").write_text(TEST_MODULE)
    subprocess.run(["git", "add", "-A"], cwd=str(project), check=True)
    subprocess.run(["git", "-c", "user.email=smoke@example.invalid",
                    "-c", "user.name=Smoke Test", "commit", "-q",
                    "-m", "Add a calculator and its tests"],
                   cwd=str(project), check=True)
    return project


# Claude Code's own auto memory writes a lesson into
# ~/.claude/projects/<project>/memory/ during the turn that teaches it, before
# this plugin's Stop hook ever runs. On the correction these suites drive, it
# reliably records "always run `make test` in this repo" first — so the reviewer
# is handed a turn whose lesson is already owned, and correctly declines with
# `already_covered`. That is the right answer to the wrong question: the check
# is meant to observe the wake, not to race another system for the same lesson.
#
# So it is off by default, and the two systems meeting is a separate check that
# says so in its name. `1` disables and `0` forces on; that polarity is Claude
# Code's, not this suite's.
DEFAULT_SMOKE_AUTO_MEMORY = "0"

# Named so a launch site can declare it deliberate. The pty harness scrubs
# inherited CLAUDE_CODE* variables, and this one has to survive that.
AUTO_MEMORY_VARIABLE = "CLAUDE_CODE_DISABLE_AUTO_MEMORY"


def auto_memory_enabled():
    """Whether driving sessions may read and write Claude Code's auto memory."""
    value = os.environ.get("SMOKE_AUTO_MEMORY", DEFAULT_SMOKE_AUTO_MEMORY).strip()
    return value.lower() not in ("", "0", "false", "no", "off")


def with_auto_memory(environment, enabled=None):
    """Set auto memory explicitly, whichever way — never leave it inherited.

    A default that varies with the developer's settings would make a decline
    reproduce for one person and not another, which is the failure this whole
    dial exists to stop happening again.
    """
    if enabled is None:
        enabled = auto_memory_enabled()
    environment[AUTO_MEMORY_VARIABLE] = "0" if enabled else "1"
    return environment


def runner_environment(auto_memory=None):
    """The environment for a session that is expected to run ``pytest``.

    The scratch project has no interpreter of its own, and the plugin has no
    dependencies to install one. What it does have is this suite's own runner:
    putting its directory on ``PATH`` makes ``pytest`` and the seeded
    ``make test`` genuinely work inside the scratch repository, so the first
    turn of check 2 succeeds instead of failing on a missing module.
    """
    environment = dict(os.environ)
    environment["PATH"] = os.pathsep.join(
        [os.path.dirname(sys.executable), environment.get("PATH", "")])
    return with_auto_memory(environment, auto_memory)


def require_cli():
    if shutil.which("claude") is None:
        pytest.skip("the claude CLI is not on PATH")


@pytest.fixture(scope="session")
def cli_version():
    require_cli()
    result = subprocess.run(["claude", "--version"], capture_output=True,
                            text=True, timeout=30)
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", result.stdout or "")
    if not match:
        pytest.skip("could not determine the claude version")
    version = tuple(int(part) for part in match.groups())
    if version < (2, 1, 196):
        pytest.skip("claude %s predates UserPromptExpansion; upgrade to 2.1.196+"
                    % ".".join(str(p) for p in version))
    return version


SCRATCH_ROOT = os.path.join(REPO_ROOT, "tmp", "smoke")

# Provider-side failures: the CLI ran, the call inside it did not. These say
# nothing about the plugin, so a check that hits one is retried and then skipped
# rather than reported as a product failure. Everything else fails loudly.
PROVIDER_STATUSES = {401: "unauthenticated", 403: "unauthenticated",
                     429: "rate_limited", 500: "provider_error",
                     502: "provider_error", 503: "overloaded",
                     529: "overloaded"}

PROVIDER_PHRASES = re.compile(
    r"(?i)usage limit|out of credit|quota|rate[ _-]?limit|too many requests|"
    r"overloaded|service unavailable|api error|internal server error|"
    r"invalid api key|please run /login|not logged in|"
    r"issue with the selected model")

SESSION_RETRY_DELAY = 20

# The model the *driving* session runs on. Not the reviewer: that is the
# component under test, it stays on SELF_IMPROVE_REVIEW_MODEL, and lowering it
# would make a green run stop saying anything about what ships. The driving
# sessions only follow a short scripted procedure, so they default to sonnet
# rather than to whatever the developer's CLI prefers — observing a plugin
# behaviour that does not depend on the model should not cost Opus usage.
DEFAULT_SMOKE_MODEL = "sonnet"


def smoke_model():
    """The driving session's model, or None to accept the CLI default.

    ``SMOKE_MODEL=`` (empty) is the way back to the CLI default, which a
    model-specific failure has to be reproducible against.
    """
    return os.environ.get("SMOKE_MODEL", DEFAULT_SMOKE_MODEL).strip() or None


# Claude Code defaults to `high` effort. These sessions follow a written
# procedure — run the suite, state a correction, accept a proposal — which is
# not reasoning work, so they are dropped to `low`. The reviewer is a separate
# dial and stays higher; see SELF_IMPROVE_REVIEW_EFFORT.
DEFAULT_SMOKE_EFFORT = "low"


def smoke_effort():
    """The driving session's effort level, or None to accept the CLI default."""
    return os.environ.get("SMOKE_EFFORT", DEFAULT_SMOKE_EFFORT).strip() or None


def model_args():
    model = smoke_model()
    return ["--model", model] if model else []


def effort_args():
    """``--effort``, not ``CLAUDE_CODE_EFFORT_LEVEL``.

    The environment variable would be inherited by every session the harness
    starts *and* by the reviewer subprocesses inside them, overriding the
    reviewer's own level. The flag reaches only the session it launches. An
    unknown flag is also a loud CLI error, which is what this suite wants: the
    version floor is already checked, so an effort level that stopped being
    accepted should fail rather than silently run at some other level.
    """
    effort = smoke_effort()
    return ["--effort", effort] if effort else []


def session_args():
    """Everything that decides how much a driving session costs to run."""
    return model_args() + effort_args()


def mangle_path(path):
    """The CLI's directory key for a working directory.

    Every character outside ``[A-Za-z0-9-]`` becomes a dash, so
    ``/tmp/smoke/test_2_x/project`` keys as ``-tmp-smoke-test-2-x-project``.
    Underscores are included: they are converted, not kept.
    """
    return re.sub(r"[^A-Za-z0-9-]", "-", str(path))


def claude_session_dir(project):
    """Where Claude Code keeps its own transcripts and memories for a directory."""
    home = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude")
    return os.path.join(home, "projects", mangle_path(project))


def forget_previous_runs(project):
    """Drop Claude's own transcripts and memories for a scratch directory.

    These live outside the workspace, so wiping ``tmp/smoke`` does not reach
    them and the next run starts holding the previous run's memory of the very
    lesson under test. In check 2 that appeared as Claude answering "already
    saved in memory, so no update needed" instead of taking the proposal, and in
    check 6 it would let a fresh session answer from memory rather than from the
    instruction that was just applied.

    Guarded on the scratch root, so it can only ever remove state belonging to a
    smoke workspace. If the CLI ever derives these paths differently the guard
    stops matching and nothing is deleted, which loses repeatability rather than
    touching anything it should not.
    """
    directory = claude_session_dir(project)
    if os.path.basename(directory).startswith(mangle_path(SCRATCH_ROOT)):
        shutil.rmtree(directory, ignore_errors=True)
    return directory


@pytest.fixture
def scratch(request, monkeypatch, cli_version):
    """A throwaway git repository with isolated plugin state.

    Lives under the repository's own gitignored ``tmp/`` rather than the system
    temporary directory, so that after a failure the workspace, the plugin
    state, and the diagnostics are all sitting somewhere obvious. It is wiped at
    the start of each run and deliberately left behind at the end.
    """
    workspace = os.path.join(SCRATCH_ROOT, request.node.name)
    if os.path.isdir(workspace):
        shutil.rmtree(workspace)

    project = pathlib.Path(workspace) / "project"
    project.mkdir(parents=True)
    (project / "CLAUDE.md").write_text(SEED_CLAUDE_MD)
    subprocess.run(["git", "init", "-q"], cwd=str(project), check=True)
    forget_previous_runs(project)

    state = pathlib.Path(workspace) / "state"
    monkeypatch.setenv("SELF_IMPROVE_STATE_DIR", str(state))
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", PLUGIN_ROOT)
    monkeypatch.chdir(project)
    return {"project": project, "state": state, "target": project / "CLAUDE.md",
            "workspace": pathlib.Path(workspace)}


class Session:
    """One headless Claude Code session driven over stream-json.

    Multiple user messages go to the same session, so a conversation can be
    scripted without a terminal. ``--include-hook-events`` is what makes the
    plugin's own hooks observable as structured data rather than as text to
    scrape.
    """

    def __init__(self, cwd, events, returncode, stderr, elapsed):
        self.cwd = cwd
        self.events = events
        self.returncode = returncode
        self.stderr = stderr
        self.elapsed = elapsed

    def hook_events(self, name=None):
        found = []
        for event in self.events:
            if event.get("type") != "system":
                continue
            if not str(event.get("subtype", "")).startswith("hook_"):
                continue
            if name and event.get("hook_event") != name:
                continue
            found.append(event)
        return found

    def assistant_text(self):
        chunks = []
        for event in self.events:
            if event.get("type") != "assistant":
                continue
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "text":
                    chunks.append(block.get("text", ""))
        return "\n".join(chunks)

    def results(self):
        return [event for event in self.events if event.get("type") == "result"]

    def find(self, needle):
        return [event for event in self.events if needle in json.dumps(event)]

    def provider_failure(self):
        """Why the provider, not the plugin, kept this session from answering.

        A rate-limited or overloaded turn still exits zero and still emits an
        assistant message: the message is the error text. Undetected, that
        becomes whichever assertion happened to run first — a Stop hook that
        never fired, an answer that does not mention `make test` — and a
        provider outage gets read as a product defect.
        """
        for event in self.events:
            if event.get("type") == "assistant" and event.get("is_api_error_message"):
                return _provider_class(event.get("error"), _text_of(event))
        for event in self.results():
            if event.get("terminal_reason") == "api_error" or \
                    event.get("api_error_status"):
                return _provider_class(event.get("api_error_status"),
                                       event.get("result"))
        if not self.results():
            # No result event at all: the CLI never got as far as a turn. Only a
            # provider or authentication failure is transient; anything else has
            # to fail.
            return _provider_class(None, self.stderr)
        return None

    def failure(self):
        """Why this session did not complete a normal turn, provider aside."""
        if self.returncode != 0:
            return "the claude CLI exited %d: %s" % (
                self.returncode, (self.stderr or "").strip()[:400] or "(no stderr)")
        results = self.results()
        if not results:
            return "the session emitted no result event"
        last = results[-1]
        if last.get("is_error") or last.get("subtype") not in (None, "success"):
            return "the session ended in %s (%s)" % (
                last.get("subtype"), last.get("terminal_reason"))
        if not [event for event in self.events if event.get("type") == "assistant"]:
            return "the session produced no assistant message"
        return None


def _text_of(event):
    chunks = [block.get("text", "")
              for block in event.get("message", {}).get("content", [])
              if block.get("type") == "text"]
    return "\n".join(chunks)


def _provider_class(status, text):
    """Name a provider failure, or return None if this is not one."""
    if isinstance(status, int) and status in PROVIDER_STATUSES:
        return PROVIDER_STATUSES[status]
    if isinstance(status, str) and status:
        return status
    if text and PROVIDER_PHRASES.search(text):
        return PROVIDER_PHRASES.search(text).group(0).lower()
    return None


def run_session(cwd, messages, timeout=600, extra_args=None, attempts=2):
    """Drive one headless session through ``messages`` and collect its stream.

    A provider failure is retried once and then skips the check. That is the
    honest outcome: nothing about the plugin was observed, and reporting it as a
    failure sends the next reader looking for a defect that is not there. Every
    other way a session can end badly fails, including the ones that would
    otherwise let a check pass without the session ever having answered.
    """
    attempts = max(attempts, 1)
    session = None
    reason = None
    for attempt in range(attempts):
        session = _run_session_once(cwd, messages, timeout=timeout,
                                    extra_args=extra_args)
        reason = session.provider_failure()
        if reason is None:
            break
        if attempt + 1 < attempts:
            time.sleep(SESSION_RETRY_DELAY)

    if reason is not None:
        pytest.skip("the model call did not go through (%s); this check observed "
                    "nothing about the plugin. %d attempt%s, %ds apart."
                    % (reason, attempts, "" if attempts == 1 else "s",
                       SESSION_RETRY_DELAY))

    failed = session.failure()
    assert failed is None, \
        "the session did not complete a turn, so nothing below is meaningful: %s" \
        % failed
    return session


def _run_session_once(cwd, messages, timeout=600, extra_args=None):
    require_cli()
    command = [
        "claude", "-p",
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        "--include-hook-events",
        "--verbose",
        "--plugin-dir", PLUGIN_ROOT,
        *session_args(),
        "--allowedTools", *ALLOWED_TOOLS,
        "--max-turns", "40",
    ]
    command += list(extra_args or [])

    payload = "".join(
        json.dumps({"type": "user",
                    "message": {"role": "user",
                                "content": [{"type": "text", "text": text}]}}) + "\n"
        for text in messages
    )

    started = time.time()
    process = subprocess.run(command, input=payload, capture_output=True,
                             text=True, cwd=str(cwd), timeout=timeout,
                             env=with_auto_memory(dict(os.environ)))
    elapsed = time.time() - started

    events = []
    for line in process.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    return Session(cwd, events, process.returncode, process.stderr, elapsed)


@pytest.fixture
def session(scratch):
    def _run(messages, **kwargs):
        if isinstance(messages, str):
            messages = [messages]
        return run_session(scratch["project"], messages, **kwargs)
    return _run


def si(scratch, *args, stdin=None):
    """Invoke the packaged dispatcher the way a hook or skill would."""
    return subprocess.run([SI, *args], input=stdin if stdin is not None else "",
                          capture_output=True, text=True,
                          cwd=str(scratch["project"]), env=dict(os.environ),
                          timeout=120)


def expansion(operation, args, session_id="smoke-session"):
    """The hook payload Claude Code emits when the user types a plugin command."""
    return json.dumps({
        "hook_event_name": "UserPromptExpansion",
        "session_id": session_id,
        "expansion_type": "slash_command",
        "command_source": "plugin",
        "command_name": operation,
        "command_args": args,
    })


def ask(question):
    """One yes/no question to the operator, for what only a human can see."""
    sys.stdout.write("\n%s [y/N] " % question)
    sys.stdout.flush()
    try:
        answer = input().strip().lower()
    except EOFError:
        return None
    return answer in ("y", "yes")
