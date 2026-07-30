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

# The skill needs to read candidate owners and run the dispatcher. It is granted
# nothing that can write a file: staging goes through si, which is the only
# component allowed to touch a target.
ALLOWED_TOOLS = [
    "Read", "Grep", "Glob", "Bash(%s:*)" % SI,
]


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
                             text=True, cwd=str(cwd), timeout=timeout)
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
