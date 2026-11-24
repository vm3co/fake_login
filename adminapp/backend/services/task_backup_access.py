from fastapi import HTTPException
from sqlalchemy import select

from backend.repository.models import TaskBackup


def backup_scope(current_user):
    if current_user.get("user_type") == "customer":
        raise HTTPException(status_code=403, detail="Backup access is not available to customers")
    if current_user.get("admin_role") is True:
        return None
    orgs = current_user.get("orgs")
    if current_user.get("user_type") != "user" or not isinstance(orgs, list) or not orgs or any(
        not isinstance(org, str) or not org for org in orgs
    ):
        raise HTTPException(status_code=403, detail="A trusted organization scope is required")
    return tuple(orgs)


def scoped_backups(scope):
    statement = select(TaskBackup)
    if scope is not None:
        statement = statement.where(TaskBackup.owner_gids.overlap(list(scope)))
    return statement


async def require_backup_access(session, backup_id, scope, *, lock=False):
    statement = scoped_backups(scope).where(TaskBackup.backup_id == backup_id)
    if lock:
        statement = statement.with_for_update()
    backup = await session.scalar(statement)
    if backup is None:
        raise HTTPException(status_code=404, detail="Backup not found")
    return backup