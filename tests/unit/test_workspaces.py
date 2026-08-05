"""
Where a live run puts its output, checked without spending a live run.

Everything here is deterministic and costs nothing, which matters because the
behaviour it covers is otherwise only observable by paying for ten sessions:
`make wake-repeat` keeping its ten runs apart rests entirely on each pytest
process claiming its own root, and that is a property of this module rather than
of the sessions it runs.
"""

import io
import os
import time

import pytest

from tests.smoke import workspaces


@pytest.fixture(autouse=True)
def _forget_the_memoized_root(monkeypatch):
    """Each test starts as its own process would, with no root claimed yet."""
    monkeypatch.setattr(workspaces, '_run_root', None)


@pytest.fixture
def runs_root(tmp_path, monkeypatch):
    """A runs root of our own, so nothing here writes to the repository's."""
    root = tmp_path / 'test-runs'
    monkeypatch.setattr(workspaces, 'RUNS_ROOT', str(root))
    return root


# Naming --------------------------------------------------------------------


def test_the_run_directory_is_named_for_the_target_that_started_it(runs_root, monkeypatch):
    """`make wake` can never land in a `make smoke` directory."""
    monkeypatch.setenv('TEST_RUN_LABEL', 'wake')
    assert os.path.basename(workspaces.run_root()).startswith('wake_')


def test_a_direct_pytest_run_still_gets_a_directory(runs_root, monkeypatch):
    """No label is a naming question, never a failure."""
    monkeypatch.delenv('TEST_RUN_LABEL', raising=False)
    assert os.path.basename(workspaces.run_root()).startswith('pytest_')


def test_the_stamp_is_sortable_and_carries_nanoseconds():
    """Sortable so `ls` is chronological; nanoseconds so it cannot collide."""
    stamp = workspaces.run_stamp(1785652202123456789)
    assert stamp.endswith('.123456789')
    assert stamp.startswith(time.strftime('%Y-%m-%d', time.localtime(1785652202)))
    assert workspaces.run_stamp(1) < workspaces.run_stamp(2)


def test_two_stamps_taken_in_a_row_differ():
    """The reason there is no collision suffix to test."""
    assert workspaces.run_stamp() != workspaces.run_stamp()


# One root per process ------------------------------------------------------


def test_the_root_is_claimed_once_and_reused(runs_root, monkeypatch):
    """Both live checks of one `make wake` must land in the same directory."""
    monkeypatch.setenv('TEST_RUN_LABEL', 'wake')
    first = workspaces.run_root()
    assert workspaces.run_root() == first
    assert os.path.isdir(first)


def test_a_second_process_claims_a_different_root(runs_root, monkeypatch):
    """
    What makes ten runs of `make wake-repeat` ten readable results.

    Clearing the memo is what a new pytest process does by existing, so this is
    the loop's behaviour with the process boundary stood in for.
    """
    monkeypatch.setenv('TEST_RUN_LABEL', 'wake-repeat-01')
    first = workspaces.run_root()

    monkeypatch.setattr(workspaces, '_run_root', None)
    monkeypatch.setenv('TEST_RUN_LABEL', 'wake-repeat-02')
    second = workspaces.run_root()

    assert first != second
    assert os.path.isdir(first) and os.path.isdir(second)


def test_nothing_is_created_until_a_root_is_asked_for(runs_root, monkeypatch):
    """`make test` imports the smoke conftest and must leave no directory."""
    monkeypatch.setenv('TEST_RUN_LABEL', 'pytest')
    assert not runs_root.exists()


# The latest symlinks -------------------------------------------------------


def test_latest_points_at_the_newest_run(runs_root, monkeypatch):
    monkeypatch.setenv('TEST_RUN_LABEL', 'wake')
    first = workspaces.run_root()

    monkeypatch.setattr(workspaces, '_run_root', None)
    second = workspaces.run_root()

    assert (runs_root / 'latest').is_symlink()
    assert os.path.realpath(str(runs_root / 'latest')) == os.path.realpath(second)
    assert os.path.realpath(str(runs_root / 'latest-wake')) == os.path.realpath(second)
    assert os.path.isdir(first), 'the previous run must survive being superseded'


def test_each_target_keeps_its_own_latest(runs_root, monkeypatch):
    """`latest-smoke` must not be moved by a wake run, or it says nothing."""
    monkeypatch.setenv('TEST_RUN_LABEL', 'smoke')
    smoke = workspaces.run_root()

    monkeypatch.setattr(workspaces, '_run_root', None)
    monkeypatch.setenv('TEST_RUN_LABEL', 'wake')
    wake = workspaces.run_root()

    assert os.path.realpath(str(runs_root / 'latest-smoke')) == os.path.realpath(smoke)
    assert os.path.realpath(str(runs_root / 'latest-wake')) == os.path.realpath(wake)
    assert os.path.realpath(str(runs_root / 'latest')) == os.path.realpath(wake)


def test_a_numbered_run_updates_its_family_link_not_one_of_its_own(runs_root, monkeypatch):
    """
    Ten iterations of `make wake-repeat` leave one shortcut, not ten.

    Observed on the first real ten-run loop: every iteration carries its own
    label so the directories sort in order, and a link per label meant ten
    `latest-wake-repeat-NN` entries each pointing at the single run that could
    ever match, burying `latest-wake` and `latest-smoke` among them.
    """
    for number in ('01', '02', '03'):
        monkeypatch.setattr(workspaces, '_run_root', None)
        monkeypatch.setenv('TEST_RUN_LABEL', 'wake-repeat-%s' % number)
        newest = workspaces.run_root()

    links = sorted(name for name in os.listdir(str(runs_root)) if name.startswith('latest'))
    assert links == ['latest', 'latest-wake-repeat']
    assert os.path.realpath(str(runs_root / 'latest-wake-repeat')) == os.path.realpath(newest)


def test_the_family_is_only_a_trailing_run_number(runs_root):
    """A target whose name ends in a word keeps it; only digits are a number."""
    assert workspaces.run_family('wake-repeat-07') == 'wake-repeat'
    assert workspaces.run_family('wake') == 'wake'
    assert workspaces.run_family('smoke-auto') == 'smoke-auto'
    assert workspaces.run_family('wake-memory') == 'wake-memory'


def test_a_filesystem_without_symlinks_costs_a_shortcut_not_a_run(runs_root, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise OSError('symlinks not supported here')

    monkeypatch.setattr(workspaces.os, 'symlink', refuse)
    monkeypatch.setenv('TEST_RUN_LABEL', 'wake')
    assert os.path.isdir(workspaces.run_root())


# The sweep -----------------------------------------------------------------


def _project_entry(config_dir, path):
    """A Claude project directory as the CLI would key it for ``path``."""
    entry = os.path.join(config_dir, 'projects', workspaces.mangle_path(path))
    os.makedirs(entry)
    return entry


def _run_dir(runs_root, label='wake', stamp='2026-08-02_03-00-00.123456789'):
    """A run directory named the way ``run_root()`` names one."""
    return runs_root / ('%s_%s' % (label, stamp))


def test_the_sweep_finds_a_directory_belonging_to_a_run(tmp_path, runs_root):
    config = tmp_path / 'claude'
    mine = _project_entry(str(config), str(_run_dir(runs_root) / 'project'))

    removed = workspaces.sweep_claude_projects(config_dir=str(config), stream=io.StringIO())

    assert removed == [mine]
    assert not os.path.exists(mine)


def test_the_sweep_finds_the_directories_of_the_old_layout(tmp_path, monkeypatch):
    """A machine that ran the suite before still has these outside the repo."""
    config = tmp_path / 'claude'
    legacy = tmp_path / 'tmp' / 'smoke'
    monkeypatch.setattr(workspaces, 'LEGACY_ROOTS', (str(legacy),))
    old = _project_entry(str(config), str(legacy / 'test_x' / 'project'))

    assert workspaces.sweep_claude_projects(config_dir=str(config), stream=io.StringIO()) == [old]


def test_the_sweep_cannot_name_anything_outside_a_test_run(tmp_path, runs_root):
    """It deletes outside the repository, so its guard is the whole safety."""
    config = tmp_path / 'claude'
    theirs = _project_entry(str(config), '/Users/someone/Develop/real-project')
    mine = _project_entry(str(config), str(_run_dir(runs_root) / 'project'))

    removed = workspaces.sweep_claude_projects(config_dir=str(config), stream=io.StringIO())

    assert removed == [mine]
    assert os.path.isdir(theirs), 'a real project directory was in range'


def test_a_neighbour_of_the_runs_root_is_not_a_test_run(tmp_path, runs_root):
    """
    Mangling maps `/` and `-` alike, so a prefix rule reaches too far.

    `<repo>/test-runs-archive/project` keys with every character the runs root
    keys with, and the sweep deletes what it names. What separates them is the
    run stamp, which a directory this suite did not create does not carry.
    """
    config = tmp_path / 'claude'
    sibling = runs_root.parent / (runs_root.name + '-archive')
    theirs = _project_entry(str(config), str(sibling / 'project'))
    nested = _project_entry(str(config), str(sibling / '2026' / 'notes' / 'project'))
    mine = _project_entry(str(config), str(_run_dir(runs_root) / 'project'))

    removed = workspaces.sweep_claude_projects(config_dir=str(config), stream=io.StringIO())

    assert removed == [mine]
    assert os.path.isdir(theirs), 'a neighbouring project directory was in range'
    assert os.path.isdir(nested), "a neighbour's own subtree was in range"


def test_a_neighbour_of_the_old_layouts_root_is_not_a_test_run(tmp_path, monkeypatch):
    config = tmp_path / 'claude'
    legacy = tmp_path / 'tmp' / 'smoke'
    monkeypatch.setattr(workspaces, 'LEGACY_ROOTS', (str(legacy),))
    theirs = _project_entry(str(config), str(legacy.parent / 'smoke-reports' / 'project'))

    assert workspaces.sweep_claude_projects(config_dir=str(config), stream=io.StringIO()) == []
    assert os.path.isdir(theirs), 'a neighbouring project directory was in range'


def test_the_sweep_says_what_it_deleted(tmp_path, runs_root):
    """Deleting outside the repository has to be readable, not inferred."""
    config = tmp_path / 'claude'
    mine = _project_entry(str(config), str(_run_dir(runs_root) / 'project'))
    stream = io.StringIO()

    workspaces.sweep_claude_projects(config_dir=str(config), stream=stream)

    assert mine in stream.getvalue()
    assert 'removed 1 test-run project directory' in stream.getvalue()


def test_the_sweep_is_quiet_when_there_is_nothing_to_do(tmp_path):
    config = tmp_path / 'claude'
    assert workspaces.sweep_claude_projects(config_dir=str(config), stream=io.StringIO()) == []
