"""Correction and retention detection.

A phrase match, not a model call, because the gate runs on every turn. The tests
that matter most are the negative ones: a false positive here wakes a reviewer
for nothing.
"""

import pytest

from selfimprove import markers


@pytest.mark.parametrize("prompt", [
    "remember this for next time",
    "please don't forget the migration step",
    "from now on use uv",
    "always run make test before committing",
    "never commit directly to main",
    "add this to your CLAUDE.md",
    "going forward, prefer the shorter form",
    "keep this in mind when editing schemas",
])
def test_retention_requests_are_detected(prompt):
    assert markers.RETENTION in markers.detect(prompt)


@pytest.mark.parametrize("prompt", [
    "always prefer uv",
    "never push to main",
    "always format with black",
    "no, always use `make test` in this repo, not pytest directly",
    "use uv, and never call pip directly",
    "fix the imports, then always sort them",
])
def test_a_standing_directive_is_a_retention_request_whatever_verb_follows(prompt):
    """`always` and `never` are not tied to a list of blessed verbs.

    A user who says "always format with black" is stating a rule as plainly as
    one who says "always run make test", and the gate that only knew a handful
    of verbs decided the difference for them. It is the standing scope that
    makes this a lesson, not the particular word after it.
    """
    assert markers.RETENTION in markers.detect(prompt)


@pytest.mark.parametrize("prompt", [
    "the build always fails on CI",
    "that never worked",
    "the flag was never set",
    "this is always the case",
    "tests never seem to pass",
    "I have never seen that",
])
def test_always_and_never_describing_the_world_are_not_directives(prompt):
    """The other half of widening the pattern, and the expensive half to get wrong.

    "the build always fails" is a report, not a rule, and reviewing it costs a
    real model call. Only a clause that opens with the adverb is read as an
    instruction.
    """
    assert markers.RETENTION not in markers.detect(prompt)


@pytest.mark.parametrize("prompt", [
    "no, that's the wrong directory",
    "actually, use the staging config",
    "that's wrong",
    "instead of pytest, run make test",
    "don't use npm here",
    "that didn't work, try again",
    "the wrong branch was checked out",
    "undo that change please",
])
def test_corrections_are_detected(prompt):
    assert markers.CORRECTION in markers.detect(prompt)


@pytest.mark.parametrize("prompt", [
    "that worked, thanks",
    "yes, that did it",
    "thanks, that fixed it",
])
def test_confirmations_are_detected(prompt):
    assert markers.CONFIRMATION in markers.detect(prompt)


@pytest.mark.parametrize("prompt", [
    "add a test for the parser",
    "what does this function do?",
    "refactor the handler to use async",
    "the build is failing on CI",
    "show me the diff",
    "run the tests",
    "explain how routing works",
    "I need to remember to call my mother",
    "",
    None,
])
def test_ordinary_prompts_produce_no_markers(prompt):
    """False positives cost a wasted review, so the negative cases matter most."""
    assert markers.detect(prompt) == []


def test_a_prompt_can_carry_several_markers():
    found = markers.detect("no, that's wrong. from now on always use make test")
    assert markers.CORRECTION in found
    assert markers.RETENTION in found


def test_detection_is_case_insensitive():
    assert markers.detect("REMEMBER THIS") == markers.detect("remember this")


def test_only_categories_are_returned():
    """The prompt text must not travel with the detection result."""
    found = markers.detect("remember this: the token is ghp_secret")
    assert found == [markers.RETENTION]
    assert all(kind in markers.KINDS for kind in found)


@pytest.mark.parametrize(("found", "expected"), [
    ([markers.CORRECTION], True),
    ([markers.RETENTION], True),
    ([markers.CONFIRMATION], False),
    ([], False),
    (None, False),
])
def test_only_corrections_and_retention_justify_keeping_the_prompt(found, expected):
    """Section 5.1 permits the prompt only for those two cases."""
    assert markers.justifies_keeping_prompt(found) is expected


def test_patterns_are_valid_and_present():
    loaded = markers._load()
    for kind in markers.KINDS:
        assert loaded[kind], "no patterns configured for %s" % kind
