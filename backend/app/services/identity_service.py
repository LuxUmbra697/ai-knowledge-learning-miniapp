"""Verified identity choices, single-use QR approvals and account recovery.

Only the configured mini-program issues WeChat identities. A QR contains a
public scene, never the browser polling secret or a login credential.
"""
import asyncio
import hashlib
import hmac
import secrets
import uuid

import aiomysql
from fastapi import HTTPException

from app.core.auth import create_token
from app.core.config import get_settings
from app.repositories.rag_index_repository import transaction
from app.services.account_service import hash_password, verify_password, _password_slots


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


async def session_version(user_id):
    async with transaction() as cur:
        await cur.execute('SELECT COALESCE(s.session_version,0) AS version FROM users u '
                          'LEFT JOIN account_security s ON s.user_id=u.id WHERE u.id=%s', (user_id,))
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(401, '账号已不存在，请重新登录')
        return row['version']


async def security_row(cur, user_id):
    await cur.execute('SELECT id FROM users WHERE id=%s FOR UPDATE', (user_id,))
    if not await cur.fetchone():
        raise HTTPException(401, '账号不存在')
    await cur.execute('INSERT INTO account_security(user_id,updated_at) VALUES(%s,UTC_TIMESTAMP()) ON DUPLICATE KEY UPDATE updated_at=updated_at', (user_id,))
    await cur.execute('SELECT * FROM account_security WHERE user_id=%s FOR UPDATE', (user_id,))
    return await cur.fetchone()


async def login_result(cur, user_id, recovery_code=None):
    await cur.execute('SELECT id,nickname,avatar_url,total_xp FROM users WHERE id=%s', (user_id,))
    user = await cur.fetchone()
    security = await security_row(cur, user_id)
    return {'token': create_token(user_id, '', session_version=security['session_version']), 'user': user,
            'recovery_code': recovery_code}


async def issue_login(user_id):
    async with transaction() as cur:
        return await login_result(cur, user_id)


async def new_challenge(cur, kind, *, openid=None, user_id=None, parent_id=None, version=0):
    challenge_id, secret = uuid.uuid4().hex, secrets.token_urlsafe(32)
    pair_code = f'{secrets.randbelow(1000000):06d}'
    await cur.execute('INSERT INTO identity_challenges(challenge_id,secret_hash,kind,user_id,openid,app_id,parent_id,session_version,pair_code,expires_at,created_at) '
                      'VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,DATE_ADD(UTC_TIMESTAMP(),INTERVAL 5 MINUTE),UTC_TIMESTAMP())',
                      (challenge_id, digest(secret), kind, user_id, openid, get_settings().wechat_app_id, parent_id, version, pair_code))
    await cur.execute('DELETE FROM identity_challenges WHERE expires_at<DATE_SUB(UTC_TIMESTAMP(),INTERVAL 1 DAY) LIMIT 50')
    return {'ticket': challenge_id + '.' + secret, 'scene': challenge_id, 'pair_code': pair_code, 'expires_in': 300}


async def challenge(cur, ticket, kinds):
    parts = ticket.split('.')
    if len(parts) != 2 or len(parts[0]) != 32 or len(parts[1]) > 100:
        raise HTTPException(400, '验证凭据无效，请重新开始')
    await cur.execute('SELECT *,expires_at>UTC_TIMESTAMP() AS valid FROM identity_challenges WHERE challenge_id=%s FOR UPDATE', (parts[0],))
    row = await cur.fetchone()
    if (not row or not hmac.compare_digest(row['secret_hash'], digest(parts[1])) or not row['valid']
            or row['kind'] not in kinds or row['state'] in ('used', 'cancelled') or row['app_id'] != get_settings().wechat_app_id):
        raise HTTPException(410, '验证已失效或已使用，请重新开始')
    return row


async def mark(cur, row, state='used'):
    await cur.execute('UPDATE identity_challenges SET state=%s WHERE challenge_id=%s', (state, row['challenge_id']))


async def owner(cur, openid):
    await cur.execute('SELECT id FROM users WHERE openid=%s AND CAST(openid AS BINARY)=CAST(%s AS BINARY)', (openid, openid))
    row = await cur.fetchone()
    return row['id'] if row else None


async def check_password(cur, credentials):
    if credentials is None:
        raise HTTPException(400, '请填写现有账号和密码')
    await cur.execute('SELECT user_id FROM account_credentials WHERE username=%s', (credentials.username,))
    identity = await cur.fetchone()
    if identity:
        await security_row(cur, identity['user_id'])
    await cur.execute('SELECT user_id,password_hash FROM account_credentials WHERE username=%s FOR UPDATE', (credentials.username,))
    row = await cur.fetchone()
    async with _password_slots:
        valid = await asyncio.to_thread(verify_password, credentials.password, row['password_hash']) if row else False
        if not row:
            await asyncio.to_thread(hash_password, credentials.password)
    if not valid:
        raise HTTPException(403, '账号或密码不正确')
    return row['user_id']


async def invalidate(cur, user_id):
    await security_row(cur, user_id)
    await cur.execute('UPDATE account_security SET session_version=session_version+1,updated_at=UTC_TIMESTAMP() WHERE user_id=%s', (user_id,))


async def register_wechat(cur, openid, credentials, *, issue_recovery=True):
    recovery = None
    await cur.execute('INSERT INTO users(openid,nickname) VALUES(%s,%s)', (openid, credentials.nickname if credentials else '学习者'))
    user_id = cur.lastrowid
    if credentials:
        async with _password_slots:
            hashed = await asyncio.to_thread(hash_password, credentials.password)
        await cur.execute('INSERT INTO account_credentials(username,user_id,password_hash) VALUES(%s,%s,%s)', (credentials.username, user_id, hashed))
        if issue_recovery:
            recovery = await rotate_recovery(cur, user_id)
    return user_id, recovery


async def bind_identity(cur, user_id, openid, replace=False):
    current = await owner(cur, openid)
    if current and current != user_id:
        raise HTTPException(409, '这个微信已绑定其他学园账号，不会自动合并或转移学习数据')
    await security_row(cur, user_id)
    await cur.execute('SELECT openid FROM users WHERE id=%s FOR UPDATE', (user_id,))
    old = (await cur.fetchone())['openid']
    if old and old != openid and not replace:
        raise HTTPException(409, '账号已经绑定微信，请在账号安全中验证身份后换绑')
    await cur.execute('UPDATE users SET openid=%s WHERE id=%s', (openid, user_id))
    if old != openid:
        await invalidate(cur, user_id)


async def begin_wechat(openid, recovery=False):
    async with transaction() as cur:
        user_id = await owner(cur, openid)
        if recovery:
            if not user_id:
                raise HTTPException(403, '该微信尚未绑定学园账号，请使用恢复码或原有微信验证')
            version = (await security_row(cur, user_id))['session_version']
            return {**await new_challenge(cur, 'recovery', openid=openid, user_id=user_id, version=version), 'status': 'verified'}
        if user_id:
            return await login_result(cur, user_id)
        return {**await new_challenge(cur, 'wechat', openid=openid), 'status': 'choice'}


async def finish_wechat(ticket, action, credentials=None):
    try:
        async with transaction() as cur:
            proof = await challenge(cur, ticket, {'wechat'})
            if action == 'cancel':
                await mark(cur, proof, 'cancelled')
                return {'status': 'cancelled'}
            if await owner(cur, proof['openid']):
                raise HTTPException(409, '微信绑定状态已变化，请重新登录')
            if action == 'register':
                user_id, recovery = await register_wechat(cur, proof['openid'], credentials)
            elif action == 'link':
                user_id = await check_password(cur, credentials)
                await bind_identity(cur, user_id, proof['openid'])
                recovery = None
            else:
                raise HTTPException(400, '请选择注册、绑定或取消')
            await mark(cur, proof)
            return await login_result(cur, user_id, recovery)
    except aiomysql.IntegrityError:
        raise HTTPException(409, '账号名称或微信已被绑定，请刷新后重试') from None


async def rotate_recovery(cur, user_id):
    code = secrets.token_urlsafe(24)
    await security_row(cur, user_id)
    await cur.execute('UPDATE account_security SET recovery_hash=%s,updated_at=UTC_TIMESTAMP() WHERE user_id=%s', (digest(code), user_id))
    return code


async def verify_identity(cur, user_id, *, password='', openid='', ticket=''):
    state = await security_row(cur, user_id)
    if ticket:
        proof = await challenge(cur, ticket, {'verify'})
        if proof['user_id'] != user_id or proof['session_version'] != state['session_version']:
            raise HTTPException(403, '身份验证已过期，请重新验证')
        await mark(cur, proof)
    elif openid:
        if await owner(cur, openid) != user_id:
            raise HTTPException(403, '请使用当前账号已绑定的微信验证')
    else:
        await cur.execute('SELECT password_hash FROM account_credentials WHERE user_id=%s', (user_id,))
        row = await cur.fetchone()
        async with _password_slots:
            valid = bool(row) and await asyncio.to_thread(verify_password, password, row['password_hash'])
        if not valid:
            raise HTTPException(403, '请验证当前密码或已绑定的微信')
    return state


async def security_profile(user_id):
    async with transaction() as cur:
        await cur.execute('SELECT u.openid,c.username,s.recovery_hash FROM users u LEFT JOIN account_credentials c ON c.user_id=u.id '
                          'LEFT JOIN account_security s ON s.user_id=u.id WHERE u.id=%s', (user_id,))
        row = await cur.fetchone()
        return {'username': row['username'], 'wechat_bound': bool(row['openid']), 'recovery_ready': bool(row['recovery_hash'])}


async def change_credentials(user_id, credentials, **proof):
    try:
        async with transaction() as cur:
            await verify_identity(cur, user_id, **proof)
            await cur.execute('SELECT username FROM account_credentials WHERE user_id=%s', (user_id,))
            existing = await cur.fetchone()
            if existing and existing['username'] != credentials.username:
                raise HTTPException(409, '账号名称不可在修改密码时更改')
            async with _password_slots:
                hashed = await asyncio.to_thread(hash_password, credentials.password)
            if existing:
                await cur.execute('UPDATE account_credentials SET password_hash=%s WHERE user_id=%s', (hashed, user_id))
            else:
                await cur.execute('INSERT INTO account_credentials(username,user_id,password_hash) VALUES(%s,%s,%s)', (credentials.username, user_id, hashed))
            code = await rotate_recovery(cur, user_id)
            await invalidate(cur, user_id)
            return await login_result(cur, user_id, code)
    except aiomysql.IntegrityError:
        raise HTTPException(409, '账号名称已被使用') from None


async def reset_password(username, password, *, recovery_code='', ticket=''):
    async with _password_slots:
        hashed = await asyncio.to_thread(hash_password, password)
    async with transaction() as cur:
        await cur.execute('SELECT user_id FROM account_credentials WHERE username=%s', (username.lower(),))
        account = await cur.fetchone()
        proof = await challenge(cur, ticket, {'recovery'}) if ticket else None
        user_id = account['user_id'] if account else None
        if not user_id or (proof and proof['user_id'] != user_id):
            raise HTTPException(403, '账号或恢复凭据不正确')
        state = await security_row(cur, user_id)
        if proof:
            if proof['session_version'] != state['session_version'] or await owner(cur, proof['openid']) != user_id:
                raise HTTPException(403, '身份验证已过期')
            await mark(cur, proof)
        elif not recovery_code or not state['recovery_hash'] or not hmac.compare_digest(digest(recovery_code), state['recovery_hash']):
            raise HTTPException(403, '账号或恢复凭据不正确')
        await cur.execute('UPDATE account_credentials SET password_hash=%s WHERE user_id=%s', (hashed, user_id))
        await cur.execute('UPDATE account_security SET recovery_hash=NULL WHERE user_id=%s', (user_id,))
        await invalidate(cur, user_id)
    return {'status': 'reset'}


async def create_qr(purpose, user_id=None):
    async with transaction() as cur:
        version = (await security_row(cur, user_id))['session_version'] if user_id else 0
        return await new_challenge(cur, 'qr_' + purpose, user_id=user_id, version=version)


async def authorized_bind_qr(user_id, **proof):
    async with transaction() as cur:
        state = await verify_identity(cur, user_id, **proof)
        return await new_challenge(cur, 'qr_bind', user_id=user_id, version=state['session_version'])


async def renew_recovery(user_id, **proof):
    async with transaction() as cur:
        await verify_identity(cur, user_id, **proof)
        await cur.execute('SELECT username FROM account_credentials WHERE user_id=%s', (user_id,))
        if not await cur.fetchone():
            raise HTTPException(409, '请先设置账号名称和密码，再生成恢复码')
        return {'recovery_code': await rotate_recovery(cur, user_id)}


async def direct_bind(user_id, openid, **proof):
    try:
        async with transaction() as cur:
            await verify_identity(cur, user_id, **proof)
            await bind_identity(cur, user_id, openid, replace=True)
            return await login_result(cur, user_id)
    except aiomysql.IntegrityError:
        raise HTTPException(409, '该微信已绑定其他账号') from None


async def scan_qr(scene, openid):
    async with transaction() as cur:
        await cur.execute('SELECT *,expires_at>UTC_TIMESTAMP() AS valid FROM identity_challenges WHERE challenge_id=%s FOR UPDATE', (scene,))
        parent = await cur.fetchone()
        if (not parent or not parent['valid'] or parent['state'] != 'pending' or parent['kind'] not in {'qr_login', 'qr_bind', 'qr_verify', 'qr_recovery'}
                or parent['app_id'] != get_settings().wechat_app_id):
            raise HTTPException(410, '二维码已失效，请回到网页刷新')
        registered = bool(await owner(cur, openid))
        proof = await new_challenge(cur, 'qr_scan', openid=openid, parent_id=scene)
        return {'ticket': proof['ticket'], 'purpose': parent['kind'][3:], 'registered': registered, 'pair_code': parent['pair_code']}


async def approve_qr(ticket, action, credentials=None):
    try:
        async with transaction() as cur:
            proof = await challenge(cur, ticket, {'qr_scan'})
            await cur.execute('SELECT *,expires_at>UTC_TIMESTAMP() AS valid FROM identity_challenges WHERE challenge_id=%s FOR UPDATE', (proof['parent_id'],))
            parent = await cur.fetchone()
            if not parent or not parent['valid'] or parent['state'] != 'pending':
                raise HTTPException(410, '二维码已失效或已确认')
            if action == 'cancel':
                await mark(cur, proof, 'cancelled')
                await mark(cur, parent, 'cancelled')
                return {'status': 'cancelled'}
            user_id = await owner(cur, proof['openid'])
            purpose = parent['kind'][3:]
            if purpose == 'bind':
                if action != 'bind' or not parent['user_id']:
                    raise HTTPException(400, '请确认绑定操作')
                state = await security_row(cur, parent['user_id'])
                if state['session_version'] != parent['session_version']:
                    raise HTTPException(409, '账号状态已变化，请重新验证后换绑')
                await bind_identity(cur, parent['user_id'], proof['openid'], replace=True)
                user_id = parent['user_id']
            elif purpose in ('verify', 'recovery'):
                if action != 'confirm' or not user_id or (purpose == 'verify' and user_id != parent['user_id']):
                    raise HTTPException(403, '请使用需要验证的学园账号所绑定的微信')
            elif action == 'login' and user_id:
                pass
            elif action in ('register', 'link') and not user_id:
                if action == 'register':
                    # QR approval carries no recovery secret; generate it explicitly after login.
                    user_id, _recovery = await register_wechat(cur, proof['openid'], credentials, issue_recovery=False)
                else:
                    user_id = await check_password(cur, credentials)
                    await bind_identity(cur, user_id, proof['openid'])
            else:
                raise HTTPException(409, '微信状态已变化，请重新扫码并选择注册或绑定')
            state = await security_row(cur, user_id)
            await cur.execute("UPDATE identity_challenges SET state='approved',user_id=%s,openid=%s,session_version=%s WHERE challenge_id=%s",
                              (user_id, proof['openid'], state['session_version'], parent['challenge_id']))
            await mark(cur, proof)
            return {'status': 'approved'}
    except aiomysql.IntegrityError:
        raise HTTPException(409, '账号名称或微信已被绑定') from None


async def poll_qr(ticket):
    async with transaction() as cur:
        row = await challenge(cur, ticket, {'qr_login', 'qr_bind', 'qr_verify', 'qr_recovery'})
        return {'status': row['state'], 'pair_code': row['pair_code']}


async def consume_qr(ticket):
    async with transaction() as cur:
        row = await challenge(cur, ticket, {'qr_login', 'qr_bind', 'qr_verify', 'qr_recovery'})
        if row['state'] != 'approved':
            raise HTTPException(409, '请先在微信中确认')
        state = await security_row(cur, row['user_id'])
        if state['session_version'] != row['session_version'] or await owner(cur, row['openid']) != row['user_id']:
            raise HTTPException(409, '账号状态已变化，请重新扫码')
        await mark(cur, row)
        if row['kind'] in ('qr_verify', 'qr_recovery'):
            return {**await new_challenge(cur, row['kind'][3:], openid=row['openid'], user_id=row['user_id'], version=state['session_version']), 'status': 'verified'}
        return await login_result(cur, row['user_id'])


async def cancel_qr(ticket):
    async with transaction() as cur:
        row = await challenge(cur, ticket, {'qr_login', 'qr_bind', 'qr_verify', 'qr_recovery'})
        if row['state'] != 'pending':
            raise HTTPException(409, '微信端已确认，请查看操作结果')
        await mark(cur, row, 'cancelled')
        return {'status': 'cancelled'}
