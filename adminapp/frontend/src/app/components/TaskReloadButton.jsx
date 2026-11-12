import { useState } from 'react';
import { Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle, IconButton, List, ListItem, Tooltip } from '@mui/material';
import RestorePageIcon from '@mui/icons-material/RestorePage';
import { useJob } from 'app/contexts/JobContext';

export default function TaskReloadButton({ tasks, disabled = false, compact = false }) {
  const { startJob } = useJob();
  const [targets, setTargets] = useState(null);
  const [sending, setSending] = useState(false);
  const open = () => setTargets([...new Map(tasks.map(task => [task.sendtask_uuid, task])).values()]);
  const submit = async () => {
    setSending(true);
    const result = await startJob('force_reload_sendtask', {
      uuids: targets.map(task => task.sendtask_uuid), confirm_reload: true,
    });
    setSending(false);
    if (result) setTargets(null);
  };
  return <>
    {compact ? <Tooltip title="備援後重新匯入"><span><IconButton aria-label="備援後重新匯入" size="small" color="warning"
      disabled={disabled || !tasks.length} onClick={open}><RestorePageIcon /></IconButton></span></Tooltip>
      : <Button startIcon={<RestorePageIcon />} color="warning" size="small" disabled={disabled || !tasks.length}
        onClick={open}>備援後重新匯入（{tasks.length}）</Button>}
    <Dialog open={targets !== null} onClose={() => { if (!sending) setTargets(null); }} fullWidth maxWidth="sm"
      PaperProps={{ sx: { backgroundColor: '#fff', backgroundImage: 'none' } }}>
      <DialogTitle>備援後重新匯入 {targets?.length || 0} 個任務</DialogTitle>
      <DialogContent>
        <DialogContentText>舊任務與本地觸發紀錄將完整移入備援，現行資料改由主系統重新匯入，本地觸發重新開始。備援不再追加事件。若明細 ID 相同，舊連結仍可能觸發現行版本。</DialogContentText>
        <List dense sx={{ maxHeight: 240, overflow: 'auto', overflowWrap: 'anywhere' }}>
          {targets?.map(task => <ListItem key={task.sendtask_uuid}>{task.sendtask_id || task.sendtask_uuid}</ListItem>)}
        </List>
      </DialogContent>
      <DialogActions><Button disabled={sending} onClick={() => setTargets(null)}>取消</Button>
        <Button disabled={sending} color="warning" variant="contained" onClick={submit}>確認備援並重新匯入</Button></DialogActions>
    </Dialog>
  </>;
}