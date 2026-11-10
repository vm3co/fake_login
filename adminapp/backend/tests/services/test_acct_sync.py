import pandas as pd
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.repository.models import Acct, User
from backend.services.db_user import DBUser


@pytest.mark.asyncio
async def test_get_se2_accts_preserves_all_known_fields_and_normalizes_values():
    source_accounts = pd.DataFrame([
        {
            "acct_uuid": "a85243aa17e84f0989a289a3ee2c2c02",
            "acct_id": "mike.xu@acercsi.com",
            "acct_full_name": "mike.xu",
            "acct_full_name_2nd": None,
            "acct_email": "mike.xu@acercsi.com",
            "acct_locale_code": "zh-TW",
            "acct_activate": "false",
            "acct_create_ut": 1758685340.0,
            "acct_update_ut": 1784012010.0,
            "acct_update_scrt_ut": 1784012010.0,
            "acct_last_login_ut": 1787553505.0,
            "acct_last_login_info": '{"cur_ip": "127.0.0.1"}',
            "admin_role": True,
            "agent_role": False,
            "orgs": ["org-1"],
        }
    ])

    with patch("backend.services.db_user.get_se2_data.get_accts", new=AsyncMock(return_value=source_accounts)):
        accounts = await DBUser().get_se2_accts()

    assert accounts == [{
        "acct_uuid": "a85243aa17e84f0989a289a3ee2c2c02",
        "acct_id": "mike.xu@acercsi.com",
        "acct_full_name": "mike.xu",
        "acct_full_name_2nd": None,
        "acct_email": "mike.xu@acercsi.com",
        "acct_locale_code": "zh-TW",
        "acct_create_ut": 1758685340,
        "acct_update_ut": 1784012010,
        "acct_update_scrt_ut": 1784012010,
        "acct_last_login_ut": 1787553505,
        "acct_last_login_info": '{"cur_ip": "127.0.0.1"}',
        "admin_role": True,
        "agent_role": False,
        "orgs": ["org-1"],
        "is_active": False,
    }]


@pytest.mark.asyncio
async def test_get_se2_accts_omits_orgs_when_organization_lookup_failed():
    source_accounts = pd.DataFrame([
        {
            "acct_uuid": "a85243aa17e84f0989a289a3ee2c2c02",
            "acct_id": "mike.xu@acercsi.com",
            "acct_full_name": "mike.xu",
            "acct_email": "mike.xu@acercsi.com",
            "acct_activate": True,
            "orgs": None,
            "_orgs_lookup_failed": True,
        }
    ])

    with patch("backend.services.db_user.get_se2_data.get_accts", new=AsyncMock(return_value=source_accounts)):
        accounts = await DBUser().get_se2_accts()

    assert "orgs" not in accounts[0]
    assert accounts[0]["is_active"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("lookup", "expected_sql"),
    [
        ({"acct_uuid": "a85243aa17e84f0989a289a3ee2c2c02"}, "users.acct_uuid"),
        ({"acct_id": "Mike.Xu@AcerCSI.com"}, "lower(accts.acct_id)"),
    ],
)
async def test_get_registered_account_joins_user_to_authoritative_acct(lookup, expected_sql):
    expected = (object(), object())
    result = MagicMock()
    result.first.return_value = expected
    session = AsyncMock()
    session.execute.return_value = result
    context = AsyncMock()
    context.__aenter__.return_value = session

    with patch("backend.services.db_user.db_controller.get_session", return_value=context):
        actual = await DBUser().get_registered_account(**lookup)

    assert actual == expected
    statement = session.execute.await_args.args[0]
    statement_sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "JOIN accts ON users.acct_uuid = accts.acct_uuid" in statement_sql
    assert expected_sql in statement_sql