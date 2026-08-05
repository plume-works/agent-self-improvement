"""State root resolution, permissions, and atomic installation."""

import os
import threading

import pytest
from selfimprove import paths


def test_state_root_prefers_the_explicit_override(tmp_path, monkeypatch):
    """
    The override must win over the value Claude Code injects into hooks.

    Claude Code sets ``CLAUDE_PLUGIN_DATA`` in every hook environment, replacing
    an inherited one, so the other order leaves the override with no effect on
    the hooks that write state.
    """
    monkeypatch.setenv('CLAUDE_PLUGIN_DATA', str(tmp_path / 'data'))
    monkeypatch.setenv('SELF_IMPROVE_STATE_DIR', str(tmp_path / 'override'))
    assert paths.state_root() == str(tmp_path / 'override')


def test_state_root_falls_back_to_plugin_data_then_claude_home(tmp_path, monkeypatch):
    monkeypatch.delenv('SELF_IMPROVE_STATE_DIR', raising=False)
    monkeypatch.setenv('CLAUDE_PLUGIN_DATA', str(tmp_path / 'data'))
    assert paths.state_root() == str(tmp_path / 'data')

    monkeypatch.delenv('CLAUDE_PLUGIN_DATA', raising=False)
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(tmp_path / 'claude'))
    assert paths.state_root() == str(tmp_path / 'claude' / 'self-improvement')


def test_state_root_expands_user(tmp_path, monkeypatch):
    monkeypatch.delenv('CLAUDE_PLUGIN_DATA', raising=False)
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('SELF_IMPROVE_STATE_DIR', '~/somewhere')
    assert paths.state_root() == str(tmp_path / 'somewhere')


def test_ensure_dir_creates_private_directory(tmp_path):
    target = tmp_path / 'a' / 'b'
    paths.ensure_dir(str(target))
    assert os.stat(target).st_mode & 0o777 == paths.DIR_MODE


def test_ensure_dir_narrows_a_permissive_existing_directory(tmp_path):
    target = tmp_path / 'wide'
    target.mkdir(mode=0o755)
    paths.ensure_dir(str(target))
    assert os.stat(target).st_mode & 0o777 == paths.DIR_MODE


def test_atomic_write_creates_private_file(tmp_path):
    target = tmp_path / 'nested' / 'file.json'
    paths.atomic_write(str(target), 'payload')
    assert target.read_text() == 'payload'
    assert os.stat(target).st_mode & 0o777 == paths.FILE_MODE


def test_atomic_write_accepts_bytes_and_replaces_contents(tmp_path):
    target = tmp_path / 'file'
    paths.atomic_write(str(target), b'first')
    paths.atomic_write(str(target), b'second')
    assert target.read_bytes() == b'second'


def test_atomic_write_leaves_no_temporary_file_behind(tmp_path):
    target = tmp_path / 'file'
    paths.atomic_write(str(target), 'x')
    leftovers = [n for n in os.listdir(tmp_path) if n.startswith('.si-tmp-')]
    assert leftovers == []


def test_atomic_write_cleans_up_when_writing_fails(tmp_path):
    class Exploding:
        def __len__(self):
            raise RuntimeError('boom')

    target = tmp_path / 'file'
    with pytest.raises((RuntimeError, TypeError)):
        paths.atomic_write(str(target), Exploding())
    leftovers = [n for n in os.listdir(tmp_path) if n.startswith('.si-tmp-')]
    assert leftovers == []
    assert not target.exists()


def test_reader_never_observes_a_partial_write(tmp_path):
    """
    The point of the temp-file-and-rename dance.

    A reader polling during repeated rewrites must only ever see one of the two
    complete payloads, never a prefix of the longer one.
    """
    target = tmp_path / 'file'
    short, long = b'a' * 64, b'b' * 65536
    paths.atomic_write(str(target), short)
    observed = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                observed.append(target.read_bytes())
            except (OSError, FileNotFoundError):
                continue

    thread = threading.Thread(target=reader)
    thread.start()
    try:
        for index in range(40):
            paths.atomic_write(str(target), long if index % 2 else short)
    finally:
        stop.set()
        thread.join()

    assert observed, 'reader never sampled the file'
    assert set(observed) <= {short, long}


def test_state_path_creates_parents(tmp_path, monkeypatch):
    monkeypatch.delenv('CLAUDE_PLUGIN_DATA', raising=False)
    monkeypatch.setenv('SELF_IMPROVE_STATE_DIR', str(tmp_path / 'state'))
    path = paths.state_path('turns', 'session', 'turn.json')
    assert os.path.isdir(os.path.dirname(path))
