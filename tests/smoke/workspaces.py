"""
Where a live run puts everything it produces.

Every check that drives a real session leaves a scratch repository, isolated
plugin state, and a raw terminal stream behind, and all of it has to still be
there afterwards. The path used to depend only on the test's name, so it was the
same on every run of every target: ``make smoke`` and ``make wake`` overwrote
each other, and ``make wake-repeat`` destroyed nine of its ten runs on the way to
the tenth — the one target whose whole purpose is comparing runs.

So each *process* claims its own directory under ``test-runs/``, named for the
target that started it, and nothing ever writes where another run has written.

Kept apart from ``conftest.py`` because ``make clean-claude`` runs it as a
program rather than as a fixture.
"""

import contextlib
import os
import re
import shutil
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RUNS_ROOT = os.path.join(REPO_ROOT, 'test-runs')

# Where runs were written before this module existed. Only the sweep reads these:
# a workspace left by the old layout still has a Claude project directory
# outside the repository, and `make clean-claude` should still be able to find
# it. Nothing writes here any more.
LEGACY_ROOTS = (os.path.join(REPO_ROOT, 'tmp', 'smoke'),)

DEFAULT_LABEL = 'pytest'

# One value per process, filled in on first use. This is the whole mechanism by
# which a run stays together: both live checks of one `make wake` ask for the
# root and get the same answer, while `make wake-repeat`'s ten separate pytest
# processes each compute their own, with no bookkeeping in the loop.
_run_root = None


def run_label():
    """
    Which target is running, for the directory name.

    Set by the Makefile per target so a `make wake` directory can never be
    mistaken for a `make smoke` one. A developer running pytest directly gets
    the default rather than an error: the label decides a name, not a behaviour.
    """
    return os.environ.get('TEST_RUN_LABEL', '').strip() or DEFAULT_LABEL


def run_stamp(now=None):
    """
    A sortable local timestamp, to the nanosecond.

    Seconds would be the readable choice and the wrong one. Two runs starting
    inside the same second is not hypothetical — `make wake-repeat` starts a
    process as soon as the previous one exits — and the alternative to a stamp
    that cannot collide is a uniquifying loop that has to be written, tested,
    and reasoned about at every call site. Nanoseconds buy all of that for nine
    characters.
    """
    now = time.time_ns() if now is None else now
    seconds, nanoseconds = divmod(now, 1_000_000_000)
    return '%s.%09d' % (time.strftime('%Y-%m-%d_%H-%M-%S', time.localtime(seconds)), nanoseconds)


def run_root():
    """
    This process's directory, created on first use.

    Deliberately not computed at import. ``make test`` imports the smoke
    ``conftest.py`` during collection even though it deselects every test in it,
    and a root claimed at import time would leave an empty directory behind on
    every offline run.
    """
    global _run_root
    if _run_root is None:
        root = os.path.join(RUNS_ROOT, '%s_%s' % (run_label(), run_stamp()))
        os.makedirs(root, exist_ok=True)
        refresh_latest(root)
        _run_root = root
    return _run_root


def run_family(label):
    """
    The label with a run number taken off it.

    ``make wake-repeat`` numbers its ten iterations so they sort in the order
    they ran, which makes every label unique — and a ``latest-<label>`` link per
    unique label is ten links each pointing at the one run that could ever
    match. Useless, and it buries the ones that mean something. The family is
    what the shortcut is for: ``latest-wake-repeat`` is the newest iteration,
    whichever number it carried.
    """
    return re.sub(r'-\d+$', '', label)


def refresh_latest(root, label=None):
    """
    Point ``latest`` and ``latest-<family>`` at ``root``.

    A convenience for finding the run you just did without reading timestamps.
    Every failure is suppressed: a filesystem that cannot do symlinks should
    cost a shortcut, not a run.
    """
    label = run_label() if label is None else label
    for name in ('latest', 'latest-%s' % run_family(label)):
        link = os.path.join(RUNS_ROOT, name)
        with contextlib.suppress(OSError):
            if os.path.islink(link) or os.path.exists(link):
                os.remove(link)
            os.symlink(os.path.basename(root), link)
    return root


def mangle_path(path):
    """
    The CLI's directory key for a working directory.

    Every character outside ``[A-Za-z0-9-]`` becomes a dash, so
    ``/repo/test-runs/wake_x/project`` keys as
    ``-repo-test-runs-wake-x-project``. Underscores and dots are included: they
    are converted, not kept.
    """
    return re.sub(r'[^A-Za-z0-9-]', '-', str(path))


# What the mangled key of a run's working directory looks like after the runs
# root: a label, the run stamp, and whatever the run put underneath it. The
# stamp is what makes this a rule rather than a guess. A prefix on the runs
# root is not enough, because mangling maps `/` and `-` to the same character:
# a real project at `<repo>/test-runs-archive/project` keys with every
# character `<repo>/test-runs/` keys with, and this sweep deletes what it
# names. No neighbouring path carries a date, a time, and nine digits of
# nanoseconds in the position a run directory carries them — short of a
# neighbour that reproduces a run directory's own name, which nothing can tell
# apart from a run once the separators are gone.
RUN_KEY_TAIL = r'-.+-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}-\d{9}(?:-.*)?'

# The old layout had no stamp to match on: it named a workspace after the test
# that claimed it, and Claude ran in that workspace's `project/`. Both ends are
# required, so the neighbour that could still be mistaken for one of these would
# have to be a Claude working directory named `project`, inside a sibling of the
# repository's own gitignored `tmp/smoke`, under a directory beginning `test`.
LEGACY_KEY_TAIL = r'-test-.+-project'


def claude_config_dir():
    return os.environ.get('CLAUDE_CONFIG_DIR') or os.path.join(os.path.expanduser('~'), '.claude')


def claude_session_dir(project):
    """Where Claude Code keeps its own transcripts and memories for a directory."""
    return os.path.join(claude_config_dir(), 'projects', mangle_path(project))


def scratch_project_dirs(config_dir=None):
    """
    Claude project directories belonging to a test run, newest name last.

    A key qualifies only if it is one of the roots' keys *followed by the shape
    a run writes underneath it* — the stamp for the current layout, a test's
    workspace and its ``project/`` for the old one. That is what keeps this
    incapable of naming anything outside ``test-runs/``, including the
    neighbours of ``test-runs/`` that a prefix rule cannot tell apart from it.
    """
    projects = os.path.join(config_dir or claude_config_dir(), 'projects')
    if not os.path.isdir(projects):
        return []
    patterns = [
        re.compile(re.escape(mangle_path(root)) + tail + r'\Z')
        for root, tail in [(RUNS_ROOT, RUN_KEY_TAIL)]
        + [(legacy, LEGACY_KEY_TAIL) for legacy in LEGACY_ROOTS]
    ]
    return sorted(
        os.path.join(projects, entry)
        for entry in os.listdir(projects)
        if any(pattern.match(entry) for pattern in patterns)
    )


def sweep_claude_projects(config_dir=None, stream=None):
    """
    Delete the Claude project directories that test runs left in ``~/.claude``.

    Each run now works in a directory nothing else has used, so Claude Code
    opens a fresh ``projects/<mangled-path>/`` for it and no run inherits the
    previous one's memory of the lesson under test. The cost of that is one
    small directory per run, accumulating outside the repository where
    ``make clean`` cannot see it. This is how they are cleared.

    Every path is printed before it goes: this deletes outside the repository,
    so what it deleted has to be readable afterwards rather than inferred from
    the matching rule.
    """
    stream = sys.stdout if stream is None else stream
    removed = []
    for path in scratch_project_dirs(config_dir):
        stream.write('removing %s\n' % path)
        shutil.rmtree(path, ignore_errors=True)
        removed.append(path)
    stream.write(
        'removed %d test-run project director%s\n'
        % (len(removed), 'y' if len(removed) == 1 else 'ies')
    )
    return removed


if __name__ == '__main__':
    sweep_claude_projects()
