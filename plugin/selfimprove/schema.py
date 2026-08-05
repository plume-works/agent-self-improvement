"""
Validation of reviewer output against ``reviewer/schema.json``.

A deliberately small subset of JSON Schema — types, enums, required keys, and
length bounds — is enough for a flat ten-field contract. Depending on a schema
package here would put a compiled extension in a hook path for no gain; see
spec section 4.1.

Every rejection reason is a bounded category rather than a message, so a
malformed reviewer response can be recorded without persisting its contents.
"""

import json
import os

from . import paths

DISCARD = 'discard'
PROPOSE = 'propose'


class SchemaError(Exception):
    """Raised with a bounded reason category, never with model output."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def load_schema(path=None):
    path = path or os.path.join(paths.plugin_root(), 'reviewer', 'schema.json')
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def extract_json(text):
    """
    Recover the JSON object from a model response.

    Models wrap structured output in prose or fences more often than not, so a
    strict parse alone would discard usable answers. Anything that still fails
    to yield one object is a schema violation.
    """
    if text is None:
        raise SchemaError('empty_response')
    text = text.strip()
    if not text:
        raise SchemaError('empty_response')

    try:
        return _require_object(json.loads(text))
    except ValueError:
        pass

    fenced = _strip_code_fence(text)
    if fenced is not None:
        try:
            return _require_object(json.loads(fenced))
        except ValueError:
            pass

    candidate = _first_balanced_object(text)
    if candidate is None:
        raise SchemaError('not_json')
    try:
        return _require_object(json.loads(candidate))
    except ValueError as exc:
        raise SchemaError('not_json') from exc


def _require_object(value):
    if not isinstance(value, dict):
        raise SchemaError('not_an_object')
    return value


def _strip_code_fence(text):
    if not text.startswith('```'):
        return None
    newline = text.find('\n')
    if newline == -1:
        return None
    closing = text.rfind('```')
    if closing <= newline:
        return None
    return text[newline + 1 : closing].strip()


def _first_balanced_object(text):
    """The first brace-balanced object in the text, ignoring braces in strings."""
    start = text.find('{')
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def validate(payload, schema=None):
    """
    Return a normalized reviewer result, or raise :class:`SchemaError`.

    A ``discard`` decision is accepted with no further fields; the reviewer is
    expected to discard most turns and should not have to justify doing so.

    It may name a category, and that category is carried through so the outcome
    can be journaled. It is never required and never fatal: an absent or
    unrecognized value is dropped and the discard still stands. A reviewer that
    declined must not have its decision turned into a schema failure by the way
    it explained itself.
    """
    schema = schema or load_schema()
    properties = schema['properties']

    if not isinstance(payload, dict):
        raise SchemaError('not_an_object')

    unknown = sorted(set(payload) - set(properties))
    if unknown:
        raise SchemaError('unknown_field')

    decision = payload.get('decision')
    if decision not in properties['decision']['enum']:
        raise SchemaError('bad_decision')
    if decision == DISCARD:
        result = {'decision': DISCARD}
        reason = payload.get('discard_reason')
        if reason in properties['discard_reason']['enum']:
            result['discard_reason'] = reason
        return result

    result = {'decision': PROPOSE}
    for field in schema['requiredWhenProposing']:
        if field not in payload:
            raise SchemaError('missing_field')
        result[field] = _check_field(field, payload[field], properties[field])

    if result['confidence'] not in schema['acceptedConfidence']:
        # Spec section 7.4: low confidence becomes a discard rather than a
        # proposal the user has to evaluate and refuse.
        raise SchemaError('low_confidence')
    return result


def _check_field(name, value, rule):
    if rule['type'] == 'string':
        if not isinstance(value, str):
            raise SchemaError('bad_type')
        value = value.strip()
        if 'enum' in rule and value not in rule['enum']:
            raise SchemaError('bad_enum')
        if len(value) < rule.get('minLength', 1):
            raise SchemaError('too_short')
        if len(value) > rule.get('maxLength', 10000):
            raise SchemaError('too_long')
        return value
    raise SchemaError('unsupported_type')
