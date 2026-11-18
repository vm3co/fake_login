export function validateBackupList(response) {
  if (response?.status !== 'success' || !Array.isArray(response.data)
      || !Number.isInteger(response.total_count) || response.total_count < 0
      || response.data.some(row => !row || typeof row.backup_id !== 'string' || !row.backup_id)
      || new Set(response.data.map(row => row.backup_id)).size !== response.data.length) {
    throw new Error('備援列表回應格式錯誤');
  }
  return response;
}

export function selectBackupPage(selected, rows, checked) {
  const next = { ...selected };
  rows.forEach(row => {
    if (checked) next[row.backup_id] = row;
    else delete next[row.backup_id];
  });
  return next;
}

export function backupPage(page, total, size) {
  return Math.min(page, Math.max(0, Math.ceil(total / size) - 1));
}

export function backupCheckParams(selected) {
  const backupIds = Object.keys(selected);
  if (!backupIds.length) throw new Error('請先選取備援');
  return { backup_ids: backupIds };
}

export function backupTime(value, seconds = false) {
  if (value === null || value === undefined || value === '') return '未知';
  const date = new Date(seconds ? Number(value) * 1000 : value);
  return Number.isNaN(date.getTime()) ? '未知' : new Intl.DateTimeFormat('zh-TW', {
    timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(date);
}