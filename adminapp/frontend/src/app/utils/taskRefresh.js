export function validatedRows(response) {
  if (response?.status !== 'success' || !Array.isArray(response.data) || response.data.some(row => (
    !row || typeof row.sendtask_uuid !== 'string' || !row.sendtask_uuid
  ))) throw new Error('任務資料回應格式錯誤');
  if (new Set(response.data.map(row => row.sendtask_uuid)).size !== response.data.length) {
    throw new Error('任務資料包含重複識別');
  }
  return response.data;
}

export function mergeTaskSnapshot(currentTasks, currentStats, tasksResponse, statsResponse, requested = null) {
  const tasks = validatedRows(tasksResponse);
  const stats = validatedRows(statsResponse);
  const taskIds = new Set(tasks.map(row => row.sendtask_uuid));
  const scope = requested === null ? null : new Set(requested);
  if (tasks.some(row => scope && !scope.has(row.sendtask_uuid)) || stats.some(row => (
    !taskIds.has(row.sendtask_uuid) || (scope && !scope.has(row.sendtask_uuid))
  )) || tasks.length !== stats.length) throw new Error('任務與統計資料不一致，請重試');
  const statsMap = Object.fromEntries(stats.map(row => [row.sendtask_uuid, row]));
  if (scope === null) return { tasks, stats: statsMap };
  return {
    tasks: [...currentTasks.filter(row => !scope.has(row.sendtask_uuid)), ...tasks],
    stats: { ...Object.fromEntries(Object.entries(currentStats).filter(([uuid]) => !scope.has(uuid))), ...statsMap },
  };
}

export function assertStableTasks(before, after) {
  const signature = response => validatedRows(response).map(row => (
    `${row.sendtask_uuid}:${row.local_generation_id || ''}:${row.sync_revision ?? ''}`
  )).sort();
  if (JSON.stringify(signature(before)) !== JSON.stringify(signature(after))) {
    throw new Error('任務版本在讀取期間變更，請重試');
  }
}

export function jobInvalidation(job) {
  const result = job.result || {};
  const outcomes = result.sync_results || {};
  const uuids = [...new Set((result.changed_uuids || []).filter(uuid => typeof uuid === 'string'))];
  const versions = Object.fromEntries(Object.entries(outcomes).filter(([, value]) => value?.committed).map(([uuid, value]) => (
    [uuid, { generation: value.generation, revision: value.revision, status: value.status }]
  )));
  return { uuids, versions, reloadList: result.reload_list === true, backupsChanged: result.backups_changed === true,
    backupIds: result.changed_backup_ids || [] };
}

export function invalidationSignature(job) {
  return JSON.stringify(jobInvalidation(job));
}

export function pollInvalidations(jobs, previous, initialized) {
  return jobs.filter(job => initialized && previous.get(job.job_id) !== invalidationSignature(job))
    .map(jobInvalidation);
}

export function combineInvalidations(events) {
  return events.reduce((combined, event) => ({
    uuids: [...new Set([...combined.uuids, ...(event.uuids || [])])],
    versions: { ...combined.versions, ...event.versions },
    reloadList: combined.reloadList || event.reloadList === true,
    backupsChanged: combined.backupsChanged || event.backupsChanged === true,
    backupIds: [...new Set([...combined.backupIds, ...(event.backupIds || [])])],
  }), { uuids: [], versions: {}, reloadList: false, backupsChanged: false, backupIds: [] });
}