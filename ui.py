"""Local, single-account Telegram backup UI."""
import asyncio
import contextlib
import json
import logging
import os
from pathlib import Path

from aiohttp import web
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from telethon import TelegramClient, errors
from telethon.tl import types
from telethon.tl.types import MessageService

load_dotenv()
ROOT = Path(__file__).parent
def restore_entity(value):
    """Restore formatting entities from Telegram's JSON representation."""
    if isinstance(value, list):
        return [restore_entity(item) for item in value]
    if isinstance(value, dict):
        fields = {key: restore_entity(item) for key, item in value.items() if key != '_'}
        return getattr(types, value['_'])(**fields) if '_' in value else fields
    return value


class BackupUI:
    def __init__(self):
        self.client = None
        self.mongo = AsyncIOMotorClient(os.getenv('MONGODB_URI', 'mongodb://localhost:27017/'), serverSelectionTimeoutMS=5000)
        self.db = self.mongo.telegram_backup
        self.task = None
        self.lock = asyncio.Lock()
        self.phone = self.code_hash = None
        self.chats = {}
        self.job = {'state': 'idle', 'processed': 0, 'skipped': 0, 'detail': ''}

    async def connect(self):
        if self.client is None:
            api_id, api_hash = os.getenv('API_ID'), os.getenv('API_HASH')
            if not api_id or not api_hash:
                raise web.HTTPBadRequest(text='Set API_ID and API_HASH in .env, then restart the UI.')
            Path('sessions').mkdir(exist_ok=True, mode=0o700)
            self.client = TelegramClient('sessions/ui', int(api_id), api_hash)
        if not self.client.is_connected():
            await self.client.connect()
        return self.client

    async def authorized(self):
        client = await self.connect()
        if not await client.is_user_authorized():
            raise web.HTTPUnauthorized(text='Sign in to Telegram first.')
        return client

    async def stop(self):
        if self.task and not self.task.done():
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task

    async def retry(self, operation):
        while True:
            try:
                return await operation()
            except errors.FloodWaitError as exc:
                self.job['detail'] = f'Telegram rate limit: waiting {exc.seconds} seconds.'
                await asyncio.sleep(exc.seconds + 1)

    async def backup(self, source, destination, account):
        key = f'{account}:{source}:{destination}'
        try:
            await self.db.command('ping')
            cursor = await self.db.ui_progress.find_one({'_id': key}) or {}
            latest = await self.retry(lambda: self.client.get_messages(self.chats[source], limit=1))
            upper = latest[0].id if latest else 0
            self.job['detail'] = 'Saving source messages to MongoDB…'
            async for message in self.client.iter_messages(self.chats[source], min_id=cursor.get('last_id', 0), max_id=upper + 1, reverse=True):
                identity = f'{key}:{message.id}'
                saved = await self.db.ui_messages.find_one({'_id': identity}) or {}
                if not saved.get('ready'):
                    media_path = None
                    skipped = isinstance(message, MessageService) or not (message.message or message.media)
                    if not skipped and (message.photo or message.document):
                        folder = Path('media') / str(account) / source / str(message.id)
                        folder.mkdir(parents=True, exist_ok=True)
                        downloaded = await self.retry(lambda: self.client.download_media(message, file=str(folder) + '/'))
                        if not downloaded:
                            raise RuntimeError(f'Could not download attachment for message {message.id}.')
                        media_path = str(Path(downloaded).resolve())
                    elif not skipped and message.media and not isinstance(message.media, types.MessageMediaWebPage):
                        raise RuntimeError(f'Unsupported media type: {type(message.media).__name__} at message {message.id}.')
                    await self.db.ui_messages.update_one({'_id': identity}, {'$set': {
                        'job_key': key, 'source_id': message.id,
                        'message': json.loads(message.to_json()), 'media_path': media_path,
                        'skipped': skipped, 'ready': True,
                    }}, upsert=True)
                await self.db.ui_progress.update_one({'_id': key}, {'$set': {'last_id': message.id}}, upsert=True)
                self.job['detail'] = f'Saved source message {message.id} to MongoDB.'

            # Delivery reads only the persisted archive; no source Message objects are sent.
            pending = self.db.ui_messages.find({'job_key': key, 'ready': True, 'sent': {'$ne': True}}).sort('source_id', 1)
            async for saved in pending:
                if saved.get('skipped'):
                    self.job['skipped'] += 1
                    continue
                stored = saved['message']
                media_path = saved.get('media_path')
                if media_path and not Path(media_path).is_file():
                    raise RuntimeError(f"Saved attachment is missing for message {saved['source_id']}.")
                self.job['detail'] = f"Sending saved message {saved['source_id']}…"
                sent = await self.retry(lambda: self.client.send_message(
                    self.chats[destination], stored.get('message') or '',
                    file=media_path, formatting_entities=restore_entity(stored.get('entities') or []),
                    parse_mode=None, link_preview=isinstance(stored.get('media'), dict) and stored['media'].get('_') == 'MessageMediaWebPage',
                ))
                if not sent:
                    raise RuntimeError('Telegram did not return a sent message.')
                await self.db.ui_messages.update_one({'_id': saved['_id']}, {'$set': {'sent': True, 'destination_message_id': sent.id}})
                self.job['processed'] += 1
                await asyncio.sleep(1)
            self.job.update(state='completed', detail='Backup completed.')
        except asyncio.CancelledError:
            self.job.update(state='stopped', detail='Backup stopped. Start again to resume.')
            raise
        except errors.ChatWriteForbiddenError:
            self.job.update(state='failed', detail='You cannot post to the destination chat. Select a destination where you have permission to send messages, then resume.')
        except Exception:
            logging.exception('Backup failed')
            self.job.update(state='failed', detail='Backup failed. Check container logs for details; verify chat permissions and MongoDB, then start again to resume.')


async def index(request):
    return web.FileResponse(ROOT / 'static' / 'index.html')


async def api(request):
    ui = request.app['ui']
    action = request.match_info['action']
    async with ui.lock:
        if action == 'status':
            client = await ui.connect()
            signed_in = await client.is_user_authorized()
            me = await client.get_me() if signed_in else None
            return web.json_response({'authorized': signed_in, 'name': (me.first_name or str(me.id)) if me else '', 'job': ui.job})
        data = await request.json()
        if action == 'login':
            client = await ui.connect()
            if await client.is_user_authorized():
                raise web.HTTPConflict(text='Already signed in.')
            phone = str(data.get('phone', '')).strip()
            if not phone:
                raise web.HTTPBadRequest(text='Enter your phone number.')
            sent = await client.send_code_request(phone)
            ui.phone, ui.code_hash = phone, sent.phone_code_hash
        elif action == 'verify':
            client = await ui.connect()
            if not ui.phone or not ui.code_hash:
                raise web.HTTPBadRequest(text='Request a login code first.')
            try:
                if data.get('password'):
                    await client.sign_in(password=data['password'])
                else:
                    await client.sign_in(phone=ui.phone, code=data.get('code', ''), phone_code_hash=ui.code_hash)
            except errors.SessionPasswordNeededError:
                return web.json_response({'password_required': True})
            ui.phone = ui.code_hash = None
        elif action == 'chats':
            client = await ui.authorized()
            dialogs = await client.get_dialogs()
            ui.chats = {str(d.id): d.entity for d in dialogs}
            return web.json_response({'chats': [{'id': str(d.id), 'name': d.name or str(d.id)} for d in dialogs]})
        elif action == 'start':
            client = await ui.authorized()
            if ui.task and not ui.task.done():
                raise web.HTTPConflict(text='A backup is already running.')
            source, destination = str(data.get('source')), str(data.get('destination'))
            if source == destination or source not in ui.chats or destination not in ui.chats:
                raise web.HTTPBadRequest(text='Select two different chats from the list.')
            me = await client.get_me()
            ui.job = {'state': 'running', 'processed': 0, 'skipped': 0, 'detail': 'Starting backup…'}
            ui.task = asyncio.create_task(ui.backup(source, destination, me.id))
        elif action == 'stop':
            await ui.authorized()
            await ui.stop()
        elif action == 'logout':
            await ui.stop()
            client = await ui.connect()
            await client.log_out()
            ui.client = None
            ui.chats.clear()
            ui.phone = ui.code_hash = None
        else:
            raise web.HTTPNotFound()
    return web.json_response({'ok': True})


@web.middleware
async def protect(request, handler):
    # Block DNS rebinding and cross-origin access to the local Telegram session.
    if request.host not in {'localhost:8080', '127.0.0.1:8080'}:
        raise web.HTTPForbidden(text='Use http://localhost:8080.')
    if request.path.startswith('/api/'):
        if request.method != 'POST' or request.headers.get('X-Local-UI') != '1' or request.headers.get('Origin') not in {'http://localhost:8080', 'http://127.0.0.1:8080'}:
            raise web.HTTPForbidden(text='Open the local UI to use this endpoint.')
    try:
        response = await handler(request)
    except errors.FloodWaitError as exc:
        response = web.json_response({'error': f'Telegram rate limit. Try again in {exc.seconds} seconds.'}, status=429)
    except errors.RPCError as exc:
        response = web.json_response({'error': f'Telegram rejected the request ({type(exc).__name__}). Check your login details or chat permissions.'}, status=400)
    except web.HTTPException as exc:
        response = web.json_response({'error': exc.text}, status=exc.status)
    except Exception:
        logging.exception('UI request failed')
        response = web.json_response({'error': 'Request failed. Check container logs and connection settings.'}, status=500)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
    return response


async def cleanup(app):
    ui = app['ui']
    await ui.stop()
    if ui.client:
        await ui.client.disconnect()
    ui.mongo.close()


def create_app():
    app = web.Application(middlewares=[protect], client_max_size=8192)
    app['ui'] = BackupUI()
    app.router.add_get('/', index)
    app.router.add_post('/api/{action}', api)
    app.on_cleanup.append(cleanup)
    return app


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    web.run_app(create_app(), host=os.getenv('UI_HOST', '127.0.0.1'), port=8080, access_log=None)
