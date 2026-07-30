"""A stand-in for the ``claude`` binary during tests.

Installed as ``SELF_IMPROVE_REVIEWER_CMD`` so the reviewer code path runs
end to end — argument vector, environment, subprocess, envelope parsing — with
a deterministic answer instead of a model call.

The behavior is chosen by ``FAKE_REVIEWER_MODE``:

    propose        a valid proposal
    discard        a valid discard
    malformed      prose that contains no JSON object
    fenced         a valid proposal wrapped in a code fence
    chatty         a valid proposal surrounded by prose
    unknown_field  schema-valid JSON with an unexpected key
    low_confidence a proposal the schema must downgrade to a discard
    timeout        sleeps past any reasonable timeout
    crash          exits non-zero
    unauthorized   exits non-zero with an authentication message
    rate_limited   exits non-zero with a 429 envelope
    overloaded     exits zero with a 529 envelope, as the CLI does
    provider_error exits non-zero with a 500 and no explanatory text
    bad_model      exits zero reporting an inaccessible model
    empty          prints nothing

``FAKE_REVIEWER_ARGV`` and ``FAKE_REVIEWER_STDIN``, when set to paths, capture
the invocation so tests can assert on isolation flags and bundle contents.
"""

import json
import os
import sys
import time

PROPOSAL = {
    "decision": "propose",
    "signal_type": "explicit_correction",
    "evidence_summary": "The user corrected the test command twice in one turn.",
    "lesson": "Run the suite with `make test`, not by invoking pytest directly.",
    "applicability": "Whenever running tests in this repository.",
    "counterexample": "Not when debugging a single test in isolation.",
    "destination_scope": "project",
    "destination_kind": "CLAUDE.md",
    "owner_query": "test command make pytest",
    "confidence": "high",
}


def _record():
    argv_path = os.environ.get("FAKE_REVIEWER_ARGV")
    if argv_path:
        with open(argv_path, "w", encoding="utf-8") as handle:
            json.dump(sys.argv[1:], handle)
    stdin_path = os.environ.get("FAKE_REVIEWER_STDIN")
    if stdin_path:
        with open(stdin_path, "w", encoding="utf-8") as handle:
            handle.write(sys.stdin.read())
    elif not sys.stdin.isatty():
        sys.stdin.read()


def _envelope(text):
    return json.dumps({"type": "result", "is_error": False, "result": text})


def _api_error(status, text):
    """The shape the CLI prints when the call inside it failed.

    Real envelopes also carry durations and token counts; the numbers are kept
    here because a classifier that reads bare digits would trip over them.
    """
    return json.dumps({"type": "result", "is_error": True, "subtype": "success",
                       "terminal_reason": "api_error", "api_error_status": status,
                       "duration_ms": 529, "num_turns": 1, "result": text})


def main():
    mode = os.environ.get("FAKE_REVIEWER_MODE", "discard")
    _record()

    if mode == "timeout":
        time.sleep(30)
        return 0
    if mode == "crash":
        sys.stderr.write("reviewer exploded\n")
        return 1
    if mode == "unauthorized":
        sys.stderr.write("Invalid API key. Please run /login.\n")
        return 1
    if mode == "rate_limited":
        sys.stdout.write(_api_error(429, "API Error: 429 rate_limit_error"))
        return 1
    if mode == "overloaded":
        sys.stdout.write(_api_error(529, "API Error: 529 overloaded_error"))
        return 0
    if mode == "provider_error":
        sys.stdout.write(_api_error(500, "something went wrong"))
        return 1
    if mode == "bad_model":
        sys.stdout.write(_api_error(
            404, "There's an issue with the selected model (sonnet-9). It may "
                 "not exist or you may not have access to it."))
        return 0
    if mode == "empty":
        return 0

    if mode == "propose":
        body = json.dumps(PROPOSAL)
    elif mode == "discard":
        body = json.dumps({"decision": "discard"})
    elif mode == "malformed":
        body = "I looked at the turn and honestly nothing stood out to me."
    elif mode == "fenced":
        body = "```json\n%s\n```" % json.dumps(PROPOSAL, indent=2)
    elif mode == "chatty":
        body = ("Here is my assessment:\n\n%s\n\nHope that helps."
                % json.dumps(PROPOSAL))
    elif mode == "unknown_field":
        payload = dict(PROPOSAL, extra_field="not in the contract")
        body = json.dumps(payload)
    elif mode == "low_confidence":
        body = json.dumps(dict(PROPOSAL, confidence="low"))
    else:
        body = json.dumps({"decision": "discard"})

    sys.stdout.write(_envelope(body))
    return 0


if __name__ == "__main__":
    sys.exit(main())
