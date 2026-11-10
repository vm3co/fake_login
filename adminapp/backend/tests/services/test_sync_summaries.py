from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.services.db_user import DBUser


@pytest.mark.asyncio
async def test_refresh_mtmpl_returns_added_and_removed_names():
    service = DBUser()
    remote = [
        {"mtmpl_uuid": "keep", "mtmpl_title": "保留標題", "mtmpl_content": "large"},
        {"mtmpl_uuid": "new", "mtmpl_title": "新增標題", "mtmpl_name": "新增名稱", "mtmpl_content": "large"},
    ]
    local = [
        SimpleNamespace(mtmpl_uuid="keep", mtmpl_title="舊標題", mtmpl_name="保留名稱"),
        SimpleNamespace(mtmpl_uuid="old", mtmpl_title="刪除標題", mtmpl_name="刪除名稱"),
    ]

    with patch.object(service, "get_se2_mtmpl", new=AsyncMock(return_value=remote)), \
         patch("backend.services.db_user.db_controller.get", new=AsyncMock(return_value=local)), \
         patch("backend.services.db_user.db_controller.upsert", new=AsyncMock()), \
         patch("backend.services.db_user.db_controller.delete", new=AsyncMock()):
        result = await service.refresh_mtmpl()

    assert result["synced_count"] == 2
    assert result["added_templates"] == [{"mtmpl_uuid": "new", "title": "新增名稱"}]
    assert result["removed_templates"] == [{"mtmpl_uuid": "old", "title": "刪除名稱"}]
    assert "mtmpl_content" not in result["added_templates"][0]


@pytest.mark.asyncio
async def test_refresh_mtmpl_empty_remote_does_not_delete_local_templates():
    service = DBUser()
    delete = AsyncMock()

    with patch.object(service, "get_se2_mtmpl", new=AsyncMock(return_value=[])), \
         patch("backend.services.db_user.db_controller.delete", delete):
        result = await service.refresh_mtmpl()

    assert result["synced_count"] == 0
    delete.assert_not_awaited()
