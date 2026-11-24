from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, func, or_, select
from starlette.concurrency import run_in_threadpool

from backend.api.user_api import get_current_user
from backend.repository.database import async_session
from backend.repository.models import TaskBackup, TaskBackupDetail
from backend.services.task_backup_access import backup_scope, require_backup_access, scoped_backups
from backend.services.sendlog_query import project_events, sendlog_query
from backend.services.excel_utils import backup_workbook


router = APIRouter(prefix="/task_backups", tags=["task_backups"])


class BackupDetailsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(default=1, ge=1)
    rowsPerPage: int = Field(default=20, ge=1, le=200)
    acctControl: list[bool] = Field(default_factory=lambda: [True] * 5, min_length=5, max_length=5)
    searchText: str | None = Field(default=None, max_length=500)
    dateFrom: date | None = None
    dateTo: date | None = None
    resultType: Literal["all", "send", "notyet", "failed", "notTriggered", "triggered"] = "all"
    showAccessed: bool = False
    showClicked: bool = False
    showFiled: bool = False
    sort: Literal["asc", "desc"] = "desc"
    sortBy: Literal["uuid", "target_email", "person_info", "plan_time", "send_time", "send_res"] = "plan_time"
    filterIp: str | None = Field(default=None, max_length=2000)
    paginate: Literal[True] = True

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.dateFrom and self.dateTo and self.dateFrom > self.dateTo:
            raise ValueError("dateFrom must not be after dateTo")
        return self


def header(backup, detail_count):
    fields = (
        "backup_id", "source_task_uuid", "source_create_ut", "source_local_generation_id", "sendtask_id",
        "owner_gids", "backed_up_at", "reason", "snapshot_schema_version", "stats_snapshot_at",
        "latest_remote_status", "last_remote_checked_at", "last_remote_create_ut", "recreated_detected_at",
    )
    return {**{field: getattr(backup, field) for field in fields}, "detail_count": detail_count,
            "actions": {"read": True, "export": True, "delete": True}}


def payload(backup, detail_count):
    return {**header(backup, detail_count), "task_snapshot": backup.task_snapshot,
            "stats_snapshot": backup.stats_snapshot, "mail_template_snapshot": backup.mail_template_snapshot}


@router.get("")
async def list_backups(
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=200),
    search: str | None = Query(default=None, max_length=500),
    sort_by: Literal["backed_up_at", "source_create_ut", "sendtask_id", "last_remote_checked_at"] = "backed_up_at",
    sort: Literal["asc", "desc"] = "desc",
    recreated: bool | None = None,
    observation: Literal["recreated", "unproven", "unchecked", "error"] | None = None,
    remote_status: Literal["unchecked", "present", "missing", "error"] | None = None,
    reason: Literal["remote_missing", "remote_recreated", "manual_reload"] | None = None,
    backed_up_from: date | None = None, backed_up_to: date | None = None,
    current_user: dict = Depends(get_current_user),
):
    scope = backup_scope(current_user)
    if backed_up_from and backed_up_to and backed_up_from > backed_up_to:
        raise HTTPException(status_code=422, detail="Invalid backup date range")
    statement = scoped_backups(scope)
    if observation == "recreated":
        statement = statement.where(TaskBackup.recreated_detected_at.isnot(None))
    elif observation == "unproven":
        statement = statement.where(TaskBackup.recreated_detected_at.is_(None))
    elif observation in {"unchecked", "error"}:
        statement = statement.where(TaskBackup.latest_remote_status == observation)
    if search:
        pattern = f"%{search}%"
        statement = statement.where(or_(TaskBackup.sendtask_id.ilike(pattern), TaskBackup.source_task_uuid.ilike(pattern)))
    if recreated is not None:
        statement = statement.where(TaskBackup.recreated_detected_at.isnot(None) if recreated else TaskBackup.recreated_detected_at.is_(None))
    if remote_status:
        statement = statement.where(TaskBackup.latest_remote_status == remote_status)
    if reason:
        statement = statement.where(TaskBackup.reason == reason)
    for value, end in ((backed_up_from, False), (backed_up_to, True)):
        if value:
            boundary = datetime.combine(value, datetime.min.time(), ZoneInfo("Asia/Taipei"))
            statement = statement.where(TaskBackup.backed_up_at < boundary + timedelta(days=1) if end else TaskBackup.backed_up_at >= boundary)
    count = select(func.count()).select_from(statement.subquery())
    detail_count = select(func.count()).where(TaskBackupDetail.backup_id == TaskBackup.backup_id).correlate(TaskBackup).scalar_subquery()
    column = getattr(TaskBackup, sort_by)
    order = column.asc().nulls_last() if sort == "asc" else column.desc().nulls_last()
    async with async_session() as session:
        async with session.begin():
            await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            total = await session.scalar(count)
            rows = (await session.execute(statement.add_columns(detail_count).order_by(order, TaskBackup.backup_id)
                                          .offset((page - 1) * page_size).limit(page_size))).all()
    return {"status": "success", "data": [header(backup, size) for backup, size in rows],
            "total_count": total, "page": page, "page_size": page_size}


@router.get("/{backup_id}")
async def get_backup(backup_id: str, current_user: dict = Depends(get_current_user)):
    scope = backup_scope(current_user)
    async with async_session() as session:
        async with session.begin():
            backup = await require_backup_access(session, backup_id, scope, lock=True)
            size = await session.scalar(select(func.count()).where(TaskBackupDetail.backup_id == backup_id))
            data = payload(backup, size)
    return {"status": "success", "data": data}


@router.post("/{backup_id}/details")
async def get_backup_details(backup_id: str, request: BackupDetailsRequest, current_user: dict = Depends(get_current_user)):
    scope = backup_scope(current_user)
    options = request.model_copy(update={
        "dateFrom": request.dateFrom.isoformat() if request.dateFrom else None,
        "dateTo": request.dateTo.isoformat() if request.dateTo else None,
    })
    statement, count = sendlog_query(TaskBackupDetail, TaskBackupDetail.backup_id == backup_id, options, timezone=ZoneInfo("Asia/Taipei"))
    async with async_session() as session:
        async with session.begin():
            await require_backup_access(session, backup_id, scope, lock=True)
            total = await session.scalar(count)
            rows = (await session.scalars(statement)).all()
            data = []
            for row in rows:
                raw = {column.name: getattr(row, column.name) for column in TaskBackupDetail.__table__.columns}
                data.append({**raw, "display": project_events(raw, request.filterIp)})
    return {"status": "success", "data": data, "total_count": total, "page": request.page, "page_size": request.rowsPerPage}


@router.get("/{backup_id}/export.xlsx")
async def export_backup(backup_id: str, current_user: dict = Depends(get_current_user)):
    scope = backup_scope(current_user)
    async with async_session() as session:
        async with session.begin():
            backup = await require_backup_access(session, backup_id, scope, lock=True)
            rows = (await session.scalars(select(TaskBackupDetail).where(TaskBackupDetail.backup_id == backup_id)
                                         .order_by(TaskBackupDetail.id))).all()
            details = [{column.name: getattr(row, column.name) for column in TaskBackupDetail.__table__.columns} for row in rows]
            data = payload(backup, len(details))
    content = await run_in_threadpool(backup_workbook, data, details)
    filename = f"task-backup-{backup_id}.xlsx"
    return StreamingResponse(BytesIO(content), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.delete("/{backup_id}")
async def delete_backup(backup_id: str, confirm_delete: str | None = None, current_user: dict = Depends(get_current_user)):
    scope = backup_scope(current_user)
    async with async_session() as session:
        async with session.begin():
            await require_backup_access(session, backup_id, scope, lock=True)
            if confirm_delete != "true":
                raise HTTPException(status_code=400, detail="Explicit confirm_delete=true is required")
            await session.execute(delete(TaskBackup).where(TaskBackup.backup_id == backup_id))
    return {"status": "success", "deleted_backup_id": backup_id, "backups_changed": True}