import os
import json
import asyncio
from aiohttp import web
import msal
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from token_cache import TokenCacheStorage
import one_drive
import uuid
import pathlib

PORT = int(os.environ.get("PORT", 8080))
CLIENT_ID = os.environ.get("CLIENT_ID") or os.getenv("ADDON_CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET") or os.getenv("ADDON_CLIENT_SECRET")
TENANT_ID = os.environ.get("TENANT_ID")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}" if TENANT_ID else "https://login.microsoftonline.com/common"
# Use delegated scopes for sign-in + files access; MSAL will manage refresh tokens in the cache
# Do not include reserved OIDC scopes (openid/profile/offline_access) in MSAL request.
SCOPES = ["Files.Read"]

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
    msal_app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
        token_cache=cache,
    )
    app['msal_app'] = msal_app
    app['token_cache_storage'] = cache_storage
    app['token_cache'] = cache
    return msal_app


async def login(request):
    msal_app = get_msal_app(request.app)
    redirect = f"http://{request.host}/auth/callback"
    auth_url = msal_app.get_authorization_request_url(SCOPES, redirect_uri=redirect)
    raise web.HTTPFound(auth_url)


async def callback(request):
    code = request.rel_url.query.get('code')
    if not code:
        return web.Response(text='Missing code', status=400)
    msal_app = get_msal_app(request.app)
    redirect = f"http://{request.host}/auth/callback"
    result = msal_app.acquire_token_by_authorization_code(code, scopes=SCOPES, redirect_uri=redirect)
    # Save cache to disk (with optional encryption)
    request.app['token_cache_storage'].save(request.app['token_cache'])
    if 'access_token' in result:
        return web.Response(text='Authentication successful. You can close this page.')
    return web.Response(text='Authentication failed', status=400)


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
    return web.json_response({'logged_out': True})


def create_app():
    app = web.Application()
    app.router.add_get('/', index)
    app.router.add_get('/auth/login', login)
    app.router.add_get('/auth/callback', callback)
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
