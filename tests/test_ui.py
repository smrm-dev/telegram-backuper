import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp.test_utils import TestClient, TestServer
from telethon import errors

from ui import BackupUI, create_app


class UITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = TestClient(TestServer(create_app()))
        await self.client.start_server()
        self.ui = self.client.app['ui']
        self.telegram = MagicMock()
        self.telegram.is_connected.return_value = True
        self.telegram.is_user_authorized = AsyncMock(return_value=True)
        self.telegram.get_me = AsyncMock(return_value=SimpleNamespace(id=7, first_name='Test'))
        self.telegram.disconnect = AsyncMock()
        self.ui.client = self.telegram
        self.headers = {'Host': 'localhost:8080', 'Origin': 'http://localhost:8080', 'X-Local-UI': '1'}

    async def asyncTearDown(self):
        await self.client.close()

    async def post(self, action, data=None):
        return await self.client.post('/api/' + action, json=data or {}, headers=self.headers)

    async def test_blocks_foreign_origin_and_host(self):
        for header in ({**self.headers, 'Origin': 'https://example.com'}, {**self.headers, 'Host': 'example.com:8080'}):
            response = await self.client.post('/api/status', json={}, headers=header)
            self.assertEqual(response.status, 403)

    async def test_2fa_transition(self):
        self.ui.phone, self.ui.code_hash = '+123', 'hash'
        self.telegram.sign_in = AsyncMock(side_effect=errors.SessionPasswordNeededError(request=None))
        response = await self.post('verify', {'code': '12345'})
        self.assertTrue((await response.json())['password_required'])
        self.telegram.sign_in = AsyncMock()
        response = await self.post('verify', {'password': 'secret'})
        self.assertEqual(response.status, 200)
        self.assertIsNone(self.ui.code_hash)

    async def test_rejects_same_chat_and_concurrent_job(self):
        self.ui.chats = {'1': object(), '2': object()}
        response = await self.post('start', {'source': '1', 'destination': '1'})
        self.assertEqual(response.status, 400)
        self.ui.task = asyncio.create_task(asyncio.sleep(30))
        response = await self.post('start', {'source': '1', 'destination': '2'})
        self.assertEqual(response.status, 409)

    async def test_logout_stops_before_revoking_session(self):
        self.ui.task = asyncio.create_task(asyncio.sleep(30))
        self.telegram.log_out = AsyncMock()
        response = await self.post('logout')
        self.assertEqual(response.status, 200)
        self.assertTrue(self.ui.task.cancelled())
        self.telegram.log_out.assert_awaited_once()
        self.assertIsNone(self.ui.client)

    async def test_archive_then_send_saved_content(self):
        self.ui.chats = {'1': 'source', '2': 'destination'}
        db = MagicMock()
        db.command = AsyncMock()
        db.ui_progress.find_one = AsyncMock(return_value={'last_id': 10})
        db.ui_progress.update_one = AsyncMock()
        db.ui_messages.find_one = AsyncMock(return_value={})
        db.ui_messages.update_one = AsyncMock()
        self.ui.db = db
        msg = SimpleNamespace(id=11, message='source text', media=None, photo=None, document=None,
                              to_json=lambda: '{"id":11,"message":"archived text","entities":[]}')
        saved = {'_id': '7:1:2:11', 'source_id': 11, 'message': {'message': 'archived text', 'entities': []}, 'ready': True}
        async def pending():
            # The capture checkpoint is durable before the sending phase starts.
            db.ui_progress.update_one.assert_awaited_once()
            yield saved
        db.ui_messages.find.return_value.sort.return_value = pending()
        self.telegram.get_messages = AsyncMock(return_value=[msg])
        async def messages(*args, **kwargs):
            self.assertEqual(kwargs['min_id'], 10)
            yield msg
        self.telegram.iter_messages = messages
        self.telegram.send_message = AsyncMock(return_value=SimpleNamespace(id=55))
        with patch('ui.asyncio.sleep', new=AsyncMock()):
            await self.ui.backup('1', '2', 7)
        self.assertEqual(self.ui.job['state'], 'completed')
        self.assertEqual(self.ui.job['processed'], 1)
        self.telegram.send_message.assert_awaited_once_with('destination', 'archived text', file=None, formatting_entities=[], parse_mode=None, link_preview=False)
        self.telegram.forward_messages.assert_not_called()
        self.assertEqual(db.ui_messages.update_one.await_args_list[-1].args[1]['$set']['sent'], True)

    async def test_media_saved_before_checkpoint_and_reuploaded(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            media = Path(folder).resolve() / 'photo.jpg'
            media.write_bytes(b'test photo')
            self.ui.chats = {'1': 'source', '2': 'destination'}
            db = MagicMock()
            db.command = AsyncMock()
            db.ui_progress.find_one = AsyncMock(return_value={})
            db.ui_progress.update_one = AsyncMock()
            db.ui_messages.find_one = AsyncMock(return_value={})
            db.ui_messages.update_one = AsyncMock()
            self.ui.db = db
            msg = SimpleNamespace(id=12, message='caption', media=object(), photo=True, document=None,
                                  to_json=lambda: '{"message":"caption"}')
            self.telegram.get_messages = AsyncMock(return_value=[msg])
            self.telegram.download_media = AsyncMock(return_value=str(media))
            async def messages(*args, **kwargs):
                yield msg
            async def pending():
                record = db.ui_messages.update_one.await_args_list[0].args[1]['$set']
                self.assertEqual(record['media_path'], str(media))
                self.assertTrue(record['ready'])
                yield {'_id': '7:1:2:12', **record}
            self.telegram.iter_messages = messages
            db.ui_messages.find.return_value.sort.return_value = pending()
            self.telegram.send_message = AsyncMock(side_effect=RuntimeError('send failed'))
            with self.assertLogs(level='ERROR') as logs:
                await self.ui.backup('1', '2', 7)
            if self.telegram.send_message.await_args is None:
                self.fail(str(logs.output))
            self.assertEqual(self.ui.job['state'], 'failed')
            self.assertEqual(self.telegram.send_message.await_args.kwargs['file'], str(media))
            # Failure does not mark archived data as sent.
            self.assertEqual(db.ui_messages.update_one.await_count, 1)
            self.telegram.forward_messages.assert_not_called()


if __name__ == '__main__':
    unittest.main()
