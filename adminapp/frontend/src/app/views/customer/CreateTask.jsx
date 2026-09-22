import { useState, useEffect } from 'react';
import axios from 'axios';
import { useSnackbar } from 'notistack';
import {
  Box,
  Grid,
  Typography,
  Button,
  FormControlLabel,
  RadioGroup,
  Radio,
  Checkbox,
  CircularProgress,
  Alert,
  Link,
  Dialog,
  DialogTitle,
  DialogContent,
  IconButton,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
  TableContainer,
  Paper,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import { MobileDateTimePicker, LocalizationProvider } from '@mui/x-date-pickers';
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFnsV3';
import {
  UploadFile,
  Download,
  Send,
} from '@mui/icons-material';

/**
 * 建立新任務表單
 * 欄位：任務名稱、任務類型、開始/結束時間、停止寄送日期、演練參與人員（CSV）、郵件樣本
 *
 * Props:
 *   - onSuccess: 建立成功 callback
 *   - readOnly: 是否唯讀模式（不可編輯、不顯示送出按鈕）
 *   - initialData: 唯讀模式下用以顯示的資料
 *       { task_name, task_type, start_date, end_date, stop_date, person_count,
 *         template_uuids: string[], unit_uuid: string }
 */

// "YYYY-MM-DDTHH:mm" 字串 → Date 物件（或 null）
const parseInputDate = (str) => {
  if (!str) return null;
  const d = new Date(str);
  return isNaN(d.getTime()) ? null : d;
};

// Date 物件 → "YYYY-MM-DDTHH:mm" 字串（後端接受的格式）
const toInputDateTime = (d) => {
  if (!d) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

export default function CreateTask({ onSuccess, readOnly = false, initialData = null, allowedEmailDomains = [], maxTaskCount = null, currentTaskCount = 0 }) {
  const { enqueueSnackbar } = useSnackbar();

  // 任務數量上限（maxTaskCount 為 null/0 代表不限制）
  const hasLimit = !readOnly && maxTaskCount != null && maxTaskCount > 0;
  const remainingTasks = hasLimit ? Math.max(maxTaskCount - currentTaskCount, 0) : null;
  const atLimit = hasLimit && currentTaskCount >= maxTaskCount;

  // 表單狀態（以 Date 物件儲存時間，方便給 DateTimePicker）
  const [taskName, setTaskName] = useState(initialData?.task_name || '');
  const [taskType, setTaskType] = useState(initialData?.task_type || 'pre');
  const [startDate, setStartDate] = useState(parseInputDate(initialData?.start_date));
  const [endDate, setEndDate] = useState(parseInputDate(initialData?.end_date));
  const [stopDate, setStopDate] = useState(parseInputDate(initialData?.stop_date));
  const [participantFile, setParticipantFile] = useState(null);
  const [selectedTemplates, setSelectedTemplates] = useState(initialData?.template_uuids || []);

  // 郵件樣本清單：{ mtmpl_uuid, mtmpl_name }[]
  const [mailTemplates, setMailTemplates] = useState([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);

  // 送出狀態
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  // 清冊 Dialog
  const [participantDialogOpen, setParticipantDialogOpen] = useState(false);

  // 從 Cookie 取得指定值
  const getCookie = (name) => {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return decodeURIComponent(parts.pop().split(';').shift());
    return null;
  };

  // 載入郵件樣本
  // - 一般模式：用 cookie 裡的 org_uuid
  // - 唯讀模式：用 initialData.unit_uuid（後端回傳的）
  useEffect(() => {
    const fetchTemplates = async () => {
      setLoadingTemplates(true);
      try {
        const orgUuid = readOnly
          ? (initialData?.unit_uuid || '')
          : (getCookie('task_creation_org_uuid') || '');

        if (!orgUuid) {
          setLoadingTemplates(false);
          return;
        }

        const res = await axios.get(`/api/get_mtmpl_name_list?unit_uuid=${orgUuid}`);
        if (res.data && Array.isArray(res.data.data)) {
          setMailTemplates(res.data.data);
        } else {
          setMailTemplates([]);
        }
      } catch (err) {
        console.error('無法載入郵件樣本：', err);
      } finally {
        setLoadingTemplates(false);
      }
    };
    fetchTemplates();
  }, [readOnly, initialData?.unit_uuid]);

  // 切換郵件樣本勾選
  const handleTemplateToggle = (uuid) => {
    setSelectedTemplates((prev) =>
      prev.includes(uuid) ? prev.filter((u) => u !== uuid) : [...prev, uuid]
    );
  };

  // 處理檔案上傳選擇
  const handleFileChange = (e) => {
    const file = e.target.files?.[0] || null;
    setParticipantFile(file);
  };

  // 下載範例檔（CSV）
  const handleDownloadTemplate = () => {
    const csvContent = 'UnitName,SubUnitName(Optional),UserName,UserEMail,Order(Optional)\nAB Company,,John,johm@abc.com,\n';
    const blob = new Blob(['﻿' + csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = '演練參與人員範例.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  // 驗證表單
  const validate = () => {
    if (atLimit) return `已達到任務建立上限（${maxTaskCount}），無法再建立新任務`;
    if (!taskName.trim()) return '請輸入任務名稱';
    if (!startDate) return '請選擇開始時間';
    if (!endDate) return '請選擇結束時間';
    if (startDate > endDate) return '結束時間不能早於開始時間';
    if (!participantFile) return '請選擇演練參與人員檔案';
    if (selectedTemplates.length === 0) return '請至少選擇一個郵件樣本';
    return null;
  };

  // 送出表單
  const handleSubmit = async () => {
    setError(null);
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }

    try {
      setSubmitting(true);

      let participantData = '';
      if (participantFile) {
        participantData = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = (e) => resolve(e.target.result);
          reader.onerror = (e) => reject(e);
          reader.readAsText(participantFile);
        });

        // 驗證 Email Domain
        if (allowedEmailDomains && allowedEmailDomains.length > 0) {
          const lines = participantData.split(/\r?\n/).filter(l => l.trim());
          if (lines.length > 1) {
            const header = lines[0].split(',');
            let emailIndex = header.findIndex(col => col.trim().toLowerCase() === 'useremail');
            if (emailIndex === -1) emailIndex = 3; // 預設第 4 欄

            for (let i = 1; i < lines.length; i++) {
              const cols = lines[i].split(',');
              if (cols.length > emailIndex) {
                const email = cols[emailIndex]?.trim() || '';
                if (email && email.includes('@')) {
                  const domain = email.split('@')[1].toLowerCase();
                  const isValid = allowedEmailDomains.some(d => d.toLowerCase() === domain);
                  if (!isValid) {
                    setError(`Email ${email} 不符合 domain 限制。允許的 domain: ${allowedEmailDomains.join(', ')}`);
                    setSubmitting(false);
                    return;
                  }
                }
              }
            }
          }
        }
      }

      const orgUuid = getCookie('task_creation_org_uuid');
      const customerUuid = getCookie('customer_uuid');

      const payload = {
        task_name: taskName.trim(),
        task_type: taskType,
        start_date: toInputDateTime(startDate),
        end_date: toInputDateTime(endDate),
        stop_date: stopDate ? toInputDateTime(stopDate) : null,
        participant_data: participantData,
        template_uuids: selectedTemplates,
        unit_uuid: orgUuid || '',
        customer_uuid: customerUuid || ''
      };

      const res = await axios.post('/api/task/create_testcase', payload, {
        headers: { 'Content-Type': 'application/json' },
      });

      if (res.data.status === 'success') {
        enqueueSnackbar('專案建立成功！', { variant: 'success' });
        setTaskName('');
        setTaskType('pre');
        setStartDate(null);
        setEndDate(null);
        setStopDate(null);
        setParticipantFile(null);
        setSelectedTemplates([]);
        if (onSuccess) onSuccess(res.data.sendtask_uuid);
      } else {
        setError(res.data.message || '建立任務失敗');
      }
    } catch (err) {
      let errorMsg = '建立任務時發生錯誤';
      const detail = err.response?.data?.detail;
      if (detail) {
        errorMsg = typeof detail === 'string' ? detail : JSON.stringify(detail);
      } else if (err.message) {
        errorMsg = err.message;
      }
      setError(errorMsg);
    } finally {
      setSubmitting(false);
    }
  };

  // ──────────────────────────────────────────────
  const ROW_SX = {
    display: 'flex',
    alignItems: 'flex-start',
    py: 2,
    borderBottom: '1px solid #e0e0e0',
  };

  const LABEL_SX = {
    minWidth: 130,
    fontWeight: 600,
    color: '#444',
    pt: '6px',
    flexShrink: 0,
  };

  return (
    <LocalizationProvider dateAdapter={AdapterDateFns}>
      <Box sx={{ maxWidth: 740, mx: 'auto', py: 1 }}>
        {/* 標題 */}
        <Typography
          variant="h5"
          align="center"
          fontWeight={700}
          sx={{ mb: 3, letterSpacing: 1 }}
        >
          {readOnly ? '任務詳細資料' : '建立新任務'}
        </Typography>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {hasLimit && (
          <Alert severity={atLimit ? 'warning' : 'info'} sx={{ mb: 2 }}>
            {atLimit
              ? `已達到任務建立上限（已建立 ${currentTaskCount} / ${maxTaskCount}），無法再建立新任務`
              : `可建立任務數量：已建立 ${currentTaskCount} / ${maxTaskCount}，剩餘 ${remainingTasks} 個`}
          </Alert>
        )}

        <Box sx={{ border: '1px solid #e0e0e0', borderRadius: 1, overflow: 'hidden' }}>

          {/* 任務名稱 */}
          <Box sx={ROW_SX}>
            <Typography sx={LABEL_SX}>任務名稱</Typography>
            {readOnly ? (
              <Typography variant="body2" sx={{ pt: '6px' }}>{taskName || '-'}</Typography>
            ) : (
              <input
                style={{
                  flex: 1,
                  border: '1px solid #c4c4c4',
                  borderRadius: 4,
                  padding: '6px 10px',
                  fontSize: 14,
                  outline: 'none',
                  width: '100%',
                }}
                placeholder="請輸入任務名稱"
                value={taskName}
                onChange={(e) => setTaskName(e.target.value)}
              />
            )}
          </Box>

          {/* 任務類型 */}
          <Box sx={ROW_SX}>
            <Typography sx={LABEL_SX}>任務類型</Typography>
            <RadioGroup
              row
              value={taskType}
              onChange={(e) => setTaskType(e.target.value)}
            >
              <FormControlLabel value="pre" control={<Radio size="small" disabled={readOnly} />} label="前測" />
              <FormControlLabel value="official" control={<Radio size="small" disabled={readOnly} />} label="正式" />
            </RadioGroup>
          </Box>

          {/* 開始及結束時間 */}
          <Box sx={ROW_SX}>
            <Typography sx={LABEL_SX}>開始及結束時間</Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: 1 }}>
              <MobileDateTimePicker
                value={startDate}
                onChange={(val) => setStartDate(val)}
                disabled={readOnly}
                slotProps={{ textField: { size: 'small', sx: { flex: 1 } } }}
                format="yyyy/MM/dd HH:mm"
              />
              <Typography sx={{ color: '#888', px: 0.5 }}>～</Typography>
              <MobileDateTimePicker
                value={endDate}
                onChange={(val) => setEndDate(val)}
                disabled={readOnly}
                slotProps={{ textField: { size: 'small', sx: { flex: 1 } } }}
                format="yyyy/MM/dd HH:mm"
              />
            </Box>
          </Box>

          {/* 停止寄送日期 */}
          <Box sx={ROW_SX}>
            <Typography sx={LABEL_SX}>停止寄送日期</Typography>
            <MobileDateTimePicker
              value={stopDate}
              onChange={(val) => setStopDate(val)}
              disabled={readOnly}
              slotProps={{ textField: { size: 'small', sx: { flex: 1, width: '100%' } } }}
              format="yyyy/MM/dd HH:mm"
            />
          </Box>

          {/* 演練參與人員 */}
          <Box sx={ROW_SX}>
            <Typography sx={LABEL_SX}>演練參與人員</Typography>
            <Box sx={{ flex: 1 }}>
              {readOnly ? (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, pt: '4px' }}>
                  <Typography variant="body2">
                    參與人數：{initialData?.person_count ?? (initialData?.participants?.length ?? '-')} 人
                  </Typography>
                  {(initialData?.participants?.length > 0) && (
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={() => setParticipantDialogOpen(true)}
                      sx={{ fontSize: '0.75rem', py: 0.3 }}
                    >
                      清冊
                    </Button>
                  )}
                </Box>
              ) : (
                <>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                    <Button
                      variant="outlined"
                      size="small"
                      component="label"
                      startIcon={<UploadFile />}
                      sx={{ whiteSpace: 'nowrap', minWidth: 100 }}
                    >
                      選擇檔案
                      <input
                        type="file"
                        accept=".csv,.xlsx,.xls"
                        hidden
                        onChange={handleFileChange}
                      />
                    </Button>
                    <Typography variant="body2" color={participantFile ? 'text.primary' : 'text.secondary'}>
                      {participantFile ? participantFile.name : '未選擇任何檔案'}
                    </Typography>
                    <Link
                      component="button"
                      variant="body2"
                      underline="hover"
                      onClick={handleDownloadTemplate}
                      sx={{ ml: 'auto', display: 'flex', alignItems: 'center', gap: 0.5, color: '#1976d2', whiteSpace: 'nowrap' }}
                    >
                      <Download fontSize="small" />
                      下載範例檔
                    </Link>
                  </Box>
                  <Typography variant="caption" color="text.secondary">
                    支援 CSV / Excel 格式，欄位：UnitName, SubUnitName(Optional), UserName, UserEMail, Order(Optional)
                  </Typography>
                  {allowedEmailDomains && allowedEmailDomains.length > 0 && (
                    <Typography variant="caption" color="error" sx={{ display: 'block', mt: 0.5 }}>
                      * 僅允許以下 Email Domain: {allowedEmailDomains.map(d => `@${d}`).join(', ')}
                    </Typography>
                  )}
                </>
              )}
            </Box>
          </Box>

          {/* 郵件樣本 */}
          <Box sx={{ display: 'flex', alignItems: 'flex-start', py: 2 }}>
            <Typography sx={LABEL_SX}>郵件樣本</Typography>
            <Box sx={{ flex: 1 }}>
              {loadingTemplates ? (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <CircularProgress size={18} />
                  <Typography variant="body2">載入中...</Typography>
                </Box>
              ) : readOnly ? (
                // 唯讀模式：只顯示已選的樣本名稱
                (() => {
                  const selected = mailTemplates.filter(t => selectedTemplates.includes(t.mtmpl_uuid));
                  return selected.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">（無）</Typography>
                  ) : (
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, pt: '4px' }}>
                      {selected.map(t => (
                        <Typography key={t.mtmpl_uuid} variant="body2">• {t.mtmpl_name}</Typography>
                      ))}
                    </Box>
                  );
                })()
              ) : mailTemplates.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  （尚無郵件樣本）
                </Typography>
              ) : (
                <Grid container spacing={0}>
                  {mailTemplates.map((tmpl) => (
                    <Grid item xs={12} key={tmpl.mtmpl_uuid}>
                      <FormControlLabel
                        control={
                          <Checkbox
                            size="small"
                            checked={selectedTemplates.includes(tmpl.mtmpl_uuid)}
                            onChange={() => handleTemplateToggle(tmpl.mtmpl_uuid)}
                          />
                        }
                        label={
                          <Typography variant="body2">{tmpl.mtmpl_name}</Typography>
                        }
                      />
                    </Grid>
                  ))}
                </Grid>
              )}
            </Box>
          </Box>

        </Box>

        {/* 建立任務按鈕（唯讀模式不顯示） */}
        {!readOnly && (
          <Button
            fullWidth
            variant="contained"
            size="large"
            onClick={handleSubmit}
            disabled={submitting || atLimit}
            startIcon={submitting ? <CircularProgress size={20} color="inherit" /> : <Send />}
            sx={{
              mt: 3,
              py: 1.5,
              fontSize: '1rem',
              fontWeight: 700,
              backgroundColor: '#29b6f6',
              '&:hover': { backgroundColor: '#0288d1' },
              borderRadius: 1,
            }}
          >
            {submitting ? '建立中...' : '建立任務'}
          </Button>
        )}
      </Box>

      {/* 清冊 Dialog */}
      {readOnly && (
        <Dialog
          open={participantDialogOpen}
          onClose={() => setParticipantDialogOpen(false)}
          maxWidth="sm"
          fullWidth
        >
          <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            演練參與人員清冊
            <IconButton size="small" onClick={() => setParticipantDialogOpen(false)}>
              <CloseIcon />
            </IconButton>
          </DialogTitle>
          <DialogContent dividers sx={{ p: 3 }}>
            <TableContainer component={Paper} elevation={0} sx={{ border: '1px solid #e0e0e0' }}>
              <Table size="small">
                <TableHead>
                  <TableRow sx={{ '& th': { fontWeight: 700, bgcolor: '#f8fafc', fontSize: '0.78rem' } }}>
                    {['單位', '子單位', '姓名', 'Email', '順序'].map((h) => (
                      <TableCell key={h}>{h}</TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(initialData?.participants || []).map((row, i) => (
                    <TableRow key={i} sx={{ '&:hover': { bgcolor: '#f8fafc' } }}>
                      {row.map((cell, j) => (
                        <TableCell key={j} sx={{ fontSize: '0.78rem' }}>{cell || '-'}</TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </DialogContent>
        </Dialog>
      )}
    </LocalizationProvider>
  );
}
