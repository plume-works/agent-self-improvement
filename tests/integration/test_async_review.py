"""
Automatic asynchronous review (spec sections 5.5 and 3.1).

The contract under test is the exit code: 0 stays silent, 2 wakes the session
with the message on stderr. Exit 2 must happen only for a valid, non-duplicate
candidate — everything else, including every reviewer failure, is silence.
"""

import json
import os

import pytest

from selfimprove import capture, gate, journal, orchestrate, proposals, schema, store
from tests.fake_reviewer import PROPOSAL

STOP = {
    'hook_event_name': 'Stop',
    'session_id': 'session-1',
    'prompt_id': 'prompt-1',
    'cwd': '/Users/example/project',
    'last_assistant_message': 'Switched to make test.',
    'stop_hook_active': False,
    'background_tasks': [],
    'session_crons': [],
}


@pytest.fixture
def corrected_turn(state_root, project):
    """Provide a turn carrying a correction, which is a supported signal."""
    event = dict(STOP, cwd=str(project))
    capture.record_prompt({**event, 'prompt': 'no, use make test instead'})
    return event


def run_stop(run_si, event, extra_env=None):
    return run_si('review-turn', stdin=json.dumps(event), env=extra_env or {})


def test_a_valid_candidate_wakes_the_session(run_si, corrected_turn, fake_reviewer):
    fake_reviewer.mode('propose')
    result = run_stop(run_si, corrected_turn)
    assert result.returncode == 2
    assert 'self-improve' in result.stderr
    assert PROPOSAL['lesson'] in result.stderr
    assert 'cand-' in result.stderr


def test_the_wake_message_forbids_editing_and_applying(run_si, corrected_turn, fake_reviewer):
    fake_reviewer.mode('propose')
    result = run_stop(run_si, corrected_turn)
    assert 'Do not edit any file yourself' in result.stderr
    assert 'only a command the user types can authorize' in result.stderr


def test_a_turn_with_no_signal_stays_silent(run_si, state_root, project, fake_reviewer):
    """The common case: nothing happened worth reflecting on."""
    fake_reviewer.mode('propose')
    event = dict(STOP, cwd=str(project))
    capture.record_prompt({**event, 'prompt': 'add a test for the parser'})
    result = run_stop(run_si, event)
    assert result.returncode == 0
    assert result.stderr == ''


def test_no_signal_means_the_reviewer_is_never_invoked(run_si, state_root, project, fake_reviewer):
    """The gate exists to avoid paying for a review."""
    fake_reviewer.mode('propose')
    event = dict(STOP, cwd=str(project))
    capture.record_prompt({**event, 'prompt': 'add a test'})
    run_stop(run_si, event)
    assert not os.path.exists(fake_reviewer.argv_file)


def test_no_signal_deletes_the_ephemeral_turn_data(run_si, state_root, project, fake_reviewer):
    fake_reviewer.mode('discard')
    event = dict(STOP, cwd=str(project))
    capture.record_prompt({**event, 'prompt': 'add a test'})
    run_stop(run_si, event)
    assert (
        store.read_record(store.TURNS, 'prompt-1', subdir='session-1', allow_expired=True) is None
    )


@pytest.mark.parametrize(
    'mode',
    [
        'discard',
        'malformed',
        'low_confidence',
        'unknown_field',
        'crash',
        'unauthorized',
        'empty',
    ],
)
def test_no_reviewer_outcome_but_a_proposal_wakes_the_session(
    run_si, corrected_turn, fake_reviewer, mode
):
    """Every reviewer failure mode is silence, not an error the user sees."""
    fake_reviewer.mode(mode)
    result = run_stop(run_si, corrected_turn)
    assert result.returncode == 0, result.stderr


def test_a_reviewer_timeout_stays_silent(run_si, corrected_turn, fake_reviewer):
    """Section 11: a timeout is silence plus a recorded error class."""
    fake_reviewer.mode('timeout')
    result = run_si(
        'review-turn', stdin=json.dumps(corrected_turn), env={'SELF_IMPROVE_REVIEW_TIMEOUT': '1'}
    )
    assert result.returncode == 0
    assert result.stderr == ''


@pytest.mark.parametrize(
    'suppressor',
    [
        {'stop_hook_active': True},
        {'background_tasks': [{'id': 'x', 'type': 'shell', 'status': 'running'}]},
        {'session_crons': [{'id': 'x', 'schedule': '* * * * *'}]},
    ],
)
def test_suppressors_prevent_the_wake(run_si, corrected_turn, fake_reviewer, suppressor):
    fake_reviewer.mode('propose')
    result = run_stop(run_si, dict(corrected_turn, **suppressor))
    assert result.returncode == 0


def test_a_reviewer_originated_session_never_reviews(run_si, corrected_turn, fake_reviewer):
    """Without this, a review could trigger a review."""
    fake_reviewer.mode('propose')
    result = run_stop(run_si, corrected_turn, {'SELF_IMPROVE_REVIEWER': '1'})
    assert result.returncode == 0


def test_a_second_stop_does_not_wake_again(run_si, corrected_turn, fake_reviewer):
    """
    The recursion guard for asyncRewake.

    Waking the session produces another turn and another Stop event. Without
    the awaiting flag this would loop.
    """
    fake_reviewer.mode('propose')
    assert run_stop(run_si, corrected_turn).returncode == 2

    capture.record_prompt({**corrected_turn, 'prompt': "no, that's wrong too"})
    assert run_stop(run_si, corrected_turn).returncode == 0


def test_presenting_the_candidate_lifts_the_guard(run_si, corrected_turn, fake_reviewer):
    fake_reviewer.mode('propose')
    result = run_stop(run_si, corrected_turn)
    candidate_id = next(
        word.strip('.') for word in result.stderr.split() if word.startswith('cand-')
    )

    shown = run_si('show-candidate', '--id', candidate_id)
    assert shown.returncode == 0
    assert gate.suppressed(corrected_turn) != 'candidate_awaiting_presentation'


def test_an_already_accepted_lesson_is_suppressed(run_si, corrected_turn, fake_reviewer):
    fake_reviewer.mode('propose')
    fingerprint = proposals.fingerprint(
        PROPOSAL['lesson'], PROPOSAL['destination_scope'], PROPOSAL['destination_kind']
    )
    journal.record_fingerprint(fingerprint, 'accepted')
    assert run_stop(run_si, corrected_turn).returncode == 0


def test_an_already_rejected_lesson_is_suppressed(run_si, corrected_turn, fake_reviewer):
    fake_reviewer.mode('propose')
    fingerprint = proposals.fingerprint(
        PROPOSAL['lesson'], PROPOSAL['destination_scope'], PROPOSAL['destination_kind']
    )
    journal.record_fingerprint(fingerprint, 'rejected', 'too_generic')
    assert run_stop(run_si, corrected_turn).returncode == 0


def test_a_suppressed_duplicate_says_so_in_the_journal(
    run_si, corrected_turn, fake_reviewer, state_root
):
    """
    A duplicate is the other outcome that is silent and leaves no candidate.

    It is the good case — the lesson is already known — but from state alone it
    reads exactly like a reviewer that proposed nothing, so it says which it was.
    """
    fake_reviewer.mode('propose')
    fingerprint = proposals.fingerprint(
        PROPOSAL['lesson'], PROPOSAL['destination_scope'], PROPOSAL['destination_kind']
    )
    journal.record_fingerprint(fingerprint, 'accepted')
    run_stop(run_si, corrected_turn)

    outcomes = [
        record for record in _diagnostics(state_root) if record['stage'] == 'review_outcome'
    ]
    assert [(record['error_class'], record['reason']) for record in outcomes] == [
        ('duplicate', 'accepted')
    ]


def test_the_candidate_is_queued_before_the_wake(run_si, corrected_turn, fake_reviewer, project):
    """A wake that never lands must still be recoverable."""
    fake_reviewer.mode('propose')
    run_stop(run_si, corrected_turn)
    waiting = orchestrate.pending_candidates(cwd=str(project))
    assert len(waiting) == 1


def test_session_start_surfaces_a_queued_candidate(run_si, corrected_turn, fake_reviewer, project):
    fake_reviewer.mode('propose')
    run_stop(run_si, corrected_turn)

    result = run_si(
        'session-start',
        stdin=json.dumps(
            {
                'hook_event_name': 'SessionStart',
                'session_id': 'session-2',
                'cwd': str(project),
                'source': 'startup',
            }
        ),
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    context = payload['hookSpecificOutput']['additionalContext']
    assert 'retained learning candidate' in context
    assert 'cand-' in context


def test_session_start_is_silent_with_nothing_queued(run_si, state_root, project):
    result = run_si(
        'session-start', stdin=json.dumps({'hook_event_name': 'SessionStart', 'cwd': str(project)})
    )
    assert result.returncode == 0
    assert result.stdout == ''


def test_review_never_persists_prompt_or_response_text(
    run_si, corrected_turn, fake_reviewer, state_root
):
    """Section 15 point 10, checked across the whole state root."""
    fake_reviewer.mode('propose')
    run_stop(run_si, corrected_turn)

    blob = []
    for dirpath, _dirs, files in os.walk(str(state_root)):
        for name in files:
            with open(os.path.join(dirpath, name), encoding='utf-8', errors='replace') as handle:
                blob.append(handle.read())
    combined = '\n'.join(blob)
    # Without this the assertions below would pass on an empty state root.
    assert 'cand-' in combined, 'expected a stored candidate to inspect'

    assert 'Switched to make test.' not in combined, 'assistant response persisted'
    assert 'no, use make test instead' not in combined, 'raw prompt persisted'


def test_forced_review_runs_the_same_pipeline(run_si, state_root, project, fake_reviewer):
    fake_reviewer.mode('propose')
    event = json.dumps({'session_id': 'session-9', 'cwd': str(project)})
    result = run_si('improve', '--focus', 'the deploy step', stdin=event)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload['outcome'] == 'candidate'
    assert payload['candidate']['signal'] == 'manual_force'


def test_forced_review_reports_when_there_is_no_lesson(run_si, state_root, project, fake_reviewer):
    fake_reviewer.mode('discard')
    event = json.dumps({'session_id': 'session-9', 'cwd': str(project)})
    result = run_si('improve', stdin=event)
    assert result.returncode == 0
    assert json.loads(result.stdout)['outcome'] == 'no_lesson'


def _diagnostics(state_root):
    path = os.path.join(str(state_root), 'diagnostics.jsonl')
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def test_a_declined_review_says_so_in_the_journal(
    run_si, corrected_turn, fake_reviewer, state_root
):
    """
    Verify that a decline leaves a trace distinct from a review that never ran.

    Both look identical in durable state otherwise: no candidate, no
    fingerprint, an incremented counter and a deleted turn. Diagnosing that
    difference used to mean re-running a live check that costs real model usage,
    and the re-run produced the same absence of evidence.
    """
    fake_reviewer.mode('discard')
    run_stop(run_si, corrected_turn)

    outcomes = [
        record for record in _diagnostics(state_root) if record['stage'] == 'review_outcome'
    ]
    assert len(outcomes) == 1, 'a review that ran left no outcome record'
    assert outcomes[0]['error_class'] == 'no_lesson'
    assert outcomes[0]['reason'] == 'one_off_instruction'


def test_a_decline_without_a_category_is_still_journaled(
    run_si, corrected_turn, fake_reviewer, state_root
):
    """The field is optional, so its absence must not cost the record."""
    fake_reviewer.mode('bare_discard')
    run_stop(run_si, corrected_turn)

    outcomes = [
        record for record in _diagnostics(state_root) if record['stage'] == 'review_outcome'
    ]
    assert [(record['error_class'], record['reason']) for record in outcomes] == [
        ('no_lesson', 'reviewer_discarded')
    ]


def test_the_journaled_reason_is_a_category_never_model_text(
    run_si, corrected_turn, fake_reviewer, state_root
):
    """
    Section 10: nothing durable may carry prose the reviewer wrote.

    The category is bounded precisely so the diagnostics file stays shareable
    without a transcript, which is the only reason it can be journaled at all.
    """
    fake_reviewer.mode('discard')
    run_stop(run_si, corrected_turn)

    reasons = {
        record['reason']
        for record in _diagnostics(state_root)
        if record['stage'] == 'review_outcome'
    }
    assert reasons <= set(schema.load_schema()['properties']['discard_reason']['enum'])


def test_a_review_that_never_reached_the_model_is_distinguishable(
    run_si, corrected_turn, fake_reviewer, state_root
):
    """
    The distinction the outcome record exists to draw.

    A transport failure and a considered decline both end as a discard, and the
    caller cannot tell them apart from the return value alone. In the journal
    they differ: the transport failure carries its own class as the reason.
    """
    fake_reviewer.mode('crash')
    run_stop(run_si, corrected_turn)

    outcomes = [
        record for record in _diagnostics(state_root) if record['stage'] == 'review_outcome'
    ]
    assert len(outcomes) == 1
    assert outcomes[0]['reason'] != 'reviewer_discarded', (
        'a reviewer that was never reached is being reported as a decline'
    )
