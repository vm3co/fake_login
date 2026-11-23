import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Alert, Box, Button, Checkbox, Chip, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogContentText, DialogTitle, IconButton, MenuItem, Stack, Table, TableBody, TableCell,
  TableContainer, TableHead, TablePagination, TableRow, TextField, Tooltip, Typography } from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import DownloadIcon from '@mui/icons-material/Download';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import FactCheckIcon from '@mui/icons-material/FactCheck';
import ClearIcon from '@mui/icons-material/Clear';
import VisibilityIcon from '@mui/icons-material/Visibility';
import { useSnackbar } from 'notistack';
import { useJob } from 'app/contexts/JobContext';
import { backupCheckParams, backupPage, backupTime, selectBackupPage, validateBackupList } from 'app/utils/backupList';

const REASONS = { remote_missing: '來源不存在', remote_recreated: '來源重建', manual_reload: '人工重新匯入' };
const REMOTE = { unchecked: '未檢查', present: '來源存在', missing: '來源不存在', error: '查詢異常' };
const FILTERS = [['', '全部'], ['recreated', '已重建'], ['unproven', '尚未證實'], ['unchecked', '未檢查'], ['error', '查詢異常']];

export default function ShowBackupTasks({ onOpenBackup }) {
  const { startJob, manualJobs } = useJob();
  const { enqueueSnackbar } = useSnackbar();
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [size, setSize] = useState(20);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [observation, setObservation] = useState('');
  const [order, setOrder] = useState('backed_up_at:desc');
  const [selected, setSelected] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [confirm, setConfirm] = useState(null);
  const [busy, setBusy] = useState(false);
  const [downloads, setDownloads] = useState({});
  const sequence = useRef(0);
  const activeChecks = manualJobs.filter(job => job.job_code === 'check_backup_recreated'
    && ['queued', 'claiming', 'running', 'cancel_requested'].includes(job.status));
  const selectedRows = Object.values(selected);
  const actionableRows = rows.filter(row => row.actions?.read);
  const pageSelected = actionableRows.filter(row => selected[row.backup_id]).length;

  useEffect(() => {
    if (search.trim() === query) return undefined;
    const timer = window.setTimeout(() => {
      setQuery(search.trim());
      setPage(0);
      setSelected({});
    }, 350);
    return () => window.clearTimeout(timer);
  }, [search, query]);

  useEffect(() => {
    const controller = new AbortController();
    const request = ++sequence.current;
    setLoading(true);
    const [sortBy, sort] = order.split(':');
    axios.get('/api/task_backups', { signal: controller.signal, params: {
      page: page + 1, page_size: size, search: query || undefined, observation: observation || undefined,
      sort_by: sortBy, sort,
    } }).then(({ data }) => {
      const result = validateBackupList(data);
      if (request !== sequence.current) return;
      const nextPage = backupPage(page, result.total_count, size);
      if (nextPage !== page) { setPage(nextPage); return; }
      setRows(result.data);
      setTotal(result.total_count);
      setError('');
      setSelected(current => {
        const next = { ...current };
        result.data.forEach(row => { if (next[row.backup_id]) next[row.backup_id] = row; });
        return next;
      });
    }).catch(failure => {
      if (!axios.isCancel(failure) && request === sequence.current) {
        setError(failure.response?.status === 403 ? '無權查閱備援任務' : `備援載入失敗：${failure.message}`);
        if (failure.response?.status === 403 || failure.response?.status === 401) {
          setRows([]); setSelected({}); setTotal(0);
        }
      }
    }).finally(() => { if (request === sequence.current) setLoading(false); });
    return () => { controller.abort(); sequence.current += 1; };
  }, [page, size, query, observation, order, refresh]);

  useEffect(() => {
    let timer;
    const reload = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => setRefresh(value => value + 1), 250);
    };
    const visibility = () => { if (!document.hidden) reload(); };
    window.addEventListener('taskBackupsInvalidated', reload);
    window.addEventListener('focus', reload);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('taskBackupsInvalidated', reload);
      window.removeEventListener('focus', reload);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, []);

  const download = async row => {
    setDownloads(current => ({ ...current, [row.backup_id]: true }));
    try {
      const response = await axios.get(`/api/task_backups/${encodeURIComponent(row.backup_id)}/export.xlsx`, { responseType: 'blob' });
      const url = URL.createObjectURL(response.data);
      const link = document.createElement('a');
      link.href = url;
      link.download = `task-backup-${row.backup_id}.xlsx`;
      document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
    } catch (failure) {
      enqueueSnackbar(`備援下載失敗：${failure.message}`, { variant: 'error' });
    } finally {
      setDownloads(current => ({ ...current, [row.backup_id]: false }));
    }
  };

  const submit = async () => {
    setBusy(true);
    try {
      if (confirm.type === 'check') {
        const targets = Object.fromEntries(confirm.rows.map(row => [row.backup_id, row]));
        const result = await startJob('check_backup_recreated', backupCheckParams(targets));
        if (result) setConfirm(null);
      } else {
        const row = confirm.rows[0];
        const { data } = await axios.delete(`/api/task_backups/${encodeURIComponent(row.backup_id)}`, { params: { confirm_delete: 'true' } });
        if (data.status !== 'success' || data.deleted_backup_id !== row.backup_id) throw new Error('刪除回應格式錯誤');
        setRows(current => current.filter(item => item.backup_id !== row.backup_id));
        setSelected(current => { const next = { ...current }; delete next[row.backup_id]; return next; });
        setConfirm(null);
        window.dispatchEvent(new CustomEvent('taskBackupsInvalidated', { detail: { backupsChanged: true, backupIds: [row.backup_id] } }));
        enqueueSnackbar('已永久刪除此份備援', { variant: 'success' });
      }
    } catch (failure) {
      enqueueSnackbar(`備援操作失敗：${failure.response?.data?.detail || failure.message}`, { variant: 'error' });
    } finally { setBusy(false); }
  };

  return <Box aria-label="備援任務列表" sx={{ minWidth: 0 }}>
    <Stack direction="row" useFlexGap flexWrap="wrap" spacing={1} sx={{ mb: 2, alignItems: 'center' }}>
      <TextField label="搜尋任務名稱或來源 UUID" value={search} onChange={event => setSearch(event.target.value)} size="small" sx={{ width: { xs: '100%', sm: 300 } }} />
      <TextField select label="觀測狀態" size="small" value={observation} sx={{ minWidth: 140 }} onChange={event => {
        setObservation(event.target.value); setPage(0); setSelected({});
      }}>{FILTERS.map(([value, label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}</TextField>
      <TextField select label="排序" size="small" value={order} sx={{ minWidth: 170 }} onChange={event => { setOrder(event.target.value); setPage(0); }}>
        <MenuItem value="backed_up_at:desc">備援時間：新到舊</MenuItem><MenuItem value="backed_up_at:asc">備援時間：舊到新</MenuItem>
        <MenuItem value="source_create_ut:desc">原版本建立：新到舊</MenuItem><MenuItem value="sendtask_id:asc">任務名稱</MenuItem>
      </TextField>
      <Tooltip title="重新整理"><span><IconButton aria-label="重新整理備援" disabled={loading} onClick={() => setRefresh(value => value + 1)}><RefreshIcon /></IconButton></span></Tooltip>
    </Stack>
    <Stack direction="row" useFlexGap flexWrap="wrap" spacing={1} sx={{ mb: 1, alignItems: 'center' }}>
      <Typography variant="body2">已選 {selectedRows.length} 份歷史版本</Typography>
      <Button size="small" startIcon={<FactCheckIcon />} disabled={!selectedRows.length || loading || Boolean(error) || busy || activeChecks.length > 0}
        onClick={() => setConfirm({ type: 'check', rows: selectedRows })}>檢查是否重建</Button>
      <Tooltip title="清除選取"><span><IconButton aria-label="清除備援選取" size="small" disabled={!selectedRows.length} onClick={() => setSelected({})}><ClearIcon /></IconButton></span></Tooltip>
      {activeChecks.length > 0 && <Chip size="small" label="備援檢查進行中" />}
      {loading && <CircularProgress size={20} aria-label="載入備援" />}
    </Stack>
    {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
    <TableContainer sx={{ overflowX: 'auto', width: '100%' }}>
      <Table size="small" sx={{ minWidth: 1380, tableLayout: 'fixed',
        '& th, & td': { textAlign: 'center', verticalAlign: 'middle', lineHeight: 1.4, px: 1.5, py: 1.5,
          borderRight: '1px solid #e0e0e0', overflowWrap: 'anywhere' },
        '& th:last-child, & td:last-child': { borderRight: 'none' },
        '& th': { backgroundColor: '#f1f1f1', fontWeight: 600 },
        '& tbody tr:nth-of-type(even)': { backgroundColor: 'rgba(25, 118, 210, 0.14)' },
        '& tbody tr:hover': { backgroundColor: 'rgba(0, 0, 0, 0.08)' },
        '& th:first-of-type, & td:first-of-type': { width: 60, minWidth: 60, px: 0 },
        '& .MuiCheckbox-root': { padding: '9px' }
      }}>
        <colgroup>{[60, 220, 270, 150, 150, 110, 80, 220, 160].map((width, index) => <col key={index} style={{ width }} />)}</colgroup>
        <TableHead><TableRow>
          <TableCell padding="checkbox"><Checkbox inputProps={{ 'aria-label': '選取本頁備援' }} disabled={loading || !actionableRows.length}
            checked={actionableRows.length > 0 && pageSelected === actionableRows.length} indeterminate={pageSelected > 0 && pageSelected < actionableRows.length}
            onChange={event => setSelected(current => selectBackupPage(current, actionableRows, event.target.checked))} /></TableCell>
          {['任務／歷史版本', '原始 UUID', '原版本建立時間', '保存時間', '保存原因', '明細數', '重建證據／最近觀測', '操作'].map(label => <TableCell key={label}>{label}</TableCell>)}
        </TableRow></TableHead>
        <TableBody>{rows.map(row => <TableRow key={row.backup_id} selected={Boolean(selected[row.backup_id])}>
          <TableCell padding="checkbox"><Checkbox inputProps={{ 'aria-label': `選取備援 ${row.backup_id}` }} checked={Boolean(selected[row.backup_id])}
            disabled={loading || !row.actions?.read} onChange={event => setSelected(current => selectBackupPage(current, [row], event.target.checked))} /></TableCell>
          <TableCell sx={{ maxWidth: 230, overflowWrap: 'anywhere' }}><Typography variant="body2">{row.sendtask_id}</Typography>
            <Tooltip title={row.backup_id}><Typography variant="caption">版本 {row.backup_id.slice(0, 8)}</Typography></Tooltip></TableCell>
          <TableCell sx={{ whiteSpace: 'nowrap', overflowWrap: 'normal' }}>{row.source_task_uuid}</TableCell>
          <TableCell sx={{ whiteSpace: 'nowrap' }}>{backupTime(row.source_create_ut, true)}</TableCell>
          <TableCell sx={{ whiteSpace: 'nowrap' }}>{backupTime(row.backed_up_at)}</TableCell>
          <TableCell>{REASONS[row.reason] || row.reason}</TableCell><TableCell>{row.detail_count}</TableCell>
          <TableCell><Stack spacing={0.5} alignItems="center">
            <Chip size="small" color={row.recreated_detected_at ? 'success' : 'default'} label={row.recreated_detected_at ? '曾證實重建' : '尚未證實'} />
            <Typography variant="caption" color={row.latest_remote_status === 'error' ? 'error' : 'text.secondary'}>{REMOTE[row.latest_remote_status] || row.latest_remote_status}</Typography>
            <Typography variant="caption">{row.last_remote_checked_at ? backupTime(row.last_remote_checked_at) : '尚無檢查時間'}</Typography>
          </Stack></TableCell>
          <TableCell><Stack direction="row" spacing={0.5} justifyContent="center">
            {onOpenBackup && row.actions?.read && <Tooltip title="唯讀備援明細"><IconButton aria-label={`備援明細 ${row.backup_id}`} onClick={() => onOpenBackup({ ...row, source: 'backup', readOnly: true })}><VisibilityIcon /></IconButton></Tooltip>}
            <Tooltip title="匯出整份備援 Excel"><span><IconButton aria-label={`匯出備援 ${row.backup_id}`} disabled={loading || Boolean(error) || !row.actions?.export || downloads[row.backup_id]} onClick={() => download(row)}><DownloadIcon /></IconButton></span></Tooltip>
            <Tooltip title="永久刪除此份備援"><span><IconButton color="error" aria-label={`刪除備援 ${row.backup_id}`} disabled={loading || Boolean(error) || !row.actions?.delete || busy}
              onClick={() => setConfirm({ type: 'delete', rows: [row] })}><DeleteOutlineIcon /></IconButton></span></Tooltip>
          </Stack></TableCell>
        </TableRow>)}
          {!rows.length && <TableRow><TableCell colSpan={9} align="center">{loading ? '載入中' : error ? '備援資料目前無法載入' : '沒有符合條件的備援任務'}</TableCell></TableRow>}
        </TableBody>
      </Table>
    </TableContainer>
    <TablePagination component="div" count={total} page={page} rowsPerPage={size} rowsPerPageOptions={[10, 20, 50, 100]}
      labelRowsPerPage="每頁份數" onPageChange={(_, value) => setPage(value)} onRowsPerPageChange={event => { setSize(Number(event.target.value)); setPage(0); }}
      sx={{ '& .MuiTablePagination-toolbar': { flexWrap: 'wrap', justifyContent: 'flex-end', px: 0 } }} />
    <Dialog open={Boolean(confirm)} onClose={() => { if (!busy) setConfirm(null); }} transitionDuration={0} maxWidth="sm" fullWidth
      PaperProps={{ sx: { backgroundColor: '#fff', backgroundImage: 'none', opacity: 1 } }}>
      <DialogTitle>{confirm?.type === 'check' ? `檢查 ${confirm.rows.length} 份備援的來源` : '永久刪除此份備援'}</DialogTitle>
      <DialogContent>
        <DialogContentText>{confirm?.type === 'check'
          ? `將檢查 ${new Set(confirm.rows.map(row => row.source_task_uuid)).size} 個來源任務，只更新重建觀測，不匯入或刪除任務。`
          : '此操作無法復原。只刪除此份歷史備援與明細，現行任務與其他備援版本不受影響。'}</DialogContentText>
        <Box sx={{ maxHeight: 240, overflow: 'auto', overflowWrap: 'anywhere', mt: 2 }}>
          {confirm?.rows.map(row => <Box key={row.backup_id} sx={{ mb: 1 }}><Typography>{row.sendtask_id}</Typography>
            <Typography variant="caption" component="div">{row.backup_id}</Typography>
            <Typography variant="caption">原版本：{backupTime(row.source_create_ut, true)}；備援：{backupTime(row.backed_up_at)}</Typography></Box>)}
        </Box>
      </DialogContent>
      <DialogActions><Button disabled={busy} onClick={() => setConfirm(null)}>取消</Button>
        <Button disabled={busy} color={confirm?.type === 'delete' ? 'error' : 'primary'} variant="contained" onClick={submit}>
          {confirm?.type === 'check' ? '確認檢查所選備援' : '確認永久刪除'}</Button></DialogActions>
    </Dialog>
  </Box>;
}