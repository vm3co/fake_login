import pytest
import pytest_asyncio
from sqlalchemy import inspect
from backend.repository.models import Base, User, SendTask, Acct, SendLogStats, JobRun

@pytest.mark.asyncio
async def test_models_inspection():
    """
    Verify that SQLAlchemy models are correctly defined and mapped.
    Since we cannot use SQLite with Postgres-specific types (ARRAY, JSONB),
    we inspect the mappers instead of creating tables.
    """
    
    # Check User model
    user_mapper = inspect(User)
    assert user_mapper.local_table.name == "users"
    assert "username" in user_mapper.columns
    for column in (
        "acct_id",
        "email",
        "full_name",
        "acct_full_name_2nd",
        "acct_locale_code",
        "acct_create_ut",
        "acct_update_ut",
        "acct_update_scrt_ut",
        "acct_last_login_ut",
        "acct_last_login_info",
        "admin_role",
        "agent_role",
        "orgs",
        "is_active",
    ):
        assert column not in user_mapper.columns
    
    # Check SendTask model
    task_mapper = inspect(SendTask)
    assert task_mapper.local_table.name == "sendtasks"
    assert "sendtask_uuid" in task_mapper.columns
    assert "sendtask_owner_gid" in task_mapper.columns

    acct_mapper = inspect(Acct)
    assert acct_mapper.local_table.name == "accts"
    for column in (
        "acct_uuid",
        "acct_locale_code",
        "acct_create_ut",
        "acct_update_ut",
        "acct_update_scrt_ut",
        "acct_last_login_ut",
        "acct_last_login_info",
        "admin_role",
        "agent_role",
    ):
        assert column in acct_mapper.columns

    job_mapper = inspect(JobRun)
    assert job_mapper.local_table.name == "job_runs"
    for column in (
        "job_id",
        "source",
        "job_type",
        "owner_username",
        "status",
        "result",
        "error",
        "started_at",
        "finished_at",
    ):
        assert column in job_mapper.columns
    assert job_mapper.columns["started_at"].type.timezone is True
    assert job_mapper.columns["finished_at"].type.timezone is True

    # Check relationships or other keys if any
    # (Currently no relationships defined in the simple models)
    
    print("All models inspected successfully.")
