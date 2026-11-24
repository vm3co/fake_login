from copy import deepcopy
from datetime import datetime, timedelta
import re

from sqlalchemy import asc, desc, false, func, or_, select


EVENT_BASES = ("access", "click", "file", "second_access", "second_qrcode", "second_input")
EVENT_COLUMNS = tuple(f"{base}_{suffix}" for base in EVENT_BASES for suffix in ("time", "src", "dev")) + ("second_input_info",)
TRIGGER_COUNT_FIELDS = [
    (f"{base}_time", f"{base}_count", "second_input_info" if base == "second_input" else f"{base}_dev")
    for base in EVENT_BASES
]


def count_trigger_times(row):
    return {count: sum(bool(value) for value in row.get(field) or []) if isinstance(row.get(field), list)
            else int(bool(row.get(field))) for field, count, _ in TRIGGER_COUNT_FIELDS}


def sendlog_query(model, source_condition, request, *, timezone=None):
    statement = select(model).where(source_condition)
    if request.searchText:
        pattern = f"%{request.searchText}%"
        statement = statement.where(or_(model.target_email.ilike(pattern), model.person_info.ilike(pattern)))
    for field, end in (("dateFrom", False), ("dateTo", True)):
        value = getattr(request, field)
        if value:
            try:
                boundary = datetime.strptime(value, "%Y-%m-%d")
                if timezone is not None:
                    boundary = boundary.replace(tzinfo=timezone)
                if end:
                    boundary += timedelta(days=1)
                timestamp = int(boundary.timestamp())
                condition = model.send_time < timestamp if end else model.send_time >= timestamp
                statement = statement.where(condition)
            except ValueError:
                if timezone is not None:
                    raise
    sent = model.send_time.isnot(None) & (model.send_time > 0)
    success = model.send_res.ilike("%True%")
    failure = model.send_res.ilike("%False%")
    pending = model.send_time.is_(None) | (model.send_time == 0)
    lengths = [func.array_length(getattr(model, field), 1) for field in ("access_time", "access_src", "access_dev")]
    triggered = or_(*(length > 0 for length in lengths))
    not_triggered = (lengths[0].is_(None) | (lengths[0] <= 0)) & (lengths[1].is_(None) | (lengths[1] <= 0)) & (lengths[2].is_(None) | (lengths[2] <= 0))
    is_send, is_failed, is_pending, is_not_triggered, is_triggered = request.acctControl
    if request.resultType == "all":
        if not any(request.acctControl):
            statement = statement.where(false())
        elif not all(request.acctControl):
            conditions = []
            if is_failed:
                conditions.append(sent & failure)
            if is_pending:
                conditions.append(pending)
            if is_send:
                conditions.append(sent & success & not_triggered if is_not_triggered and not is_triggered
                                  else triggered if is_triggered and not is_not_triggered else sent & success)
            if conditions:
                statement = statement.where(or_(*conditions))
    else:
        conditions = {"send": sent & success, "failed": sent & failure, "notyet": pending,
                      "notTriggered": sent & success & not_triggered, "triggered": triggered}
        if request.resultType in conditions:
            statement = statement.where(conditions[request.resultType])
    for flag, column in (("showAccessed", "access_time"), ("showClicked", "click_time"), ("showFiled", "file_time")):
        if getattr(request, flag):
            statement = statement.where(func.array_length(getattr(model, column), 1) > 0)
    column = getattr(model, request.sortBy, model.plan_time)
    direction = asc if request.sort == "asc" else desc
    statement = statement.order_by(direction(column), direction(model.id))
    count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
    if request.paginate:
        statement = statement.offset((request.page - 1) * request.rowsPerPage).limit(request.rowsPerPage)
    return statement, count_statement


def project_events(record, filter_ip=None):
    item = deepcopy(record)
    patterns = []
    for address in (filter_ip or "").split(","):
        address = address.strip()
        if address and re.fullmatch(r"[0-9a-fA-F.:*]+", address):
            patterns.append(re.compile("^" + re.escape(address).replace(r"\*", ".*") + "$"))
    if patterns:
        for base in EVENT_BASES:
            source = item.get(f"{base}_src")
            if isinstance(source, list) and source:
                keep = [index for index, address in enumerate(source)
                        if not address or not any(pattern.fullmatch(str(address)) for pattern in patterns)]
                for field in EVENT_COLUMNS:
                    if field.startswith(base + "_") and isinstance(item.get(field), list):
                        item[field] = [item[field][index] for index in keep if index < len(item[field])] or None
    item.update(count_trigger_times(item))
    for field in EVENT_COLUMNS:
        if isinstance(item.get(field), list):
            item[field] = item[field][-1] if item[field] else None
    return item