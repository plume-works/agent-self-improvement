"""Detecting retention requests, corrections, and confirmations in a prompt.

Deliberately a phrase match rather than a model call: the gate has to be cheap
enough to run on every turn, and a false positive here costs only a discarded
review. Patterns live in ``markers.json`` so they can be tuned and tested as
data.

A marker is permission to reflect, never proof that a lesson exists.
"""

import json
import os
import re

RETENTION = "retention"
CORRECTION = "correction"
CONFIRMATION = "confirmation"
KINDS = (RETENTION, CORRECTION, CONFIRMATION)

_cache = {}


def _load():
    from . import paths

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "markers.json")
    if not os.path.exists(path):
        path = os.path.join(paths.plugin_root(), "selfimprove", "markers.json")
    key = path
    if key not in _cache:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        _cache[key] = {
            kind: [re.compile(pattern, re.IGNORECASE | re.MULTILINE) for pattern in data.get(kind, [])]
            for kind in KINDS
        }
    return _cache[key]


def detect(prompt):
    """Which marker kinds appear in ``prompt``, as a sorted list.

    Only the kinds are returned, never the matched text: the caller records
    which category fired, and the prompt itself is held only in the ephemeral
    turn file when a marker justifies keeping it.
    """
    if not prompt or not isinstance(prompt, str):
        return []
    patterns = _load()
    return sorted(kind for kind in KINDS if any(pattern.search(prompt) for pattern in patterns[kind]))


def has_correction(markers):
    return CORRECTION in (markers or [])


def has_retention(markers):
    return RETENTION in (markers or [])


def has_confirmation(markers):
    return CONFIRMATION in (markers or [])


def justifies_keeping_prompt(markers):
    """Whether section 5.1 permits storing the prompt in the turn file.

    Only a correction or a retention request does. A confirmation on its own
    tells the reviewer nothing the event record does not already carry.
    """
    return has_correction(markers) or has_retention(markers)
