"""Real isolated MySQL transactions; WeChat transport alone is substituted."""
import asyncio
import uuid

import pytest
from fastapi import HTTPException

from app.core.auth import decode_token
from app.services import identity_service as identity
from app.services.account_service import AccountCredentials, authenticate
from app.repositories.rag_index_repository import transaction


@pytest.mark.asyncio
async def test_direct_binding_checks_password_ownership_and_idempotent_session_version(users):
    from app.services.account_service import hash_password
    password = 'Native-bind-isolated-123'
    async with transaction() as cur:
        await cur.execute('INSERT INTO account_credentials VALUES(%s,%s,%s,UTC_TIMESTAMP())',
                          ('native_' + uuid.uuid4().hex[:15], users[0], hash_password(password)))
        await cur.execute('SELECT openid FROM users WHERE id=%s', (users[1],))
        occupied = (await cur.fetchone())['openid']
    new_openid = 'native_' + uuid.uuid4().hex
    initial = await identity.session_version(users[0])
    with pytest.raises(HTTPException) as denied:
        await identity.direct_bind(users[0], new_openid, password='wrong-password')
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException) as conflict:
        await identity.direct_bind(users[0], occupied, password=password)
    assert conflict.value.status_code == 409
    assert await identity.session_version(users[0]) == initial
    result = await identity.direct_bind(users[0], new_openid, password=password)
    assert result['user']['id'] == users[0]
    version = await identity.session_version(users[0])
    assert version == initial + 1
    replay = await identity.direct_bind(users[0], new_openid, password=password)
    assert replay['user']['id'] == users[0]
    assert await identity.session_version(users[0]) == version


@pytest.mark.asyncio
async def test_unknown_wechat_choice_cancel_does_not_create_user(users):
    openid = 'wx_' + uuid.uuid4().hex
    result = await identity.begin_wechat(openid)
    assert result['status'] == 'choice' and 'token' not in result
    await identity.finish_wechat(result['ticket'], 'cancel')
    async with transaction() as cur:
        await cur.execute('SELECT id FROM users WHERE openid=%s', (openid,))
        assert await cur.fetchone() is None
    with pytest.raises(HTTPException):
        await identity.finish_wechat(result['ticket'], 'register')


@pytest.mark.asyncio
async def test_link_keeps_existing_data_identity_and_is_single_use(users):
    username = 'identity_' + uuid.uuid4().hex[:15]
    credentials = AccountCredentials(username=username, password='Correct-password-123')
    from app.services.account_service import hash_password
    async with transaction() as cur:
        await cur.execute('INSERT INTO account_credentials VALUES(%s,%s,%s,UTC_TIMESTAMP())',
                          (username, users[0], hash_password(credentials.password)))
        await cur.execute('UPDATE users SET openid=NULL WHERE id=%s', (users[0],))
    result = await identity.begin_wechat('new_' + uuid.uuid4().hex)
    responses = await asyncio.gather(*[identity.finish_wechat(result['ticket'], 'link', credentials) for _ in range(2)], return_exceptions=True)
    assert sum(isinstance(item, HTTPException) for item in responses) == 1
    success = next(item for item in responses if isinstance(item, dict))
    assert success['user']['id'] == users[0]
    assert decode_token(success['token'])['user_id'] == users[0]
    from app.core.auth import get_current_user, create_token
    from app.core.exceptions import AuthenticationError
    from types import SimpleNamespace
    with pytest.raises(AuthenticationError):
        await get_current_user(SimpleNamespace(headers={'Authorization': 'Bearer ' + create_token(users[0], '')}))


@pytest.mark.asyncio
async def test_recovery_code_single_use_revokes_previous_sessions(users):
    username = 'recovery_' + uuid.uuid4().hex[:15]
    credentials = AccountCredentials(username=username, password='Old-password-123')
    account = await authenticate(credentials, True, 'isolated-recovery')
    try:
        assert account.recovery_code
        await identity.reset_password(username, 'New-password-123', recovery_code=account.recovery_code)
        assert await identity.session_version(account.user.id) > decode_token(account.token).get('sv', 0)
        with pytest.raises(HTTPException):
            await identity.reset_password(username, 'Another-password-123', recovery_code=account.recovery_code)
        with pytest.raises(HTTPException):
            await authenticate(credentials, False, 'isolated-recovery')
        logged_in = await authenticate(credentials.model_copy(update={'password': 'New-password-123'}), False, 'isolated-recovery')
        assert decode_token(logged_in.token)['sv'] == await identity.session_version(account.user.id)
    finally:
        async with transaction() as cur:
            await cur.execute('DELETE FROM users WHERE id=%s', (account.user.id,))


@pytest.mark.asyncio
async def test_qr_requires_browser_secret_and_wechat_confirmation(users):
    async with transaction() as cur:
        await cur.execute('SELECT openid FROM users WHERE id=%s', (users[0],))
        openid = (await cur.fetchone())['openid']
    qr = await identity.create_qr('login')
    scanned = await identity.scan_qr(qr['scene'], openid)
    assert (await identity.poll_qr(qr['ticket']))['status'] == 'pending'
    with pytest.raises(HTTPException):
        await identity.poll_qr(qr['scene'] + '.wrong')
    await identity.approve_qr(scanned['ticket'], 'login')
    assert (await identity.poll_qr(qr['ticket']))['status'] == 'approved'
    result = await identity.consume_qr(qr['ticket'])
    assert result['user']['id'] == users[0]
    with pytest.raises(HTTPException):
        await identity.consume_qr(qr['ticket'])


@pytest.mark.asyncio
async def test_qr_registration_does_not_claim_an_undelivered_recovery_code(users):
    openid = 'qr_new_' + uuid.uuid4().hex
    credentials = AccountCredentials(username='qr_' + uuid.uuid4().hex[:15], password='Private-password-123')
    qr = await identity.create_qr('login')
    scan = await identity.scan_qr(qr['scene'], openid)
    await identity.approve_qr(scan['ticket'], 'register', credentials)
    result = await identity.consume_qr(qr['ticket'])
    try:
        profile = await identity.security_profile(result['user']['id'])
        assert profile['wechat_bound'] is True
        assert profile['recovery_ready'] is False
        code = await identity.renew_recovery(result['user']['id'], password=credentials.password)
        assert code['recovery_code']
        assert (await identity.security_profile(result['user']['id']))['recovery_ready'] is True
    finally:
        async with transaction() as cur:
            await cur.execute('DELETE FROM users WHERE id=%s', (result['user']['id'],))


@pytest.mark.asyncio
async def test_expired_proof_and_bound_wechat_cannot_be_stolen(users):
    qr = await identity.create_qr('bind', user_id=users[0])
    async with transaction() as cur:
        await cur.execute('SELECT openid FROM users WHERE id=%s', (users[1],))
        openid = (await cur.fetchone())['openid']
    scan = await identity.scan_qr(qr['scene'], openid)
    with pytest.raises(HTTPException):
        await identity.approve_qr(scan['ticket'], 'bind')
    async with transaction() as cur:
        await cur.execute('UPDATE identity_challenges SET expires_at=DATE_SUB(UTC_TIMESTAMP(),INTERVAL 1 SECOND) WHERE challenge_id=%s', (qr['scene'],))
    with pytest.raises(HTTPException):
        await identity.poll_qr(qr['ticket'])


@pytest.mark.asyncio
async def test_successful_rebind_revokes_old_identity_and_old_browser_session(users):
    old = 'old_' + uuid.uuid4().hex
    new = 'new_' + uuid.uuid4().hex
    async with transaction() as cur:
        await cur.execute('UPDATE users SET openid=%s WHERE id=%s', (old, users[0]))
    qr = await identity.authorized_bind_qr(users[0], openid=old)
    scanned = await identity.scan_qr(qr['scene'], new)
    await identity.approve_qr(scanned['ticket'], 'bind')
    result = await identity.consume_qr(qr['ticket'])
    assert result['user']['id'] == users[0]
    assert decode_token(result['token'])['sv'] == 1
    assert (await identity.begin_wechat(old))['status'] == 'choice'
    assert (await identity.begin_wechat(new))['user']['id'] == users[0]


@pytest.mark.asyncio
async def test_rebind_proof_invalidated_by_concurrent_password_security_change(users):
    async with transaction() as cur:
        await cur.execute('SELECT openid FROM users WHERE id=%s', (users[0],))
        old = (await cur.fetchone())['openid']
    qr = await identity.authorized_bind_qr(users[0], openid=old)
    scanned = await identity.scan_qr(qr['scene'], 'new_' + uuid.uuid4().hex)
    async with transaction() as cur:
        await identity.invalidate(cur, users[0])
    with pytest.raises(HTTPException):
        await identity.approve_qr(scanned['ticket'], 'bind')


@pytest.mark.asyncio
async def test_qr_cancel_prevents_later_approval(users):
    qr = await identity.create_qr('login')
    scan = await identity.scan_qr(qr['scene'], 'new_' + uuid.uuid4().hex)
    await identity.cancel_qr(qr['ticket'])
    with pytest.raises(HTTPException):
        await identity.approve_qr(scan['ticket'], 'register')


@pytest.mark.asyncio
async def test_bound_wechat_recovery_requires_correct_account_and_one_time_proof(users):
    username = 'wxrecovery_' + uuid.uuid4().hex[:15]
    credentials = AccountCredentials(username=username, password='Old-password-123')
    account = await authenticate(credentials, True, 'isolated-wxrecovery')
    openid = 'recover_' + uuid.uuid4().hex
    try:
        async with transaction() as cur:
            await cur.execute('UPDATE users SET openid=%s WHERE id=%s', (openid, account.user.id))
        proof = await identity.begin_wechat(openid, recovery=True)
        with pytest.raises(HTTPException):
            await identity.reset_password('different', 'New-password-123', ticket=proof['ticket'])
        await identity.reset_password(username, 'New-password-123', ticket=proof['ticket'])
        with pytest.raises(HTTPException):
            await identity.reset_password(username, 'New-password-456', ticket=proof['ticket'])
    finally:
        async with transaction() as cur:
            await cur.execute('DELETE FROM users WHERE id=%s', (account.user.id,))


@pytest.mark.asyncio
async def test_password_login_cannot_mint_post_reset_session_with_old_password(users):
    credentials = AccountCredentials(username='race_' + uuid.uuid4().hex[:15], password='Old-password-123')
    account = await authenticate(credentials, True, 'isolated-race')
    try:
        logged_in, _ = await asyncio.gather(authenticate(credentials, False, 'isolated-race'),
            identity.reset_password(credentials.username, 'New-password-123', recovery_code=account.recovery_code), return_exceptions=True)
        if not isinstance(logged_in, Exception):
            assert decode_token(logged_in.token)['sv'] < await identity.session_version(account.user.id)
        else:
            assert isinstance(logged_in, HTTPException)
    finally:
        async with transaction() as cur:
            await cur.execute('DELETE FROM users WHERE id=%s', (account.user.id,))


@pytest.mark.asyncio
async def test_openid_comparison_is_case_sensitive_even_with_legacy_collation(users):
    value = 'CaseSensitive_' + uuid.uuid4().hex
    async with transaction() as cur:
        await cur.execute('UPDATE users SET openid=%s WHERE id=%s', (value, users[0]))
    assert (await identity.begin_wechat(value.lower()))['status'] == 'choice'
