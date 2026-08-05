"""Reviewer output validation (spec section 7.4).

Malformed output, low confidence, unsupported destinations, and policy
violations all become a discard. Nothing here may let unvalidated model output
reach the proposal path.
"""

import json

import pytest

from selfimprove import schema
from tests.fake_reviewer import PROPOSAL


def test_accepts_a_well_formed_proposal():
    result = schema.validate(dict(PROPOSAL))
    assert result["decision"] == schema.PROPOSE
    assert result["lesson"].startswith("Run the suite")


def test_accepts_a_bare_discard():
    """The reviewer discards most turns and should not have to justify it."""
    assert schema.validate({"decision": "discard"}) == {"decision": "discard"}


def test_a_discard_may_name_a_category_and_it_is_carried_through():
    """The category is what makes a decline legible after the session ends.

    Without it a clean discard is indistinguishable from a reviewer that was
    never reached: same absent candidate, same absent diagnostics, same
    incremented counter.
    """
    result = schema.validate({"decision": "discard", "discard_reason": "inferred_not_stated"})
    assert result == {"decision": "discard", "discard_reason": "inferred_not_stated"}


@pytest.mark.parametrize("reason", ["made_up", "", None, 7, {"a": 1}])
def test_an_unrecognized_discard_category_is_dropped_not_fatal(reason):
    """A decline must never become a schema failure over how it was labelled.

    The label is journal decoration; the decision is the answer. Rejecting the
    object would turn a correct discard into a `SchemaError`, which is both a
    worse diagnostic and a lie about what the reviewer said.
    """
    assert schema.validate({"decision": "discard", "discard_reason": reason}) == {"decision": "discard"}


def test_the_category_does_not_travel_with_a_proposal():
    """Nothing downstream should read a discard reason off an accepted lesson."""
    result = schema.validate(dict(PROPOSAL, discard_reason="no_durable_lesson"))
    assert "discard_reason" not in result


def test_low_confidence_is_rejected():
    with pytest.raises(schema.SchemaError) as caught:
        schema.validate(dict(PROPOSAL, confidence="low"))
    assert caught.value.reason == "low_confidence"


@pytest.mark.parametrize(
    "field",
    [
        "signal_type",
        "evidence_summary",
        "lesson",
        "applicability",
        "counterexample",
        "destination_scope",
        "destination_kind",
        "owner_query",
        "confidence",
    ],
)
def test_a_proposal_missing_any_required_field_is_rejected(field):
    payload = dict(PROPOSAL)
    del payload[field]
    with pytest.raises(schema.SchemaError) as caught:
        schema.validate(payload)
    assert caught.value.reason == "missing_field"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("decision", "maybe"),
        ("signal_type", "vibes"),
        ("destination_scope", "global"),
        ("destination_kind", "settings.json"),
        ("confidence", "certain"),
    ],
)
def test_values_outside_the_contract_are_rejected(field, value):
    payload = dict(PROPOSAL)
    payload[field] = value
    with pytest.raises(schema.SchemaError):
        schema.validate(payload)


def test_unsupported_destination_cannot_smuggle_in_a_target():
    """destination_kind is an enum precisely so settings.json cannot appear."""
    with pytest.raises(schema.SchemaError) as caught:
        schema.validate(dict(PROPOSAL, destination_kind="hooks.json"))
    assert caught.value.reason == "bad_enum"


def test_unknown_fields_are_rejected():
    with pytest.raises(schema.SchemaError) as caught:
        schema.validate(dict(PROPOSAL, target_path="/etc/passwd"))
    assert caught.value.reason == "unknown_field"


def test_non_string_values_are_rejected():
    with pytest.raises(schema.SchemaError) as caught:
        schema.validate(dict(PROPOSAL, lesson={"nested": "object"}))
    assert caught.value.reason == "bad_type"


def test_overlong_values_are_rejected():
    with pytest.raises(schema.SchemaError) as caught:
        schema.validate(dict(PROPOSAL, lesson="x" * 5000))
    assert caught.value.reason == "too_long"


def test_trivially_short_lesson_is_rejected():
    with pytest.raises(schema.SchemaError) as caught:
        schema.validate(dict(PROPOSAL, lesson="do it"))
    assert caught.value.reason == "too_short"


def test_values_are_stripped():
    result = schema.validate(dict(PROPOSAL, lesson="  " + PROPOSAL["lesson"] + "  "))
    assert result["lesson"] == PROPOSAL["lesson"]


def test_non_object_payload_is_rejected():
    with pytest.raises(schema.SchemaError):
        schema.validate(["decision", "propose"])


@pytest.mark.parametrize(
    "text",
    [
        json.dumps(PROPOSAL),
        "```json\n%s\n```" % json.dumps(PROPOSAL),
        "```\n%s\n```" % json.dumps(PROPOSAL),
        "Here is my answer:\n%s\nLet me know." % json.dumps(PROPOSAL),
    ],
)
def test_extract_json_recovers_the_object_from_common_wrappings(text):
    """Models wrap structured output more often than not."""
    assert schema.extract_json(text)["decision"] == "propose"


def test_extract_json_ignores_braces_inside_strings():
    payload = dict(PROPOSAL, lesson="Use ${VAR} syntax, never {bare} braces here")
    assert schema.extract_json("noise " + json.dumps(payload))["lesson"] == payload["lesson"]


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("", "empty_response"),
        (None, "empty_response"),
        ("   ", "empty_response"),
        ("no json here at all", "not_json"),
        ("[1, 2, 3]", "not_an_object"),
    ],
)
def test_extract_json_rejects_unusable_text(text, reason):
    with pytest.raises(schema.SchemaError) as caught:
        schema.extract_json(text)
    assert caught.value.reason == reason


def test_schema_file_and_validator_agree_on_required_fields():
    """The JSON file is the contract; the validator must not drift from it."""
    loaded = schema.load_schema()
    for field in loaded["requiredWhenProposing"]:
        assert field in loaded["properties"]
    assert set(loaded["properties"]) >= set(PROPOSAL)
