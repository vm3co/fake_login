import asyncio
import os
import httpx
from fastapi import FastAPI
from app.api.record_api import router
from sqlalchemy import text
from app.workers.persistence_worker import PersistenceWorker
from app.repository.db_controller import db_controller

async def main():
    assert os.environ.get('POSTGRES_HOST') == 'tsb016-e2e-postgres'
    assert os.environ.get('POSTGRES_DB') == 'tsb_schema_test'
    assert os.environ.get('REDIS_HOST') == 'tsb016-e2e-redis'
    worker = PersistenceWorker()
    client = await worker.redis.get_client()
    assert await client.ping()
    assert await client.llen('buffer:trigger_events') == 0
    before = (await db_controller.execute(text('SELECT uuid,second_input_info FROM send_log_details ORDER BY uuid'))).all()
    before = {row[0]: row[1] for row in before}
    history = (await db_controller.execute(text('SELECT backup_id,uuid,second_input_info FROM task_backup_details ORDER BY backup_id,uuid'))).all()
    completed = asyncio.Event()
    original = worker.process_event
    async def tracked(event):
        await original(event)
        if event['uuid'] == 'v300-person-0':
            completed.set()
    worker.process_event = tracked
    app = FastAPI()
    app.include_router(router, prefix='/api')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://audit') as http:
        for uuid in ['v100-person-0', 'v200-person-0', 'v300-person-0']:
            response = await http.post('/api/input', json={
                'url': f'https://example.test/trigger/page/audit/{uuid}',
                'input_data': 'masked-audit'}, headers={'User-Agent': 'isolated-e2e'})
            assert response.status_code == 200 and response.json()['status'] == 'success'
    assert await client.llen('buffer:trigger_events') == 3
    task = asyncio.create_task(worker.start())
    try:
        await asyncio.wait_for(completed.wait(), timeout=15)
        rows = await db_controller.execute(text("SELECT uuid,second_input_info FROM send_log_details WHERE sendtask_uuid='e2e-task' ORDER BY uuid"))
        rows = rows.all()
        assert len(rows) == 2
        assert rows[0][0] == 'v300-person-0' and rows[0][1] == (before['v300-person-0'] or []) + ['masked-audit'], rows
        assert rows[1][1] == before[rows[1][0]], rows
        backups = await db_controller.execute(text('SELECT backup_id,uuid,second_input_info FROM task_backup_details ORDER BY backup_id,uuid'))
        assert backups.all() == history
        others = (await db_controller.execute(text("SELECT uuid,second_input_info FROM send_log_details WHERE sendtask_uuid<>'e2e-task'"))).all()
        assert all(row[1] == before[row[0]] for row in others)
        assert await client.llen('buffer:trigger_events') == 0
        print('PASS trigger HTTP ASGI -> Redis BLPOP -> PersistenceWorker -> SQL: old A/B ignored, C updated, backup immutable')
    finally:
        await worker.stop()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await client.aclose()

asyncio.run(main())