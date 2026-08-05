"""
A self-check of the pty harness, driving a program that only echoes its input.

These test the harness, not the plugin: nothing here touches ``claude``, the
gate, or the reviewer. That is why they are marked ``harness`` rather than named
for the wake — the wake is what the harness is used to observe, not what these
checks observe.

The harness types blind. It never reads the screen to decide anything, which is
what keeps it uncoupled from an interface with no compatibility contract — and
what makes a stalled live run ambiguous. Either the session under test did not
do what was asked, or the input never arrived as input: wrong line ending, a
prompt folded into the turn already running, a dialog nobody answered.

These checks settle that half. They drive :mod:`tests.smoke.echo_terminal`, a
fake interactive program that echoes each captured line with a marker and can
emit an unprompted marker seconds later, and they assert the four things the
live checks depend on: input is delivered a line at a time, turn boundaries are
detected from quiescence, a marker arriving with nothing typed is seen, and one
that never arrives is not.

No model, no cost, nothing that can change underneath them — so unlike the live
checks these are ordinary tests and run in ``make test``. When a live check
stalls and these pass, the harness is delivering input and the stall is in the
session under test. ``make test-harness`` only reruns them alone, trace on.
"""

import os
import sys

import pytest

from tests.smoke.conftest import CORRECTION, FIRST_TURN
from tests.smoke.pty_harness import Deadline, PtySession, Trace

pytestmark = pytest.mark.harness


ECHO_COMMAND = [sys.executable, '-u', '-m', 'tests.smoke.echo_terminal']


def echo_session(deadline, extra=()):
    """
    Run a fake terminal through the harness used by the live checks.

    ``-u`` because a buffered fake would go quiet while it still had output to
    write, and the turn boundary here is quiescence.
    """
    environment = dict(os.environ)
    environment['PYTHONPATH'] = os.pathsep.join(
        [
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            environment.get('PYTHONPATH', ''),
        ]
    )
    return PtySession(
        [*ECHO_COMMAND, *extra], cwd=os.getcwd(), env=environment, deadline=deadline
    ).start()


def test_echo_mode_shows_every_captured_prompt(tmp_path):
    """
    Each line the harness types arrives as its own line, in order.

    This is the failure that is invisible in a live run: a prompt that never
    reached the session, or that was folded into the turn already running, and
    plugin state that looks the same either way.
    """
    trace = Trace('echo-capture', directory=tmp_path)
    deadline = Deadline(budget=60.0, trace=trace)
    session = echo_session(deadline)
    try:
        assert session.wait_until_quiet(quiet=1.0, timeout=15.0, label='startup')
        for index, text in enumerate([FIRST_TURN, CORRECTION], start=1):
            session.send_line(text)
            assert session.wait_until_quiet(quiet=1.0, timeout=15.0, label='turn-%d' % index), (
                'the echo terminal never went quiet after turn %d' % index
            )
            trace.echo('turn-%d' % index, session.screen())
            assert session.contains('captured[%d]: %s' % (index, text)), (
                'turn %d was not captured as its own line:\n%s' % (index, session.tail())
            )
        status = session.close()
    finally:
        if session.process is not None and session.process.poll() is None:
            session.close()
    assert status == 0, 'the echo terminal did not exit cleanly (%r)' % (status,)
    assert (tmp_path / 'echo-capture.pty.log').read_text(), (
        'the raw terminal stream was not recorded'
    )


def test_echo_mode_sees_a_marker_that_arrives_with_nothing_typed(tmp_path):
    """
    An unprompted marker is detected: the shape of the wake, without a model.

    ``watch`` keeps reading while typing nothing, which is exactly what the live
    check does after its last turn. If this fails, a missing wake in the live
    check says nothing about the plugin.
    """
    marker = 'cand-echo0123456789'
    trace = Trace('echo-wake', directory=tmp_path)
    deadline = Deadline(budget=60.0, trace=trace)
    session = echo_session(
        deadline, extra=['--wake-after', '3', '--wake-text', 'self-improve: candidate ' + marker]
    )
    try:
        assert session.wait_until_quiet(quiet=1.0, timeout=15.0, label='startup')
        session.send_line(FIRST_TURN)
        assert session.wait_until_quiet(quiet=1.0, timeout=15.0, label='turn-1')
        assert not session.contains(marker), (
            'the marker arrived during the turn, so its arrival proves nothing'
        )
        woke = session.watch(
            lambda: session.contains(marker), timeout=20.0, label='wake-on-screen'
        )
        trace.echo('after-wake', session.screen())
        status = session.close()
    finally:
        if session.process is not None and session.process.poll() is None:
            session.close()
    assert woke, 'an unprompted marker was never seen:\n%s' % session.tail()
    assert status == 0, 'the echo terminal did not exit cleanly (%r)' % (status,)


def test_echo_mode_does_not_invent_a_marker_that_never_arrives():
    """
    The negative half: with nothing sending a marker, none is seen.

    A ``contains`` that answered yes regardless would make the live wake check
    pass without a wake, and the live control is expensive enough that this
    needs to be settled here.
    """
    deadline = Deadline(budget=30.0)
    session = echo_session(deadline)
    try:
        assert session.wait_until_quiet(quiet=1.0, timeout=15.0, label='startup')
        session.send_line(FIRST_TURN)
        assert session.wait_until_quiet(quiet=1.0, timeout=15.0, label='turn-1')
        assert not session.watch(
            lambda: session.contains('cand-neverarrives'), timeout=3.0, label='wake-on-screen'
        )
        status = session.close()
    finally:
        if session.process is not None and session.process.poll() is None:
            session.close()
    assert status == 0
