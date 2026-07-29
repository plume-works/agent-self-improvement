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


def run_session(cwd, messages, timeout=600, extra_args=None):
    """Drive one headless session through ``messages`` and collect its stream."""
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
