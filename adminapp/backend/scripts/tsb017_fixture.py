import asyncio
import os
import sys

from sqlalchemy import insert, select, text

from backend.repository.database import Base, engine
from backend.repository.models import SendTask, SendLogDetail, SendLogStats
from backend.repository.task_backup_schema import migrate_task_backup_schema
from backend.repository.task_reload_schema import migrate_task_reload_schema


async def main():
    if os.environ.get('POSTGRES_HOST') not in {'tsb017-source', 'tsb017-restore'}:
        raise RuntimeError('Only dedicated TSB-017 synthetic hosts are allowed')
    mode = sys.argv[1]
    async with engine.begin() as connection:
        if await connection.scalar(text('SELECT current_database()')) != 'tsb017_synthetic':
            raise RuntimeError('Only tsb017_synthetic database is allowed')
        await connection.execute(text('CREATE SEQUENCE IF NOT EXISTS job_run_queue_sequence'))
        if mode == 'seed':
            await connection.run_sync(Base.metadata.create_all)
            await connection.execute(insert(SendTask).values(
                sendtask_uuid='synthetic-task', sendtask_id='Synthetic legacy task',
                sendtask_owner_gid=['synthetic-org'], sendtask_create_ut=100))
            for number in range(3):
                await connection.execute(insert(SendLogDetail).values(
                    uuid=f'synthetic-person-{number}', sendtask_uuid='synthetic-task',
                    target_email=f'person-{number}@example.test',
                    second_input_time=[10, 20], second_input_info=['masked-first', 'masked-last']))
            await connection.execute(insert(SendLogStats).values(
                sendtask_uuid='synthetic-task', totalplanned=3))
            await connection.execute(text('DROP TABLE task_reload_operations, task_backup_details, task_backups'))
            await connection.execute(text('ALTER TABLE sendtasks DROP COLUMN local_generation_id, DROP COLUMN sync_revision'))
        elif mode == 'migrate':
            await migrate_task_backup_schema(connection)
            await migrate_task_reload_schema(connection)
            before = (await connection.execute(select(SendTask.local_generation_id, SendTask.sync_revision))).one()
            await migrate_task_backup_schema(connection)
            await migrate_task_reload_schema(connection)
            after = (await connection.execute(select(SendTask.local_generation_id, SendTask.sync_revision))).one()
            assert before == after and before[0] and before[1] == 0
            assert await connection.scalar(text('SELECT count(*) FROM task_backups')) == 0
            assert await connection.scalar(text('SELECT count(*) FROM task_reload_operations')) == 0
        else:
            raise RuntimeError('Expected seed or migrate')
        assert await connection.scalar(text('SELECT count(*) FROM sendtasks')) == 1
        assert await connection.scalar(text('SELECT count(*) FROM send_log_details')) == 3
        assert await connection.scalar(text('SELECT totalplanned FROM sendlog_stats')) == 3
        rows = (await connection.execute(text('SELECT second_input_time, second_input_info FROM send_log_details'))).all()
        assert all(row[0] == [10, 20] and row[1] == ['masked-first', 'masked-last'] for row in rows)
    await engine.dispose()
    print(f'PASS synthetic {mode}: task/details/statistics/event arrays preserved')


asyncio.run(main())