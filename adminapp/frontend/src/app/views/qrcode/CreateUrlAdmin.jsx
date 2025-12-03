import { useState, useEffect } from 'react';
import { useSnackbar } from 'notistack';
import {
  Box,
  Button,
  FormControl,
  Radio,
  RadioGroup,
  Typography,
  TextField,
  InputAdornment,
  IconButton,
  Link,
  Card,
  CardContent,
  Stack,
  Paper,
  Divider,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  CircularProgress,
  Grid,
  Alert,
} from '@mui/material';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import UploadIcon from '@mui/icons-material/Upload';
import CloseIcon from '@mui/icons-material/Close';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';


const CreateUrl = () => {
  const [selectedOption, setSelectedOption] = useState('');
  const [outputTextUrl, setOutputTextUrl] = useState('');
  const [outputTextQrcode, setOutputTextQrcode] = useState('');
  const { enqueueSnackbar } = useSnackbar();

  // 動態載入 pageOptions
  const [pageOptions, setPageOptions] = useState([]);
  const [loadingOptions, setLoadingOptions] = useState(true);
  const [loadError, setLoadError] = useState(null);

  // 彈跳視窗的 State
  const [openUploadDialog, setOpenUploadDialog] = useState(false);
  const [editMode, setEditMode] = useState(null);
  const [oldPageValue, setOldPageValue] = useState('');
  const [pageLabel, setPageLabel] = useState('');
  const [pageValue, setPageValue] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);

  // 刪除確認視窗
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  const trigger_url = `${window.location.origin}/trigger`;

  // 新增: 直接從 URL 生成 QR Code 的 state
  const [directUrlInput, setDirectUrlInput] = useState('');
  const api_base_url = `${window.location.origin}/api`;

  // 載入 json
  const fetchPageOptions = async () => {
    setLoadingOptions(true);
    setLoadError(null);
    try {
      const response = await fetch('/api/trigget_page/get');
      if (!response.ok) {
        throw new Error('無法載入頁面列表');
      }
      const data = await response.json();
      setPageOptions(data);
    } catch (err) {
      console.error(err);
      setLoadError(err.message);
    } finally {
      setLoadingOptions(false);
    }
  };

  useEffect(() => {
    fetchPageOptions();
  }, []);

  const handleConfirm = () => {
    if (!selectedOption) {
      enqueueSnackbar('請先選擇一個選項', { variant: 'warning' });
    } else {
      setOutputTextUrl(`${trigger_url}/page/${selectedOption}/99999_99999`)
      setOutputTextQrcode(`${trigger_url}/qrcode/${selectedOption}/uuid?uuid=99999_99999`);
    }
  };

  const handleCopyUrl = async () => {
    if (!outputTextUrl) {
      enqueueSnackbar('沒有可以複製的內容！', { variant: 'warning' });
      return;
    }
    try {
      await navigator.clipboard.writeText(outputTextUrl);
      enqueueSnackbar('複製成功！', { variant: 'success' });
    } catch (err) {
      enqueueSnackbar(`複製失敗：${err.message}`, { variant: 'error' });
    }
  };

  const handleCopyQrcode = async () => {
    if (!outputTextQrcode) {
      enqueueSnackbar('沒有可以複製的內容！', { variant: 'warning' });
      return;
    }
    try {
      await navigator.clipboard.writeText(outputTextQrcode);
      enqueueSnackbar('複製成功！', { variant: 'success' });
    } catch (err) {
      enqueueSnackbar(`複製失敗：${err.message}`, { variant: 'error' });
    }
  };

  // 彈跳視窗的處理函式
  const handleOpenUploadDialog = (option = null) => {
    if (option) {
      // 進入修改模式
      setEditMode(option.value);
      setPageLabel(option.label);
      setPageValue(option.value);
      setOldPageValue(option.value);
    } else {
      // 進入新增模式
      setEditMode(null);
      setPageLabel('');
      setPageValue('');
      setOldPageValue('');
    }
    setSelectedFile(null); // 總是清空檔案選擇
    setOpenUploadDialog(true);
  };

  const handleCloseUploadDialog = () => {
    setOpenUploadDialog(false);
    // 關閉時清空表單
    setEditMode(null);
    setPageLabel('');
    setPageValue('');
    setOldPageValue('');
    setSelectedFile(null);
  };

  const handleFileChange = (event) => {
    if (event.target.files && event.target.files.length > 0) {
      setSelectedFile(event.target.files[0]);
    }
  };

  const handleUploadAndUpdate = async () => {
    if (!pageLabel || !pageValue) {
      enqueueSnackbar('請輸入網頁名稱和 url 顯示名稱', { variant: 'warning' });
      return;
    }

    // 在"新增"模式下，檔案是必需的
    if (!editMode && !selectedFile) {
      enqueueSnackbar('請選擇要上傳的檔案', { variant: 'warning' });
      return;
    }

    const formData = new FormData();
    formData.append('pageLabel', pageLabel);
    formData.append('pageValue', pageValue);
    formData.append('oldPageValue', oldPageValue);

    // 在"修改"模式下，檔案是可選的
    if (selectedFile) {
      formData.append('file', selectedFile);
    }

    // 決定要呼叫哪個 API
    const isEdit = !!editMode;
    const apiUrl = isEdit ? '/api/trigget_page/update' : '/api/trigget_page/upload';

    try {
      const response = await fetch(apiUrl, {
        method: 'POST',
        body: formData,
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail || '操作失敗');
      }

      enqueueSnackbar(isEdit ? '修改成功！' : '上傳成功！', { variant: 'success' });
      handleCloseUploadDialog();
      fetchPageOptions();

    } catch (err) {
      console.error("操作失敗:", err);
      enqueueSnackbar(err.message, { variant: 'error' });
    }
  };

  // [新增] 刪除處理函式
  const handleOpenDeleteDialog = (option) => {
    setDeleteConfirm(option);
  };

  const handleCloseDeleteDialog = () => {
    setDeleteConfirm(null);
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm) return;

    const formData = new FormData();
    formData.append('pageValue', deleteConfirm.value);

    try {
      const response = await fetch('/api/trigget_page/delete', {
        method: 'POST',
        body: formData,
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail || '刪除失敗');
      }

      enqueueSnackbar('刪除成功！', { variant: 'success' });
      handleCloseDeleteDialog();
      fetchPageOptions(); // [重要] 重新載入列表

      // 如果刪除的是當前選中的，清空選項
      if (selectedOption === deleteConfirm.value) {
        setSelectedOption('');
      }

    } catch (err) {
      console.error("刪除失敗:", err);
      enqueueSnackbar(err.message, { variant: 'error' });
    }
  };


  return (
    <>

      <Card sx={{ maxWidth: 1200, mx: 'auto', mt: 4, borderRadius: 3, boxShadow: 3, position: 'relative' }}>
        <CardContent>
          <Grid container spacing={4}>
            {/* 左側: 操作區 */}
            <Grid item xs={12} md={7}>
              <Stack spacing={3}>
                <Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                    <Typography variant="h5" component="h1">
                      假網址生成
                    </Typography>
                    <Button
                      variant="contained"
                      color="secondary"
                      startIcon={<UploadIcon />}
                      onClick={handleOpenUploadDialog}
                    >
                      上傳頁面
                    </Button>
                  </Box>
                  <Typography variant="h6" component="h2" sx={{ color: 'text.secondary' }}>
                    請選擇登入頁面版型：
                  </Typography>
                </Box>

                {loadingOptions ? (
                  <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
                    <CircularProgress />
                  </Box>
                ) : loadError ? (
                  <Alert severity="error">
                    {loadError} <Button onClick={fetchPageOptions}>重試</Button>
                  </Alert>
                ) : (
                  <FormControl component="fieldset" fullWidth>
                    <RadioGroup
                      aria-label="trigger-page-template"
                      name="option"
                      value={selectedOption}
                      onChange={(e) => setSelectedOption(e.target.value)}
                    >
                      <Stack spacing={1}>
                        {pageOptions.map((option) => (
                          <Paper
                            key={option.value}
                            variant="outlined"
                            sx={{
                              p: 1.5,
                              display: 'flex',
                              alignItems: 'center',
                              cursor: 'pointer',
                              '&:hover': { backgroundColor: 'action.hover' },
                              ...(selectedOption === option.value && {
                                borderColor: 'primary.main',
                                boxShadow: (theme) => `0 0 0 1px ${theme.palette.primary.main}`,
                              })
                            }}
                            onClick={() => setSelectedOption(option.value)}
                          >
                            <Radio
                              checked={selectedOption === option.value}
                              value={option.value}
                              name="option-radio-button"
                            />
                            <Typography sx={{ flexGrow: 1, ml: 1, fontWeight: 500 }}>
                              {option.label}
                            </Typography>
                            <Stack direction="row" spacing={0.5}>
                              <Button
                                component={Link}
                                href={trigger_url + '/' + option.value + '/test'}
                                target="_blank"
                                rel="noopener noreferrer"
                                variant="outlined"
                                size="small"
                                onClick={(e) => e.stopPropagation()}
                              >
                                預覽
                              </Button>
                              <IconButton
                                size="small"
                                color="primary"
                                onClick={(e) => { e.stopPropagation(); handleOpenUploadDialog(option); }}
                              >
                                <EditIcon fontSize="small" />
                              </IconButton>
                              <IconButton
                                size="small"
                                color="error"
                                onClick={(e) => { e.stopPropagation(); handleOpenDeleteDialog(option); }}
                              >
                                <DeleteIcon fontSize="small" />
                              </IconButton>
                            </Stack>
                          </Paper>
                        ))}
                      </Stack>
                    </RadioGroup>
                  </FormControl>
                )}

                <Box>
                  <Button
                    variant="contained"
                    size="large"
                    onClick={handleConfirm}
                    disabled={loadingOptions || !!loadError}
                  >
                    產生網址
                  </Button>
                </Box>

                <Box>
                  <Divider sx={{ my: 3 }} />
                  <Typography variant="h6" component="h3" gutterBottom>
                    從任意網址生成 QR Code
                  </Typography>
                  <Stack spacing={2} direction="row" alignItems="center">
                    <TextField
                      fullWidth
                      label="請在此貼上網址"
                      value={directUrlInput}
                      onChange={(e) => setDirectUrlInput(e.target.value)}
                      variant="outlined"
                      size="small"
                    />
                    <Button variant="contained" onClick={() => {
                      if (!directUrlInput) {
                        enqueueSnackbar('請輸入網址', { variant: 'warning' });
                        return;
                      }
                      try {
                        setOutputTextUrl(`${trigger_url}/page/from-url/99999_99999?url=${encodeURIComponent(directUrlInput)}`)
                        setOutputTextQrcode(`${trigger_url}/qrcode/from-url/uuid?uuid=99999_99999&url=${encodeURIComponent(directUrlInput)}`);
                      } catch (e) {
                        enqueueSnackbar('請輸入有效的網址 (例如: https://www.google.com)', { variant: e });
                      }
                    }}>
                      產生
                    </Button>
                  </Stack>
                </Box>
              </Stack>
            </Grid>

            {/* 右側: 結果區 */}
            <Grid item xs={12} md={5}>
              <Paper variant="outlined" sx={{ p: 2, position: 'sticky', top: '20px' }}>
                <Typography variant="h6" component="h3" gutterBottom>
                  產生的網址
                </Typography>
                <Stack spacing={2}>
                  <TextField
                    fullWidth
                    label="Url"
                    value={outputTextUrl}
                    InputProps={{
                      readOnly: true,
                      endAdornment: (
                        <InputAdornment position="end">
                          <IconButton aria-label="copy url" onClick={handleCopyUrl} edge="end">
                            <ContentCopyIcon />
                          </IconButton>
                        </InputAdornment>
                      ),
                    }}
                  />
                  <TextField
                    fullWidth
                    label="Qrcode網址"
                    value={outputTextQrcode}
                    InputProps={{
                      readOnly: true,
                      endAdornment: (
                        <InputAdornment position="end">
                          <IconButton aria-label="copy url" onClick={handleCopyQrcode} edge="end">
                            <ContentCopyIcon />
                          </IconButton>
                        </InputAdornment>
                      ),
                    }}
                  />
                  {outputTextUrl && (
                    <Box sx={{ textAlign: 'center', mt: 2 }}>
                      <img src={outputTextQrcode} alt="QR Code" style={{ maxWidth: '150px', height: 'auto' }} />
                    </Box>
                  )}
                </Stack>
              </Paper>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      <Dialog open={openUploadDialog} onClose={handleCloseUploadDialog} fullWidth maxWidth="xs">
        <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          {editMode ? '修改頁面版型' : '上傳新頁面版型'}
          <IconButton onClick={handleCloseUploadDialog} edge="end">
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              autoFocus
              required
              margin="dense"
              id="pageLabel"
              label="網頁名稱 (Label)"
              helperText="顯示在選項中的名稱 (e.g., '我的新頁面')"
              type="text"
              fullWidth
              variant="outlined"
              value={pageLabel}
              onChange={(e) => setPageLabel(e.target.value)}
            />
            <TextField
              required
              margin="dense"
              id="pageValue"
              label="網頁值 (Value)"
              helperText="用於 URL 和檔名 (e.g., 'mynewpage')，只能用小寫英文、數字、底線"
              type="text"
              fullWidth
              variant="outlined"
              value={pageValue}
              onChange={(e) => setPageValue(e.target.value.toLowerCase().trim())}
            // disabled={!!editMode} // 修改時，Value (主鍵) 不可變
            />
            <Button
              variant="outlined"
              component="label"
            >
              {editMode ? '上傳新檔案 (可選)' : '上傳 HTML 檔案 (必需)'}
              <input
                type="file"
                hidden
                onChange={handleFileChange}
                accept=".html"
              />
            </Button>
            {selectedFile && (
              <Typography variant="body2" color="text.secondary">
                已選擇: {selectedFile.name}
              </Typography>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseUploadDialog}>取消</Button>
          <Button onClick={handleUploadAndUpdate} variant="contained">
            {editMode ? '儲存修改' : '上傳'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* 刪除確認視窗 */}
      <Dialog
        open={!!deleteConfirm}
        onClose={handleCloseDeleteDialog}
        maxWidth="xs"
      >
        <DialogTitle>確認刪除</DialogTitle>
        <DialogContent>
          <Typography>
            你確定要刪除頁面 <strong>"{deleteConfirm?.label}"</strong> 嗎？
          </Typography>
          <Typography color="text.secondary" variant="body2">
            (value: {deleteConfirm?.value})
          </Typography>
          <Alert severity="error" sx={{ mt: 2 }}>
            此動作無法復原。對應的 HTML 檔案將會被永久刪除。
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDeleteDialog}>取消</Button>
          <Button onClick={handleDeleteConfirm} variant="contained" color="error">
            確認刪除
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};
export default CreateUrl;