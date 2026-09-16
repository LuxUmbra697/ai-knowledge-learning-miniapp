"""Public proofs and authenticated account mutations have distinct schemas."""
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from app.core.auth import get_current_user
from app.core.config import get_settings
from app.models.common import ApiResponse
from app.models.user import LoginRequest
from app.services import identity_service as service, wechat_qr
from app.services.user_service import wx_code_to_openid
from app.services.account_service import AccountCredentials, check_login_rate

router = APIRouter(prefix='/user/identity', tags=['account-security'])


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Ticket(Input):
    ticket: str = Field(min_length=35, max_length=140, repr=False)


class Decision(Ticket):
    action: Literal['register', 'link', 'cancel', 'login', 'confirm', 'bind']
    credentials: AccountCredentials | None = None


class Proof(Input):
    password: str = Field(default='', max_length=128, repr=False)
    wechat_code: str = Field(default='', max_length=256, repr=False)
    ticket: str = Field(default='', max_length=140, repr=False)


class CredentialsChange(Proof):
    credentials: AccountCredentials


class Reset(Input):
    username: str = Field(min_length=3, max_length=40, pattern=r'^[a-zA-Z0-9_.-]+$')
    password: str = Field(min_length=10, max_length=128, repr=False)
    recovery_code: str = Field(default='', max_length=100, repr=False)
    ticket: str = Field(default='', max_length=140, repr=False)


class QrCreate(Input):
    purpose: Literal['login', 'recovery'] = 'login'


class QrScan(LoginRequest):
    scene: str = Field(pattern=r'^[a-f0-9]{32}$')


class NativeBind(Input):
    wechat_code: str = Field(min_length=1, max_length=256, repr=False)
    password: str = Field(min_length=1, max_length=128, repr=False)


async def rate(request, key, scope='identity', limits=(60, 12)):
    await check_login_rate(request.client.host if request.client else 'unknown', key, scope=scope, limits=limits)


async def proof_values(req):
    return {'password': req.password, 'ticket': req.ticket,
            'openid': await wx_code_to_openid(req.wechat_code) if req.wechat_code else ''}


def ok(value):
    return ApiResponse.success(data=value)


@router.get('/capabilities')
async def capabilities():
    settings = get_settings()
    return ok({'wechat_configured': bool(settings.wechat_app_id and settings.wechat_app_secret),
               'qr_channel': 'miniprogram', 'qr_environment': settings.wechat_qr_env,
               'recovery_methods': ['recovery_code', 'bound_wechat']})


@router.post('/wechat/finish')
async def finish(req: Decision, request: Request):
    await rate(request, req.credentials.username if req.credentials else 'wechat-choice')
    return ok(await service.finish_wechat(req.ticket, req.action, req.credentials))


@router.post('/wechat/recover')
async def wechat_recover(req: LoginRequest, request: Request):
    await rate(request, 'wechat-recovery')
    return ok(await service.begin_wechat(await wx_code_to_openid(req.code), recovery=True))


@router.get('/security')
async def security(user_id: int = Depends(get_current_user)):
    return ok(await service.security_profile(user_id))


@router.post('/wechat/bind-current')
async def bind_current(req: NativeBind, request: Request, user_id: int = Depends(get_current_user)):
    await rate(request, str(user_id), scope='identity-security')
    openid = await wx_code_to_openid(req.wechat_code)
    return ok(await service.direct_bind(user_id, openid, password=req.password))


@router.post('/credentials')
async def credentials(req: CredentialsChange, request: Request, user_id: int = Depends(get_current_user)):
    await rate(request, str(user_id), scope='identity-security')
    return ok(await service.change_credentials(user_id, req.credentials, **await proof_values(req)))


@router.post('/recovery-code')
async def recovery_code(req: Proof, request: Request, user_id: int = Depends(get_current_user)):
    await rate(request, str(user_id), scope='identity-security')
    return ok(await service.renew_recovery(user_id, **await proof_values(req)))


@router.post('/password/reset')
async def reset(req: Reset, request: Request):
    await rate(request, req.username.lower(), scope='identity-recovery')
    return ok(await service.reset_password(req.username, req.password, recovery_code=req.recovery_code, ticket=req.ticket))


async def with_image(qr):
    try:
        return {**qr, 'image': await wechat_qr.qr_image(qr['scene']), 'environment': get_settings().wechat_qr_env}
    except BaseException:
        await service.cancel_qr(qr['ticket'])
        raise


@router.post('/qr/create')
async def create(req: QrCreate, request: Request):
    await rate(request, 'qr-create', scope='identity-qr-create', limits=(20, 10))
    return ok(await with_image(await service.create_qr(req.purpose)))


@router.post('/qr/verify')
async def verify(request: Request, user_id: int = Depends(get_current_user)):
    await rate(request, str(user_id), scope='identity-qr-create', limits=(20, 10))
    return ok(await with_image(await service.create_qr('verify', user_id)))


@router.post('/qr/bind')
async def bind(req: Proof, request: Request, user_id: int = Depends(get_current_user)):
    await rate(request, str(user_id), scope='identity-qr-create', limits=(20, 10))
    return ok(await with_image(await service.authorized_bind_qr(user_id, **await proof_values(req))))


@router.post('/qr/scan')
async def scan(req: QrScan, request: Request):
    await rate(request, 'qr-scan', scope='identity-scan')
    return ok(await service.scan_qr(req.scene, await wx_code_to_openid(req.code)))


@router.post('/qr/approve')
async def approve(req: Decision, request: Request):
    await rate(request, req.credentials.username if req.credentials else 'qr-approve', scope='identity-scan')
    return ok(await service.approve_qr(req.ticket, req.action, req.credentials))


@router.post('/qr/poll')
async def poll(req: Ticket, request: Request):
    await rate(request, req.ticket[:32], scope='identity-poll', limits=(1000, 180))
    return ok(await service.poll_qr(req.ticket))


@router.post('/qr/consume')
async def consume(req: Ticket, request: Request):
    await rate(request, 'qr-consume')
    return ok(await service.consume_qr(req.ticket))


@router.post('/qr/cancel')
async def cancel(req: Ticket, request: Request):
    await rate(request, 'qr-cancel')
    return ok(await service.cancel_qr(req.ticket))
