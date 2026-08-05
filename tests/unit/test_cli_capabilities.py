"""
Reporting a Claude Code version too old for the hook contract.

The machine this plugin was developed on ran v2.1.81, which has no
``UserPromptExpansion`` event at all. That is the whole authorization path, so
the failure has to be legible rather than silent.
"""

from selfimprove import commands


def test_no_warning_when_the_cli_is_new_enough(monkeypatch):
    monkeypatch.setattr(commands, 'cli_version', lambda: (2, 1, 200))
    assert commands.cli_capability_warnings() == []


def test_no_warning_when_the_cli_is_absent(monkeypatch):
    monkeypatch.setattr(commands, 'cli_version', lambda: None)
    assert commands.cli_capability_warnings() == []


def test_warns_and_names_the_consequence_on_an_old_cli(monkeypatch):
    monkeypatch.setattr(commands, 'cli_version', lambda: (2, 1, 81))
    warnings = commands.cli_capability_warnings()
    assert len(warnings) == 1
    assert '2.1.81' in warnings[0]
    assert 'UserPromptExpansion' in warnings[0]
    assert 'authorized' in warnings[0]


def test_version_parsing_ignores_surrounding_text(monkeypatch):
    class Result:
        stdout = '2.1.81 (Claude Code)\n'

    monkeypatch.setattr(commands.shutil, 'which', lambda name: '/usr/bin/claude')
    monkeypatch.setattr(commands.subprocess, 'run', lambda *a, **k: Result())
    assert commands.cli_version() == (2, 1, 81)


def test_version_is_none_when_the_cli_cannot_be_run(monkeypatch):
    monkeypatch.setattr(commands.shutil, 'which', lambda name: '/usr/bin/claude')

    def explode(*args, **kwargs):
        raise OSError('nope')

    monkeypatch.setattr(commands.subprocess, 'run', explode)
    assert commands.cli_version() is None
