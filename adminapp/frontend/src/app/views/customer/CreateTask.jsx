import { useState, useEffect } from 'react';
import axios from 'axios';
import { useSnackbar } from 'notistack';
import {
  Box,
  Grid,
  Typography,
  TextField,
  Button,
  FormControl,
  FormControlLabel,
  FormLabel,
  RadioGroup,
  Radio,
  Checkbox,
  CircularProgress,
  Alert,
  Divider,
  Link,
} from '@mui/material';
import {
  UploadFile,
  Download,
  Send,
} from '@mui/icons-material';

/**
 * 建立新任務表單
 * 欄位：任務名稱、任務類型、開始/結束時間、停止寄送日期、演練參與人員（CSV）、郵件樣本
 */
export default function CreateTask({ onSuccess }) {
  const { enqueueSnackbar } = useSnackbar();

  // 表單狀態
  const [taskName, setTaskName] = useState('');
  const [taskType, setTaskType] = useState('pre'); // 'pre' | 'official'
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [stopDate, setStopDate] = useState('');
  const [participantFile, setParticipantFile] = useState(null);
  const [selectedTemplates, setSelectedTemplates] = useState([]);

  // 郵件樣本資料
  const [mailTemplates, setMailTemplates] = useState([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);

  // 送出狀態
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  // 從 Cookie 取得指定值
  const getCookie = (name) => {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return decodeURIComponent(parts.pop().split(';').shift());
    return null;
  };

  // 載入郵件樣本
  useEffect(() => {
    const fetchTemplates = async () => {
      setLoadingTemplates(true);
      try {
        const orgUuid = getCookie('task_creation_org_uuid');
        if (!orgUuid) {
          console.warn('找不到組織 UUID，無法取得郵件樣本');
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
  }, []);

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
    const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = '演練參與人員範例.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  // 驗證表單
  const validate = () => {
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

      // 讀取 CSV 內容為字串
      let participantData = '';
      if (participantFile) {
        participantData = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = (e) => resolve(e.target.result);
          reader.onerror = (e) => reject(e);
          reader.readAsText(participantFile);
        });
      }

      const orgUuid = getCookie('task_creation_org_uuid');
      const customerUuid = getCookie('customer_uuid');

      const payload = {
        task_name: taskName.trim(),
        task_type: taskType,
        start_date: startDate,
        end_date: endDate,
        stop_date: stopDate || null,
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
        // 清空表單
        setTaskName('');
        setTaskType('pre');
        setStartDate('');
        setEndDate('');
        setStopDate('');
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
  // 表格列樣式
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
    <Box sx={{ maxWidth: 740, mx: 'auto', py: 1 }}>
      {/* 標題 */}
      <Typography
        variant="h5"
        align="center"
        fontWeight={700}
        sx={{ mb: 3, letterSpacing: 1 }}
      >
        建立新任務
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Box sx={{ border: '1px solid #e0e0e0', borderRadius: 1, overflow: 'hidden' }}>

        {/* 任務名稱 */}
        <Box sx={ROW_SX}>
          <Typography sx={LABEL_SX}>任務名稱</Typography>
          <TextField
            fullWidth
            size="small"
            placeholder="請輸入任務名稱"
            value={taskName}
            onChange={(e) => setTaskName(e.target.value)}
            variant="outlined"
          />
        </Box>

        {/* 任務類型 */}
        <Box sx={ROW_SX}>
          <Typography sx={LABEL_SX}>任務類型</Typography>
          <RadioGroup
            row
            value={taskType}
            onChange={(e) => setTaskType(e.target.value)}
          >
            <FormControlLabel value="pre" control={<Radio size="small" />} label="前測" />
            <FormControlLabel value="official" control={<Radio size="small" />} label="正式" />
          </RadioGroup>
        </Box>

        {/* 開始及結束時間 */}
        <Box sx={ROW_SX}>
          <Typography sx={LABEL_SX}>開始及結束時間</Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: 1 }}>
            <TextField
              size="small"
              type="datetime-local"
              placeholder="請選擇開始時間"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              InputLabelProps={{ shrink: true }}
              inputProps={{ style: { color: startDate ? '#222' : '#aaa' } }}
              sx={{ flex: 1 }}
            />
            <Typography sx={{ color: '#888', px: 0.5 }}>～</Typography>
            <TextField
              size="small"
              type="datetime-local"
              placeholder="請選擇結束時間"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              InputLabelProps={{ shrink: true }}
              inputProps={{ style: { color: endDate ? '#222' : '#aaa' } }}
              sx={{ flex: 1 }}
            />
          </Box>
        </Box>

        {/* 停止寄送日期 */}
        <Box sx={ROW_SX}>
          <Typography sx={LABEL_SX}>停止寄送日期</Typography>
          <TextField
            size="small"
            type="datetime-local"
            placeholder="請選擇停止寄送時間"
            value={stopDate}
            onChange={(e) => setStopDate(e.target.value)}
            InputLabelProps={{ shrink: true }}
            inputProps={{ style: { color: stopDate ? '#222' : '#aaa' } }}
            sx={{ flex: 1, width: '100%' }}
          />
        </Box>

        {/* 演練參與人員 */}
        <Box sx={ROW_SX}>
          <Typography sx={LABEL_SX}>演練參與人員</Typography>
          <Box sx={{ flex: 1 }}>
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

      {/* 建立任務按鈕 */}
      <Button
        fullWidth
        variant="contained"
        size="large"
        onClick={handleSubmit}
        disabled={submitting}
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
    </Box>
  );
}
