import os
import asyncio
from aiohttp import web
import msal
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from token_cache import TokenCacheStorage
import one_drive
import uuid
import pathlib

PORT = int(os.environ.get("PORT", 8080))
# Compatible with OneDrive personal accounts, like the reference add-on.
DEFAULT_CLIENT_ID = "b8a647cf-eccf-4c7f-a0a6-2cbec5d0b94d"
CLIENT_ID = os.environ.get("CLIENT_ID") or os.getenv("ADDON_CLIENT_ID") or DEFAULT_CLIENT_ID
AUTHORITY = "https://login.microsoftonline.com/consumers"
SCOPES = ["offline_access", "Files.ReadWrite.AppFolder"]

TOKEN_CACHE_PATH = os.environ.get('TOKEN_CACHE_PATH', 'token_cache.bin')
BACKUP_PATH = os.environ.get('BACKUP_PATH', '/backup')
REMOTE_FOLDER = os.environ.get('REMOTE_FOLDER', 'Backups')


async def index(request):
    return web.FileResponse('static/index.html')


def schedule_jobs(app):
    scheduler = AsyncIOScheduler()
    scheduler.start()
    app['scheduler'] = scheduler


def get_msal_app(app):
    if 'msal_app' in app:
        return app['msal_app']
    cache_storage = TokenCacheStorage(path=TOKEN_CACHE_PATH)
    cache = cache_storage.load()
    msal_app = msal.PublicClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        token_cache=cache,
    )
    app['msal_app'] = msal_app
    app['token_cache_storage'] = cache_storage
    app['token_cache'] = cache
    app.setdefault('auth_state', {'status': 'idle'})
    return msal_app


def _auth_result_payload(auth_state):
    return {
        'status': auth_state.get('status', 'idle'),
        'message': auth_state.get('message'),
        'verification_uri': auth_state.get('verification_uri'),
        'user_code': auth_state.get('user_code'),
        'expires_in': auth_state.get('expires_in'),
    }

async def device_login_start(request):
    msal_app = get_msal_app(request.app)
    flow = msal_app.initiate_device_flow(scopes=SCOPES)
    if 'user_code' not in flow:
        return web.json_response({'error': 'failed_to_initiate_device_flow', 'details': flow}, status=500)

    auth_state = {
        'status': 'pending',
        'message': flow.get('message'),
        'verification_uri': flow.get('verification_uri'),
        'user_code': flow.get('user_code'),
        'expires_in': flow.get('expires_in'),
        'flow': flow,
    }
    request.app['auth_state'] = auth_state

    async def _run_device_flow():
        try:
            result = await asyncio.to_thread(msal_app.acquire_token_by_device_flow, flow)
            if 'access_token' in result:
                request.app['token_cache_storage'].save(request.app['token_cache'])
                request.app['auth_state']['status'] = 'authenticated'
                request.app['auth_state']['message'] = 'Authentication successful'
            else:
                request.app['auth_state']['status'] = 'error'
                request.app['auth_state']['message'] = result.get('error_description') or result.get('error') or 'Authentication failed'
        except Exception as ex:
            request.app['auth_state']['status'] = 'error'
            request.app['auth_state']['message'] = str(ex)

    asyncio.create_task(_run_device_flow())
    return web.json_response(_auth_result_payload(request.app['auth_state']))


async def device_login_status(request):
    _ = get_msal_app(request.app)
    auth_state = request.app.get('auth_state', {'status': 'idle'})
    if auth_state.get('status') == 'pending':
        token = acquire_token_silent(request.app)
        if token:
            request.app['auth_state']['status'] = 'authenticated'
            request.app['auth_state']['message'] = 'Authentication successful'
    return web.json_response(_auth_result_payload(request.app['auth_state']))


def _get_account(msal_app):
    accounts = msal_app.get_accounts()
    return accounts[0] if accounts else None


def acquire_token_silent(app):
    msal_app = get_msal_app(app)
    account = _get_account(msal_app)
    if not account:
        return None
    result = msal_app.acquire_token_silent(SCOPES, account=account)
    # MSAL will automatically use refresh_token if access token expired
    # Persist cache after possible refresh
    app['token_cache_storage'].save(app['token_cache'])
    return result


async def status(request):
    tokens = acquire_token_silent(request.app)
    return web.json_response({'authenticated': bool(tokens)})


async def trigger_backup(request):
    # placeholder: ensure we have a valid token before starting
    token = acquire_token_silent(request.app)
    if not token:
        return web.json_response({'error': 'not_authenticated'}, status=401)
    return web.json_response({'started': True})


async def list_backups(request):
    token = acquire_token_silent(request.app)
    if not token:
        return web.json_response({'error': 'not_authenticated'}, status=401)
    access_token = token.get('access_token')
    try:
        items = await one_drive.list_folder(access_token, folder_path=REMOTE_FOLDER)
        # map items to minimal info
        out = []
        for it in items:
            out.append({
                'id': it.get('id'),
                'name': it.get('name'),
                'size': it.get('size'),
                'lastModifiedDateTime': it.get('lastModifiedDateTime'),
                'file': 'file' in it,
            })
        return web.json_response({'items': out})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)


async def download_request(request):
    token = acquire_token_silent(request.app)
    if not token:
        return web.json_response({'error': 'not_authenticated'}, status=401)
    data = await request.json()
    item_id = data.get('item_id')
    name = data.get('name')
    if not item_id and not name:
        return web.json_response({'error': 'item_id or name required'}, status=400)
    # decide destination path
    dest_dir = os.environ.get('BACKUP_PATH', BACKUP_PATH)
    pathlib.Path(dest_dir).mkdir(parents=True, exist_ok=True)
    dest_path = os.path.join(dest_dir, name or f'{item_id}.bin')
    job_id = str(uuid.uuid4())
    # store job status
    request.app.setdefault('downloads', {})
    request.app['downloads'][job_id] = {'status': 'queued', 'path': dest_path}

    async def _run_download():
        request.app['downloads'][job_id]['status'] = 'running'
        try:
            access_token = token.get('access_token')
            result = await one_drive.download_item(access_token, item_id, dest_path)
            request.app['downloads'][job_id]['status'] = result.get('status')
            request.app['downloads'][job_id]['result'] = result
        except Exception as e:
            request.app['downloads'][job_id]['status'] = 'error'
            request.app['downloads'][job_id]['error'] = str(e)

    asyncio.create_task(_run_download())
    return web.json_response({'job_id': job_id})


async def download_status(request):
    job_id = request.match_info.get('job_id')
    info = request.app.get('downloads', {}).get(job_id)
    if not info:
        return web.json_response({'error': 'not_found'}, status=404)
    return web.json_response(info)


async def logout(request):
    # clear cache file
    storage: TokenCacheStorage = request.app.get('token_cache_storage')
    if storage and os.path.exists(storage.path):
        try:
            os.remove(storage.path)
        except Exception:
            pass
    request.app.pop('msal_app', None)
    request.app.pop('token_cache', None)
    request.app['auth_state'] = {'status': 'idle'}
    return web.json_response({'logged_out': True})


def create_app():
    app = web.Application()
    app.router.add_get('/', index)
    app.router.add_post('/api/auth/device/start', device_login_start)
    app.router.add_get('/api/auth/device/status', device_login_status)
    app.router.add_get('/api/status', status)
    app.router.add_post('/api/backup', trigger_backup)
    app.router.add_get('/api/list', list_backups)
    app.router.add_post('/api/download', download_request)
    app.router.add_get('/api/downloads/{job_id}', download_status)
    app.router.add_post('/api/logout', logout)
    schedule_jobs(app)
    return app


if __name__ == '__main__':
    web.run_app(create_app(), port=PORT)
