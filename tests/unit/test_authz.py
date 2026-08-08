"""
One-time authorization from a literal user command (spec section 5.2).

The property under test is that only a typed slash command from this plugin
creates an authorization, and that each one works exactly once.
"""

import pytest

from selfimprove import authz, store

EVENT = {
    'hook_event_name': 'UserPromptExpansion',
    'session_id': 'session-1',
    'expansion_type': 'slash_command',
    'command_source': 'plugin',
    'command_name': 'apply',
    'command_args': 'prop-abc123 0123456789ab',
}


@pytest.mark.parametrize(
    'name',
    [
        'apply',
        'self-improve:apply',
        '/apply',
        'APPLY',
        ' apply ',
    ],
)
def test_command_names_map_to_operations(name):
    assert authz.operation_from_command_name(name) == authz.APPLY


@pytest.mark.parametrize(
    'name',
    [
        'improve',
        'deploy',
        'other-plugin:apply',
        '',
        None,
        'applying',
    ],
)
def test_unrelated_command_names_do_not_map(name):
    assert authz.operation_from_command_name(name) is None


def test_a_typed_plugin_slash_command_is_accepted():
    assert authz.accepts(EVENT) == authz.APPLY


def test_an_mcp_prompt_expansion_is_rejected():
    assert authz.accepts(dict(EVENT, expansion_type='mcp_prompt')) is None


def test_an_expansion_from_another_source_is_rejected():
    """Only this plugin's own commands authorize its mutations."""
    assert authz.accepts(dict(EVENT, command_source='user')) is None
    assert authz.accepts(dict(EVENT, command_source='project')) is None


def test_an_unrelated_command_is_rejected():
    assert authz.accepts(dict(EVENT, command_name='deploy')) is None


@pytest.mark.parametrize(
    ('operation', 'args', 'expected'),
    [
        (
            authz.APPLY,
            'prop-1 abc123def456',
            {'proposal_id': 'prop-1', 'hash_prefix': 'abc123def456'},
        ),
        (authz.REJECT, 'prop-1', {'proposal_id': 'prop-1'}),
        (authz.ROLLBACK, 'mut-1', {'mutation_id': 'mut-1'}),
    ],
)
def test_arguments_are_parsed(operation, args, expected):
    assert authz.parse_arguments(operation, args) == expected


@pytest.mark.parametrize(
    ('operation', 'args'),
    [
        (authz.APPLY, 'prop-1'),
        (authz.APPLY, ''),
        (authz.APPLY, 'prop-1 abc extra'),
        (authz.REJECT, ''),
        (authz.REJECT, 'prop-1 prop-2'),
        (authz.ROLLBACK, ''),
    ],
)
def test_malformed_arguments_are_refused(operation, args):
    with pytest.raises(authz.AuthorizationError):
        authz.parse_arguments(operation, args)


def test_hash_prefix_is_normalized_to_lowercase():
    parsed = authz.parse_arguments(authz.APPLY, 'prop-1 ABC123DEF456')
    assert parsed['hash_prefix'] == 'abc123def456'


def test_a_granted_authorization_is_consumable_once(state_root):
    authz.grant(EVENT, authz.APPLY, {'proposal_id': 'prop-abc123', 'hash_prefix': '0123456789ab'})

    claimed = authz.consume(
        authz.APPLY, session_id='session-1', proposal_id='prop-abc123', hash_prefix='0123456789ab'
    )
    assert claimed['operation'] == authz.APPLY

    with pytest.raises(authz.AuthorizationError):
        authz.consume(
            authz.APPLY,
            session_id='session-1',
            proposal_id='prop-abc123',
            hash_prefix='0123456789ab',
        )


def test_consumption_requires_the_matching_proposal(state_root):
    authz.grant(EVENT, authz.APPLY, {'proposal_id': 'prop-abc123', 'hash_prefix': '0123456789ab'})
    with pytest.raises(authz.AuthorizationError):
        authz.consume(authz.APPLY, proposal_id='prop-different', hash_prefix='0123456789ab')


def test_consumption_requires_the_matching_hash_prefix(state_root):
    """An authorization for one set of bytes cannot install another."""
    authz.grant(EVENT, authz.APPLY, {'proposal_id': 'prop-abc123', 'hash_prefix': '0123456789ab'})
    with pytest.raises(authz.AuthorizationError):
        authz.consume(authz.APPLY, proposal_id='prop-abc123', hash_prefix='ffffffffffff')


def test_consumption_requires_the_matching_operation(state_root):
    authz.grant(EVENT, authz.APPLY, {'proposal_id': 'prop-abc123', 'hash_prefix': '0123456789ab'})
    with pytest.raises(authz.AuthorizationError):
        authz.consume(authz.REJECT, proposal_id='prop-abc123')


def test_consumption_is_scoped_to_the_granting_session(state_root):
    authz.grant(EVENT, authz.APPLY, {'proposal_id': 'prop-abc123', 'hash_prefix': '0123456789ab'})
    with pytest.raises(authz.AuthorizationError):
        authz.consume(
            authz.APPLY,
            session_id='a-different-session',
            proposal_id='prop-abc123',
            hash_prefix='0123456789ab',
        )


def test_an_expired_authorization_cannot_be_consumed(state_root, monkeypatch):
    """Ten minutes, enforced on read rather than waiting for a sweep."""
    from selfimprove import config

    monkeypatch.setattr(config, 'AUTHORIZATION_TTL', -1)
    authz.grant(EVENT, authz.APPLY, {'proposal_id': 'prop-abc123', 'hash_prefix': '0123456789ab'})
    with pytest.raises(authz.AuthorizationError):
        authz.consume(authz.APPLY, proposal_id='prop-abc123', hash_prefix='0123456789ab')


def test_no_authorization_at_all_is_refused(state_root):
    with pytest.raises(authz.AuthorizationError) as caught:
        authz.consume(authz.APPLY, proposal_id='prop-abc123', hash_prefix='0123456789ab')
    assert caught.value.reason == 'no_matching_authorization'


def test_the_record_is_removed_from_disk_when_claimed(state_root):
    record = authz.grant(
        EVENT, authz.APPLY, {'proposal_id': 'prop-abc123', 'hash_prefix': '0123456789ab'}
    )
    authz.consume(authz.APPLY, proposal_id='prop-abc123', hash_prefix='0123456789ab')
    assert store.read_record(store.AUTHORIZATIONS, record['nonce'], allow_expired=True) is None
