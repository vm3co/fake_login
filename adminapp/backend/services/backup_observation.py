from sqlalchemy import select

from backend.repository.models import TaskBackup
from backend.services.se2_task_reader import TaskReadError, normalize_timestamp


async def update_backup_observations(session, *, task_uuid, scope, checked_at, status, create_ut=None, backup_ids=None):
    if status not in {"present", "missing", "error"}:
        raise ValueError("Invalid remote observation status")
    if checked_at.tzinfo is None:
        raise ValueError("Observation time must include a timezone")
    if status == "present":
        create_ut = normalize_timestamp(create_ut)
    else:
        create_ut = None
    statement = select(TaskBackup).where(TaskBackup.source_task_uuid == task_uuid)
    if scope is not None:
        statement = statement.where(TaskBackup.owner_gids.overlap(list(scope)))
    if backup_ids is not None:
        statement = statement.where(TaskBackup.backup_id.in_(backup_ids))
    backups = (await session.scalars(statement.order_by(TaskBackup.backup_id).with_for_update())).all()
    results = []
    for backup in backups:
        stale = backup.last_remote_checked_at is not None and backup.last_remote_checked_at >= checked_at
        outcome = status
        try:
            source_create_ut = normalize_timestamp(backup.source_create_ut)
        except TaskReadError:
            source_create_ut = None
            if status == "present":
                outcome = "error"
        if not stale:
            backup.latest_remote_status = outcome
            backup.last_remote_checked_at = checked_at
            backup.last_remote_create_ut = create_ut if outcome == "present" else None
            if outcome == "present" and source_create_ut != create_ut and backup.recreated_detected_at is None:
                backup.recreated_detected_at = checked_at
        results.append({
            "backup_id": backup.backup_id, "source_task_uuid": task_uuid,
            "latest_remote_status": backup.latest_remote_status,
            "last_remote_checked_at": backup.last_remote_checked_at.isoformat() if backup.last_remote_checked_at else None,
            "last_remote_create_ut": backup.last_remote_create_ut,
            "recreated_detected_at": backup.recreated_detected_at.isoformat() if backup.recreated_detected_at else None,
            "applied": not stale,
        })
    return results