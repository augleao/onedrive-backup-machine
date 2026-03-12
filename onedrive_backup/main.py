import os
import json
import uuid
import asyncio
import pathlib
import logging
import threading
from datetime import datetime, timedelta, timezone
from aiohttp import web
import msal
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from token_cache import TokenCacheStorage
import one_drive


_LOGGER = logging.getLogger(__name__)

PORT = int(os.environ.get("PORT", 8080))
CLIENT_ID = (os.environ.get("CLIENT_ID") or os.getenv("ADDON_CLIENT_ID") or "").strip()
TENANT_ID = (os.environ.get("TENANT_ID") or "").strip()
# If tenant_id is provided, use tenant authority (works for org-only apps).
# Otherwise default to consumers for personal Microsoft account device flow.
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}" if TENANT_ID else "https://login.microsoftonline.com/consumers"
# Request access to user files so task creation can browse full OneDrive tree.
SCOPES = ["Files.Read"]

TOKEN_CACHE_PATH = os.environ.get('TOKEN_CACHE_PATH', 'token_cache.bin')
BACKUP_PATH = os.environ.get('BACKUP_PATH', '/backup')
STATE_PATH = os.environ.get('STATE_PATH', '/data/backup_tasks_state.json')
DEFAULT_RETENTION_DAYS = int(os.environ.get('RETENTION_DAYS_DEFAULT', '30'))


class StateStore:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()

    def _default_state(self):
        return {
            'settings': {
                'retention_days': DEFAULT_RETENTION_DAYS,
            },
            'tasks': [],
        }

    def load(self):
        with self._lock:
            if not os.path.exists(self.path):
                return self._default_state()
            with open(self.path, 'r', encoding='utf-8') as f:
                data = json.load(f)

        state = self._default_state()
        state.update(data if isinstance(data, dict) else {})
        state['settings'] = {**self._default_state()['settings'], **(state.get('settings') or {})}
        state['tasks'] = state.get('tasks') or []
        return state

    def save(self, state):
        os.makedirs(os.path.dirname(self.path) or '.', exist_ok=True)
        payload = json.dumps(state, ensure_ascii=True, indent=2)
        with self._lock:
            with open(self.path, 'w', encoding='utf-8') as f:
                f.write(payload)


def now_local():
    return datetime.now()


def now_utc_iso():
    return datetime.now(timezone.utc).isoformat()


def parse_hhmm(value):
    if not isinstance(value, str) or ':' not in value:
        raise ValueError('time must be HH:MM')
    hh, mm = value.split(':', 1)
    hour = int(hh)
    minute = int(mm)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError('time must be HH:MM')
    return hour, minute


def parse_graph_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except Exception:
        return None


def shift_month(year, month):
    if month == 12:
        return year + 1, 1
    return year, month + 1


def compute_next_run(task, from_dt=None):
    from_dt = from_dt or now_local()
    schedule = task.get('schedule') or {}
    schedule_type = schedule.get('type', 'daily')
    hour, minute = parse_hhmm(schedule.get('time', '02:00'))

    if schedule_type == 'daily':
        candidate = from_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= from_dt:
            candidate += timedelta(days=1)
        return candidate.isoformat()

    if schedule_type == 'weekly':
        weekday = int(schedule.get('weekday', 0))
        if weekday < 0 or weekday > 6:
            raise ValueError('weekday must be between 0 and 6')
        candidate = from_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
        delta = (weekday - from_dt.weekday()) % 7
        candidate += timedelta(days=delta)
        if candidate <= from_dt:
            candidate += timedelta(days=7)
        return candidate.isoformat()

    if schedule_type == 'monthly':
        day = int(schedule.get('day', 1))
        if day < 1 or day > 28:
            raise ValueError('day must be between 1 and 28')
        candidate = from_dt.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= from_dt:
            y, m = shift_month(candidate.year, candidate.month)
            candidate = candidate.replace(year=y, month=m)
        return candidate.isoformat()

    raise ValueError('schedule.type must be daily, weekly or monthly')


def _normalize_graph_parent_path(parent_path):
    raw = ''
    if parent_path and ':' in parent_path:
        raw = parent_path.split(':', 1)[1]
    elif parent_path:
        raw = parent_path
    parts = [p for p in raw.strip('/').split('/') if p]

    # Graph approot path usually starts with Apps/<AppName>/...
    if len(parts) >= 2 and parts[0].lower() == 'apps':
        parts = parts[2:]

    return '/'.join(parts)


def get_state(app):
    return app['state']


def save_state(app):
    app['state_store'].save(app['state'])


def find_task(state, task_id):
    return next((t for t in state['tasks'] if t.get('id') == task_id), None)


def validate_task_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError('payload must be an object')

    name = (payload.get('name') or '').strip()
    if not name:
        raise ValueError('name is required')

    destination_path = (payload.get('destination_path') or '').strip()
    if not destination_path:
        raise ValueError('destination_path is required')

    schedule = payload.get('schedule') or {}
    schedule_type = schedule.get('type', 'daily')
    if schedule_type not in ('daily', 'weekly', 'monthly'):
        raise ValueError('schedule.type must be daily, weekly or monthly')
    parse_hhmm(schedule.get('time', '02:00'))
    if schedule_type == 'weekly':
        weekday = int(schedule.get('weekday', 0))
        if weekday < 0 or weekday > 6:
            raise ValueError('schedule.weekday must be between 0 and 6')
    if schedule_type == 'monthly':
        day = int(schedule.get('day', 1))
        if day < 1 or day > 28:
            raise ValueError('schedule.day must be between 1 and 28')

    strategy = payload.get('strategy') or {}
    mode = strategy.get('mode', 'full')
    if mode not in ('full', 'incremental'):
        raise ValueError('strategy.mode must be full or incremental')
    until_full = int(strategy.get('incrementals_until_full', 3))
    if until_full < 1 or until_full > 365:
        raise ValueError('strategy.incrementals_until_full must be between 1 and 365')

    sources_in = payload.get('sources') or []
    if not isinstance(sources_in, list) or not sources_in:
        raise ValueError('at least one source must be selected')

    sources = []
    for src in sources_in:
        src_id = (src.get('id') or '').strip()
        src_name = (src.get('name') or '').strip()
        if not src_id or not src_name:
            raise ValueError('each source must contain id and name')
        path = (src.get('path') or src_name).strip('/').strip()
        if not path:
            path = src_name
        sources.append({
            'id': src_id,
            'name': src_name,
            'path': path,
            'is_folder': bool(src.get('is_folder')),
            'lastModifiedDateTime': src.get('lastModifiedDateTime'),
            'size': src.get('size') or 0,
        })

    return {
        'name': name,
        'enabled': bool(payload.get('enabled', True)),
        'destination_path': destination_path,
        'sources': sources,
        'schedule': {
            'type': schedule_type,
            'time': schedule.get('time', '02:00'),
            'weekday': int(schedule.get('weekday', 0)),
            'day': int(schedule.get('day', 1)),
        },
        'strategy': {
            'mode': mode,
            'incrementals_until_full': until_full,
        },
    }


async def index(request):
    base = pathlib.Path(__file__).parent
    return web.FileResponse(base.joinpath('static', 'index.html'))


@web.middleware
async def api_error_middleware(request, handler):
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception as ex:
        _LOGGER.exception("Unhandled API error on %s", request.path)
        if request.path.startswith('/api/'):
            return web.json_response(
                {
                    'error': 'internal_server_error',
                    'message': str(ex),
                },
                status=500,
            )
        raise


def schedule_jobs(app):
    # Bind scheduler to the currently running aiohttp loop.
    scheduler = AsyncIOScheduler(event_loop=asyncio.get_running_loop())
    scheduler.start()
    app['scheduler'] = scheduler
    sync_task_schedules(app)


async def on_startup(app):
    schedule_jobs(app)


async def on_cleanup(app):
    scheduler = app.get('scheduler')
    if not scheduler:
        return
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        _LOGGER.exception('Failed to shutdown scheduler cleanly')


def sync_task_schedules(app):
    scheduler = app.get('scheduler')
    if not scheduler:
        return
    for job in scheduler.get_jobs():
        if job.id.startswith('task_'):
            scheduler.remove_job(job.id)

    state = get_state(app)
    now = now_local()
    for task in state['tasks']:
        if not task.get('enabled', True):
            task.setdefault('state', {})['next_run_at'] = None
            continue

        schedule = task.get('schedule') or {}
        hour, minute = parse_hhmm(schedule.get('time', '02:00'))
        kwargs = {'hour': hour, 'minute': minute}
        schedule_type = schedule.get('type', 'daily')
        if schedule_type == 'weekly':
            kwargs['day_of_week'] = int(schedule.get('weekday', 0))
        elif schedule_type == 'monthly':
            kwargs['day'] = int(schedule.get('day', 1))

        task_id = task['id']

        def _runner(tid=task_id):
            asyncio.create_task(run_task_by_id(app, tid, trigger='scheduled'))

        scheduler.add_job(_runner, trigger='cron', id=f'task_{task_id}', replace_existing=True, **kwargs)
        task.setdefault('state', {})['next_run_at'] = compute_next_run(task, from_dt=now)

    save_state(app)


def get_msal_app(app):
    if 'msal_app' in app:
        return app['msal_app']
    if not CLIENT_ID:
        raise ValueError('client_id is required. Set it in add-on Configuration before linking your account.')

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
    verification_uri = auth_state.get('verification_uri')
    if verification_uri and 'login.microsoft.com/device' in verification_uri:
        verification_uri = 'https://microsoft.com/devicelogin'

    verification_uri_complete = auth_state.get('verification_uri_complete')
    if verification_uri_complete and 'login.microsoft.com/device' in verification_uri_complete:
        # Keep full URL behavior but normalize host variant.
        verification_uri_complete = verification_uri_complete.replace('login.microsoft.com/device', 'microsoft.com/devicelogin')

    return {
        'status': auth_state.get('status', 'idle'),
        'message': auth_state.get('message'),
        'verification_uri': verification_uri,
        'verification_uri_complete': verification_uri_complete,
        'user_code': auth_state.get('user_code'),
        'expires_in': auth_state.get('expires_in'),
    }


def _get_account(msal_app):
    accounts = msal_app.get_accounts()
    return accounts[0] if accounts else None


def acquire_token_silent(app):
    msal_app = get_msal_app(app)
    account = _get_account(msal_app)
    if not account:
        return None
    result = msal_app.acquire_token_silent(SCOPES, account=account)
    app['token_cache_storage'].save(app['token_cache'])
    return result


async def device_login_start(request):
    if not CLIENT_ID:
        return web.json_response(
            {
                'error': 'client_id_missing',
                'message': 'client_id is required. Set it in add-on Configuration before linking your account.',
            },
            status=400,
        )
    try:
        msal_app = get_msal_app(request.app)
        flow = msal_app.initiate_device_flow(scopes=SCOPES)
    except Exception as ex:
        _LOGGER.exception('Failed to start device flow')
        return web.json_response(
            {
                'error': 'failed_to_start_device_flow',
                'message': str(ex),
            },
            status=500,
        )

    if 'user_code' not in flow:
        flow_message = None
        if isinstance(flow, dict):
            flow_message = flow.get('error_description') or flow.get('error')
        return web.json_response(
            {
                'error': 'failed_to_initiate_device_flow',
                'message': flow_message or 'Device flow was not initiated by Microsoft identity platform.',
                'details': flow,
            },
            status=500,
        )

    auth_state = {
        'status': 'pending',
        'message': flow.get('message'),
        'verification_uri': flow.get('verification_uri'),
        'verification_uri_complete': flow.get('verification_uri_complete'),
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
    if not CLIENT_ID:
        return web.json_response(
            {
                'status': 'error',
                'message': 'client_id is required. Set it in add-on Configuration.',
                'verification_uri': None,
                'user_code': None,
                'expires_in': None,
            }
        )

    try:
        _ = get_msal_app(request.app)
    except Exception as ex:
        return web.json_response(
            {
                'status': 'error',
                'message': str(ex),
                'verification_uri': None,
                'user_code': None,
                'expires_in': None,
            },
            status=500,
        )

    auth_state = request.app.get('auth_state', {'status': 'idle'})
    if auth_state.get('status') == 'pending':
        try:
            token = acquire_token_silent(request.app)
        except Exception as ex:
            request.app['auth_state']['status'] = 'error'
            request.app['auth_state']['message'] = str(ex)
            return web.json_response(_auth_result_payload(request.app['auth_state']), status=500)
        if token:
            request.app['auth_state']['status'] = 'authenticated'
            request.app['auth_state']['message'] = 'Authentication successful'
    return web.json_response(_auth_result_payload(request.app['auth_state']))


async def status(request):
    if not CLIENT_ID:
        return web.json_response(
            {
                'authenticated': False,
                'client_id_configured': False,
                'message': 'Set client_id in add-on configuration.',
            }
        )

    try:
        tokens = acquire_token_silent(request.app)
    except Exception as ex:
        return web.json_response(
            {
                'authenticated': False,
                'client_id_configured': True,
                'message': str(ex),
            },
            status=200,
        )

    return web.json_response(
        {
            'authenticated': bool(tokens),
            'client_id_configured': bool(CLIENT_ID),
        }
    )


async def logout(request):
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


async def onedrive_tree(request):
    token = acquire_token_silent(request.app)
    if not token:
        return web.json_response({'error': 'not_authenticated'}, status=401)

    parent_id = request.query.get('parent_id')
    try:
        items = await one_drive.list_children(token.get('access_token'), parent_id=parent_id)
    except Exception as ex:
        msg = str(ex)
        if 'SPO license' in msg or 'Tenant does not have a SPO license' in msg:
            return web.json_response(
                {
                    'error': 'onedrive_license_missing',
                    'message': (
                        'The signed-in account does not have an active OneDrive/SharePoint license in this tenant. '
                        'Assign a OneDrive license to this user, or clear tenant_id in add-on configuration and relink with a personal Microsoft account.'
                    ),
                },
                status=400,
            )
        raise

    out = []
    for item in items:
        parent_path = _normalize_graph_parent_path((item.get('parentReference') or {}).get('path'))
        path = f"{parent_path}/{item.get('name')}" if parent_path else item.get('name')
        out.append(
            {
                'id': item.get('id'),
                'name': item.get('name'),
                'path': path,
                'is_folder': 'folder' in item,
                'size': item.get('size') or 0,
                'lastModifiedDateTime': item.get('lastModifiedDateTime'),
            }
        )

    return web.json_response({'items': out})


async def get_settings(request):
    state = get_state(request.app)
    return web.json_response(state.get('settings') or {'retention_days': DEFAULT_RETENTION_DAYS})


async def put_settings(request):
    payload = await request.json()
    retention_days = int((payload or {}).get('retention_days', DEFAULT_RETENTION_DAYS))
    if retention_days < 1 or retention_days > 3650:
        return web.json_response({'error': 'retention_days must be between 1 and 3650'}, status=400)

    state = get_state(request.app)
    state['settings']['retention_days'] = retention_days
    save_state(request.app)
    return web.json_response(state['settings'])


async def get_tasks(request):
    state = get_state(request.app)
    return web.json_response({'tasks': state['tasks']})


async def create_task(request):
    payload = await request.json()
    try:
        normalized = validate_task_payload(payload)
    except ValueError as ex:
        return web.json_response({'error': str(ex)}, status=400)

    task = {
        'id': str(uuid.uuid4()),
        **normalized,
        'created_at': now_utc_iso(),
        'updated_at': now_utc_iso(),
        'state': {
            'last_run_at': None,
            'last_status': 'idle',
            'next_run_at': None,
            'incremental_count': 0,
        },
    }
    task['state']['next_run_at'] = compute_next_run(task)

    state = get_state(request.app)
    state['tasks'].append(task)
    save_state(request.app)
    sync_task_schedules(request.app)
    return web.json_response(task, status=201)


async def update_task(request):
    task_id = request.match_info.get('task_id')
    state = get_state(request.app)
    task = find_task(state, task_id)
    if not task:
        return web.json_response({'error': 'not_found'}, status=404)

    payload = await request.json()
    try:
        normalized = validate_task_payload(payload)
    except ValueError as ex:
        return web.json_response({'error': str(ex)}, status=400)

    existing_state = task.get('state') or {}
    task.update(normalized)
    task['updated_at'] = now_utc_iso()
    task['state'] = {
        'last_run_at': existing_state.get('last_run_at'),
        'last_status': existing_state.get('last_status', 'idle'),
        'next_run_at': None,
        'incremental_count': int(existing_state.get('incremental_count') or 0),
    }
    if task.get('enabled', True):
        task['state']['next_run_at'] = compute_next_run(task)

    save_state(request.app)
    sync_task_schedules(request.app)
    return web.json_response(task)


async def delete_task(request):
    task_id = request.match_info.get('task_id')
    state = get_state(request.app)
    before = len(state['tasks'])
    state['tasks'] = [t for t in state['tasks'] if t.get('id') != task_id]
    if len(state['tasks']) == before:
        return web.json_response({'error': 'not_found'}, status=404)

    save_state(request.app)
    sync_task_schedules(request.app)
    return web.json_response({'deleted': True})


async def sync_file_item(access_token, item, destination_root, rel_path, mode, summary):
    dest_path = os.path.join(destination_root, rel_path)
    os.makedirs(os.path.dirname(dest_path) or '.', exist_ok=True)

    if mode == 'incremental' and os.path.exists(dest_path):
        remote_dt = parse_graph_datetime(item.get('lastModifiedDateTime'))
        local_dt = datetime.fromtimestamp(os.path.getmtime(dest_path), tz=timezone.utc)
        if remote_dt and remote_dt <= local_dt:
            summary['skipped'] += 1
            return

    await one_drive.download_item(access_token, item.get('id'), dest_path, overwrite=True)
    summary['downloaded'] += 1


async def sync_folder(access_token, folder_id, rel_root, destination_root, mode, summary):
    children = await one_drive.list_children(access_token, parent_id=folder_id)
    for child in children:
        child_name = child.get('name') or child.get('id')
        child_rel = f"{rel_root}/{child_name}" if rel_root else child_name
        if 'folder' in child:
            os.makedirs(os.path.join(destination_root, child_rel), exist_ok=True)
            await sync_folder(access_token, child.get('id'), child_rel, destination_root, mode, summary)
        elif 'file' in child:
            await sync_file_item(access_token, child, destination_root, child_rel, mode, summary)


async def sync_source(access_token, source, destination_root, mode, summary):
    rel_path = (source.get('path') or source.get('name') or source.get('id') or 'item').strip('/').strip()
    if source.get('is_folder'):
        os.makedirs(os.path.join(destination_root, rel_path), exist_ok=True)
        await sync_folder(access_token, source.get('id'), rel_path, destination_root, mode, summary)
    else:
        await sync_file_item(access_token, source, destination_root, rel_path, mode, summary)


async def run_task_by_id(app, task_id, trigger='manual', existing_job_id=None):
    state = get_state(app)
    task = find_task(state, task_id)
    if not task:
        raise ValueError('Task not found')

    jobs = app.setdefault('jobs', {})
    job_id = existing_job_id or str(uuid.uuid4())
    if job_id not in jobs:
        jobs[job_id] = {
            'id': job_id,
            'task_id': task_id,
            'task_name': task.get('name'),
            'trigger': trigger,
            'status': 'running',
            'started_at': now_utc_iso(),
            'completed_at': None,
            'mode': None,
            'summary': {
                'downloaded': 0,
                'skipped': 0,
                'errors': 0,
                'error_messages': [],
            },
        }
    else:
        jobs[job_id]['status'] = 'running'

    try:
        token = acquire_token_silent(app)
        if not token:
            raise ValueError('not_authenticated')
        access_token = token.get('access_token')

        configured_mode = (task.get('strategy') or {}).get('mode', 'full')
        effective_mode = configured_mode
        incrementals_until_full = int((task.get('strategy') or {}).get('incrementals_until_full', 3))
        current_incremental_count = int(((task.get('state') or {}).get('incremental_count')) or 0)

        if configured_mode == 'incremental':
            if current_incremental_count >= incrementals_until_full:
                effective_mode = 'full'
            else:
                effective_mode = 'incremental'

        jobs[job_id]['mode'] = effective_mode

        destination_root = task.get('destination_path') or BACKUP_PATH
        os.makedirs(destination_root, exist_ok=True)
        summary = jobs[job_id]['summary']

        for source in task.get('sources') or []:
            try:
                await sync_source(access_token, source, destination_root, effective_mode, summary)
            except Exception as source_ex:
                summary['errors'] += 1
                summary['error_messages'].append(str(source_ex))

        if summary['errors'] > 0:
            jobs[job_id]['status'] = 'completed_with_errors'
            task_state = task.setdefault('state', {})
            task_state['last_status'] = 'completed_with_errors'
        else:
            jobs[job_id]['status'] = 'completed'
            task_state = task.setdefault('state', {})
            task_state['last_status'] = 'completed'

        if configured_mode == 'incremental':
            if effective_mode == 'full':
                task_state['incremental_count'] = 0
            else:
                task_state['incremental_count'] = current_incremental_count + 1
        else:
            task_state['incremental_count'] = 0

        task_state['last_run_at'] = now_utc_iso()
        task_state['next_run_at'] = compute_next_run(task) if task.get('enabled', True) else None
        task['updated_at'] = now_utc_iso()
        save_state(app)

    except Exception as ex:
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['summary']['errors'] += 1
        jobs[job_id]['summary']['error_messages'].append(str(ex))
        task_state = task.setdefault('state', {})
        task_state['last_status'] = 'error'
        task_state['last_run_at'] = now_utc_iso()
        task_state['next_run_at'] = compute_next_run(task) if task.get('enabled', True) else None
        task['updated_at'] = now_utc_iso()
        save_state(app)

    finally:
        jobs[job_id]['completed_at'] = now_utc_iso()

    return jobs[job_id]


async def run_task_now(request):
    task_id = request.match_info.get('task_id')
    state = get_state(request.app)
    task = find_task(state, task_id)
    if not task:
        return web.json_response({'error': 'not_found'}, status=404)

    jobs = request.app.setdefault('jobs', {})
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        'id': job_id,
        'task_id': task_id,
        'task_name': task.get('name'),
        'trigger': 'manual',
        'status': 'queued',
        'started_at': now_utc_iso(),
        'completed_at': None,
        'mode': None,
        'summary': {
            'downloaded': 0,
            'skipped': 0,
            'errors': 0,
            'error_messages': [],
        },
    }

    async def _runner():
        jobs[job_id]['status'] = 'running'
        await run_task_by_id(request.app, task_id, trigger='manual', existing_job_id=job_id)

    asyncio.create_task(_runner())
    return web.json_response({'started': True, 'task_id': task_id, 'job_id': job_id})


async def get_job(request):
    job_id = request.match_info.get('job_id')
    job = request.app.get('jobs', {}).get(job_id)
    if not job:
        return web.json_response({'error': 'not_found'}, status=404)
    return web.json_response(job)


async def list_jobs(request):
    jobs = list((request.app.get('jobs') or {}).values())
    jobs.sort(key=lambda j: j.get('started_at') or '', reverse=True)
    return web.json_response({'jobs': jobs[:100]})


async def trigger_backup(request):
    state = get_state(request.app)
    tasks = state.get('tasks') or []
    if not tasks:
        return web.json_response({'error': 'no_tasks_configured'}, status=400)

    task_id = tasks[0]['id']
    task_name = tasks[0].get('name')
    jobs = request.app.setdefault('jobs', {})
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        'id': job_id,
        'task_id': task_id,
        'task_name': task_name,
        'trigger': 'manual',
        'status': 'queued',
        'started_at': now_utc_iso(),
        'completed_at': None,
        'mode': None,
        'summary': {
            'downloaded': 0,
            'skipped': 0,
            'errors': 0,
            'error_messages': [],
        },
    }

    async def _runner():
        jobs[job_id]['status'] = 'running'
        await run_task_by_id(request.app, task_id, trigger='manual', existing_job_id=job_id)

    asyncio.create_task(_runner())
    return web.json_response({'started': True, 'task_id': task_id, 'job_id': job_id})


async def list_backups(request):
    token = acquire_token_silent(request.app)
    if not token:
        return web.json_response({'error': 'not_authenticated'}, status=401)

    items = await one_drive.list_children(token.get('access_token'), parent_id=None)
    out = []
    for item in items:
        out.append(
            {
                'id': item.get('id'),
                'name': item.get('name'),
                'size': item.get('size') or 0,
                'lastModifiedDateTime': item.get('lastModifiedDateTime'),
                'file': 'file' in item,
            }
        )
    return web.json_response({'items': out})


def create_app():
    app = web.Application(middlewares=[api_error_middleware])
    static_dir = str(pathlib.Path(__file__).parent.joinpath('static'))
    app.router.add_static('/static', static_dir, show_index=False)

    app['state_store'] = StateStore(STATE_PATH)
    app['state'] = app['state_store'].load()
    app['jobs'] = {}

    app.router.add_get('/', index)

    app.router.add_post('/api/auth/device/start', device_login_start)
    app.router.add_get('/api/auth/device/status', device_login_status)
    app.router.add_post('/api/logout', logout)
    app.router.add_get('/api/status', status)

    app.router.add_get('/api/settings', get_settings)
    app.router.add_put('/api/settings', put_settings)

    app.router.add_get('/api/tasks', get_tasks)
    app.router.add_post('/api/tasks', create_task)
    app.router.add_put('/api/tasks/{task_id}', update_task)
    app.router.add_delete('/api/tasks/{task_id}', delete_task)
    app.router.add_post('/api/tasks/{task_id}/run', run_task_now)

    app.router.add_get('/api/jobs', list_jobs)
    app.router.add_get('/api/jobs/{job_id}', get_job)
    app.router.add_get('/api/onedrive/tree', onedrive_tree)

    app.router.add_post('/api/backup', trigger_backup)
    app.router.add_get('/api/list', list_backups)

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


if __name__ == '__main__':
    web.run_app(create_app(), port=PORT)
