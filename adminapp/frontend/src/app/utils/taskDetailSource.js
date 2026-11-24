export function detailSource(task) {
  if (task?.source === 'backup') {
    if (!task.backup_id) throw new Error('缺少備援識別');
    return { backup: true, key: `backup:${task.backup_id}`, base: `/api/task_backups/${encodeURIComponent(task.backup_id)}` };
  }
  if (!task?.sendtask_uuid || !task.local_generation_id) throw new Error('缺少現行任務版本識別');
  return { backup: false, key: `current:${task.sendtask_uuid}:${task.local_generation_id}` };
}

export function detailRequest(source, task, page, filters) {
  const acctControl = source.backup ? [true, true, true, true, true] :
    [!!task.send, !!task.failed, !!task.notyet, !!task.notTriggered, !!task.triggered];
  const body = { page: page + 1, acctControl, ...filters };
  if (source.backup) {
    body.dateFrom ||= null;
    body.dateTo ||= null;
    return { url: `${source.base}/details`, body };
  }
  return { url: '/api/get_sendlog_detail', body: { ...body, sendtask_uuid: task.sendtask_uuid } };
}

export function backupHeader(response, backupId) {
  const data = response?.data;
  if (response?.status !== 'success' || data?.backup_id !== backupId ||
      !data.task_snapshot || !Object.hasOwn(data, 'stats_snapshot') ||
      !data.mail_template_snapshot || typeof data.mail_template_snapshot !== 'object') {
    throw new Error('備援快照格式不完整');
  }
  return { ...data, templates: Object.values(data.mail_template_snapshot).filter(Boolean) };
}

export function detailRows(response, backup = false) {
  if (response?.status !== 'success' || !Array.isArray(response.data) ||
      !Number.isInteger(response.total_count) || response.total_count < 0) throw new Error('明細資料格式不完整');
  return { rows: response.data.map(row => {
    if (backup && (!row.display || typeof row.display !== 'object')) throw new Error('備援事件投影缺失');
    return backup ? { ...row, ...row.display } : row;
  }), total: response.total_count };
}