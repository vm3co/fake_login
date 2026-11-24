import { useEffect, useRef, useState } from 'react';
import { useSnackbar } from 'notistack';

export default function useTaskDetailInvalidation(dialog, setDialog, tasks) {
  const { enqueueSnackbar } = useSnackbar();
  const [revision, setRevision] = useState(0);
  const current = useRef({ dialog, tasks });
  current.current = { dialog, tasks };
  useEffect(() => {
    const invalidate = event => {
      const { dialog: opened } = current.current;
      if (!opened.open || !opened.task) return;
      const uuid = opened.task.sendtask_uuid;
      if (!(event.detail?.uuids || []).includes(uuid)) return;
      const version = event.detail?.versions?.[uuid];
      if (!version || ['recreated', 'reloaded', 'backed_up'].includes(version.status)
          || (opened.task.local_generation_id && version.generation !== opened.task.local_generation_id)) {
        setDialog({ open: false, task: null });
        enqueueSnackbar('任務版本已變更，請重新開啟明細', { variant: 'warning' });
      } else setRevision(value => value + 1);
    };
    window.addEventListener('taskDataInvalidated', invalidate);
    return () => window.removeEventListener('taskDataInvalidated', invalidate);
  }, [enqueueSnackbar, setDialog]);
  useEffect(() => {
    if (!dialog.open || !dialog.task) return;
    const task = tasks.find(row => row.sendtask_uuid === dialog.task.sendtask_uuid);
    if (!task || (dialog.task.local_generation_id && task.local_generation_id !== dialog.task.local_generation_id)) {
      setDialog({ open: false, task: null });
      enqueueSnackbar('任務已移出或版本已變更，請重新開啟明細', { variant: 'warning' });
    } else if (task.sync_revision !== dialog.task.sync_revision) {
      setDialog({ ...dialog, task: { ...dialog.task, ...task, name: task.sendtask_id } });
      setRevision(value => value + 1);
    }
  }, [tasks, dialog, enqueueSnackbar, setDialog]);
  return revision;
}