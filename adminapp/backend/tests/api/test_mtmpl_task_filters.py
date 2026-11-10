"""
GET /api/get_mtmpl_task_filters 的權限與聚合測試。

所有 DB 存取皆以 AsyncMock 取代，登入身分以 app.dependency_overrides 注入，
不連線、不改動任何真實資料庫。
"""
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient

from backend.main import app
from backend.api.user_api import get_current_user


def _task(sendtask_id, mail_template, owner_gid, uuid):
    return SimpleNamespace(
        sendtask_id=sendtask_id,
        mail_template=mail_template,
        sendtask_owner_gid=owner_gid,
        sendtask_uuid=uuid,
    )


# 兩筆同名 (Phishing-A) → mail_template 應去重取聯集；
# Phishing-B 的 mail_template 為 None（不可報錯）；空 sendtask_id 應被略過。
ALL_TASKS = [
    _task("Phishing-A", ["m1", "m2"], ["org1"], "u-a"),
    _task("Phishing-A", ["m2", "m3", None], ["org2"], "u-a2"),
    _task("Phishing-B", None, ["org2"], "u-b"),
    _task("", ["mX"], ["org1"], "u-empty"),
]


@pytest.fixture
def as_user():
    """注入登入身分；測試結束清除 override。"""
    def _set(user_type, username="tester", acct_uuid="acct-1", admin_role=False, orgs=None):
        app.dependency_overrides[get_current_user] = lambda: {
            "user_type": user_type,
            "username": username,
            "acct_uuid": acct_uuid,
            "admin_role": admin_role,
            "orgs": orgs or [],
        }
    yield _set
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_sees_all_and_unions(async_client: AsyncClient, as_user):
    as_user("admin", admin_role=True)
    with patch("backend.api.data_api.db_controller") as mock_db:
        mock_db.get = AsyncMock(return_value=ALL_TASKS)
        resp = await async_client.get("/api/get_mtmpl_task_filters")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    data = body["data"]

    # 無 sendtask_id 的任務被略過，名稱排序
    assert [d["sendtask_id"] for d in data] == ["Phishing-A", "Phishing-B"]

    a = next(d for d in data if d["sendtask_id"] == "Phishing-A")
    assert a["mail_template"] == ["m1", "m2", "m3"]  # 同名聯集去重排序、None 被濾掉

    b = next(d for d in data if d["sendtask_id"] == "Phishing-B")
    assert b["mail_template"] == []  # mail_template=None → 空陣列且不報錯

    # 最小揭露：每個 item 只有兩個公開 key
    for d in data:
        assert set(d.keys()) == {"sendtask_id", "mail_template"}


@pytest.mark.asyncio
async def test_platform_admin_cannot_see_tasks(async_client: AsyncClient, as_user):
    as_user("platform_admin")
    with patch("backend.api.data_api.db_controller") as mock_db:
        mock_db.get = AsyncMock(return_value=ALL_TASKS)
        resp = await async_client.get("/api/get_mtmpl_task_filters")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_user_filtered_by_orgs(async_client: AsyncClient, as_user):
    as_user("user", username="u1@example.com", orgs=["org1"])
    with patch("backend.api.data_api.db_controller") as mock_db:
        mock_db.get = AsyncMock(return_value=ALL_TASKS)
        resp = await async_client.get("/api/get_mtmpl_task_filters")

    assert resp.status_code == 200
    data = resp.json()["data"]
    # 只有 owner_gid 與 acct.orgs(["org1"]) 有交集的任務 → 僅 u-a (Phishing-A)
    assert [d["sendtask_id"] for d in data] == ["Phishing-A"]
    assert data[0]["mail_template"] == ["m1", "m2"]  # u-a2(org2) 已被排除，故不含 m3


@pytest.mark.asyncio
async def test_user_empty_orgs_returns_empty(async_client: AsyncClient, as_user):
    as_user("user", orgs=[])
    with patch("backend.api.data_api.db_controller") as mock_db:
        mock_db.get = AsyncMock(return_value=ALL_TASKS)
        resp = await async_client.get("/api/get_mtmpl_task_filters")

    assert resp.status_code == 200
    assert resp.json()["data"] == []
    mock_db.get.assert_not_called()  # orgs 空 → 不得退化為查全部任務


@pytest.mark.asyncio
async def test_user_not_found_returns_empty(async_client: AsyncClient, as_user):
    as_user("user", orgs=[])
    with patch("backend.api.data_api.db_controller") as mock_db:
        mock_db.get = AsyncMock(return_value=ALL_TASKS)
        resp = await async_client.get("/api/get_mtmpl_task_filters")

    assert resp.status_code == 200
    assert resp.json()["data"] == []


@pytest.mark.asyncio
async def test_customer_only_authorized_tasks(async_client: AsyncClient, as_user):
    as_user("customer", username="cust1")
    # sendtasks 內含一筆無 uuid 的髒資料，應被安全略過
    fake_customer = SimpleNamespace(sendtasks=[{"uuid": "u-b"}, {"no_uuid": 1}])
    task_b = _task("Phishing-B", ["mZ"], ["org2"], "u-b")
    with patch("backend.api.data_api.db_controller") as mock_db:
        mock_db.get_one = AsyncMock(return_value=fake_customer)
        mock_db.get = AsyncMock(return_value=[task_b])
        resp = await async_client.get("/api/get_mtmpl_task_filters")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [d["sendtask_id"] for d in data] == ["Phishing-B"]
    assert data[0]["mail_template"] == ["mZ"]

    # 查詢必須限制在客戶授權的 uuid（無法由 request 自行擴充）
    _, kwargs = mock_db.get.call_args
    assert set(kwargs["filters"]["sendtask_uuid"]) == {"u-b"}


@pytest.mark.asyncio
async def test_customer_no_authorized_tasks_returns_empty(async_client: AsyncClient, as_user):
    as_user("customer")
    fake_customer = SimpleNamespace(sendtasks=[])
    with patch("backend.api.data_api.db_controller") as mock_db:
        mock_db.get_one = AsyncMock(return_value=fake_customer)
        mock_db.get = AsyncMock(return_value=[])
        resp = await async_client.get("/api/get_mtmpl_task_filters")

    assert resp.status_code == 200
    assert resp.json()["data"] == []
    mock_db.get.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_user_type_forbidden(async_client: AsyncClient, as_user):
    as_user("mystery")
    with patch("backend.api.data_api.db_controller") as mock_db:
        mock_db.get = AsyncMock(return_value=ALL_TASKS)
        resp = await async_client.get("/api/get_mtmpl_task_filters")

    assert resp.status_code == 403
    assert resp.json()["detail"] == "無權存取任務"
