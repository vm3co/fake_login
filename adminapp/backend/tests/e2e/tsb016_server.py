import os
import asyncio
import sys
from contextlib import asynccontextmanager
sys.path.insert(0, '/app')
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse
from sqlalchemy import text, insert, select
from backend.repository.database import Base, engine, async_session
from backend.repository.models import Mtmpl, Acct, User, CustomerAcct
from backend.core.security import hash_password
from backend.api import user_api, data_api, job_api, task_backup_api
from backend.services.db_user import DBUser
from backend.services.task_sync_core import TaskSyncService
from backend.services.se2_task_reader import TaskSnapshot, TaskNotFound, TaskReadError
from backend.services.job_queue import job_queue

state = {'version': 100, 'count': 3, 'missing': False}

class Reader:
    async def read_sendtasks(self, **kwargs):
        return [(await self.read_sendtask('mobile-task'))['data']]

    async def read_sendtask(self, uuid, **kwargs):
        if state['missing']:
            raise TaskNotFound('Controlled remote missing')
        return {'data': {'sendtask_uuid': uuid, 'sendtask_create_ut': state['version'],
            'sendtask_owner_gid': ['audit-org'], 'sendtask_id': 'Mobile task' if uuid == 'mobile-task' else 'E2E task', 'pre_test_enable': False}}

    async def read_task_snapshot(self, uuid, **kwargs):
        if state.get('block_after_one'):
            state['read_count'] = state.get('read_count', 0) + 1
            if state['read_count'] > 1:
                await asyncio.Event().wait()
        if uuid == state.get('fail_uuid'):
            raise TaskReadError('controlled_page_failure')
        if uuid == state.get('wait_uuid'):
            await asyncio.Event().wait()
        record = (await self.read_sendtask(uuid))['data']
        return TaskSnapshot(task=record, metadata={'pause': False, 'stop_time_new': -1,
            'summary': {'person_count': state['count']}},
            sendlogs=[{'uuid': f"{'' if uuid == 'e2e-task' else uuid + '-'}v{state['version']}-person-{number}", 'target_email': f"v{state['version']}-{number}@example.test",
                'person_info': f'Person {number}', 'template_uuid': 'audit-template', 'plan_time': 1794960000,
                'send_time': 1794960000, 'send_res': 'True',
                **{f'{base}_{suffix}': [] for base in ('access', 'click', 'file') for suffix in ('time', 'src', 'dev')}}
                for number in range(state['count'])], testcase={'testcase_uuid': uuid, 'testcase_id': 'E2E'},
            create_ut=state['version'], sendlog_type='test')

db = DBUser(task_sync=TaskSyncService(async_session, Reader()))
job_api.db_user = db

@asynccontextmanager
async def lifespan(app):
    if os.environ.get('POSTGRES_HOST') != 'tsb016-e2e-postgres' or os.environ.get('REDIS_HOST') != 'tsb016-e2e-redis':
        raise RuntimeError('Dedicated E2E hosts required')
    async with engine.begin() as conn:
        assert await conn.scalar(text('SELECT current_database()')) == 'tsb_schema_test'
        await conn.execute(text('CREATE SEQUENCE IF NOT EXISTS job_run_queue_sequence'))
        await conn.run_sync(Base.metadata.create_all)
        fresh = not await conn.scalar(select(Mtmpl.id).limit(1))
        if fresh:
            await conn.execute(insert(Mtmpl).values(mtmpl_uuid='audit-template', mtmpl_title='Historical subject'))
        for name, org in [('same', 'audit-org'), ('other', 'other-org')]:
            if not fresh:
                continue
            email = f'{name}@example.test'
            await conn.execute(insert(Acct).values(acct_uuid=name, acct_id=email, acct_email=email,
                acct_full_name=name, is_active=True, admin_role=False, orgs=[org]))
            await conn.execute(insert(User).values(acct_uuid=name, username=email,
                password_hash=hash_password('audit-test-only')))
        if fresh:
            await conn.execute(insert(CustomerAcct).values(customer_uuid='audit-customer',
                customer_name='customer@example.test', customer_full_name='Audit customer', acct_uuid='same',
                password_hash=hash_password('audit-test-only'), sendtasks=[{'uuid': 'e2e-task'}]))
    if fresh:
        await db.get_task_sync().sync('e2e-task', orgs=None)
    await job_queue.start()
    yield
    await job_queue.stop()
    await engine.dispose()

app = FastAPI(lifespan=lifespan)
app.include_router(user_api.get_router(db), prefix='/api')
app.include_router(data_api.get_router(db), prefix='/api')
app.include_router(job_api.router, prefix='/api')
app.include_router(task_backup_api.router, prefix='/api')

@app.post('/audit/remote')
async def remote(value: dict):
    state.update(value)
    return state

app.mount('/assets', StaticFiles(directory='/app/frontend/dist/assets'), name='assets')
@app.get('/{path:path}')
async def frontend(path: str):
    return FileResponse('/app/frontend/dist/index.html')