import { useState, useEffect } from 'react';
import { useSnackbar } from 'notistack';
import {
  Box,
  Button,
  FormControl,
  FormControlLabel,
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
  CircularProgress,
  Grid,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Checkbox,
} from '@mui/material';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import CloseIcon from '@mui/icons-material/Close';


const CreateUrl = () => {
  const [selectedOption, setSelectedOption] = useState('');
  const [outputTextUrl, setOutputTextUrl] = useState('');
  const [outputTextQrcode, setOutputTextQrcode] = useState('');
  const { enqueueSnackbar } = useSnackbar();

  // 動態載入 pageOptions
  const [pageOptions, setPageOptions] = useState([]);
  const [loadingOptions, setLoadingOptions] = useState(true);
  const [loadError, setLoadError] = useState(null);

  const [triggerBaseUrl, setTriggerBaseUrl] = useState('');
  const [directUrlInput, setDirectUrlInput] = useState('');
  const api_base_url = `${window.location.origin}/api`;

  // 自訂頁面彈跳視窗 State
  const [openCreateDialog, setOpenCreateDialog] = useState(false);
  const [createPageLabel, setCreatePageLabel] = useState('');
  const [createPageValue, setCreatePageValue] = useState('');
  const [createPageTitle, setCreatePageTitle] = useState('');
  const [createBgColor, setCreateBgColor] = useState('#f2f2f2');
  const [createBgImage, setCreateBgImage] = useState('');
  const [createFormTitle, setCreateFormTitle] = useState('登入');
  const [createInputLabel, setCreateInputLabel] = useState('');
  const [createIsEmail, setCreateIsEmail] = useState(true);
  const [createBtnText, setCreateBtnText] = useState('登入');
  const [templateType, setTemplateType] = useState('test');
  const [createSvg, setCreateSvg] = useState('');

  // 載入 json & config
  const fetchPageOptions = async () => {
    setLoadingOptions(true);
    setLoadError(null);
    try {
      // 並行請求 config 和 pageOptions
      const [configRes, pagesRes] = await Promise.all([
        fetch('/api/trigget_page/config'),
        fetch('/api/trigget_page/get')
      ]);

      if (!pagesRes.ok) {
        throw new Error('無法載入頁面列表');
      }

      const pagesData = await pagesRes.json();
      setPageOptions(pagesData);

      if (configRes.ok) {
        const configData = await configRes.json();
        // 如果後端有回傳 triggerUrl 就用，否則 fallback 到預設 (window.location.origin + '/trigger')
        if (configData.triggerUrl) {
          setTriggerBaseUrl(configData.triggerUrl);
        } else {
          setTriggerBaseUrl(`${window.location.origin}/trigger`);
        }
      } else {
        // Config API 失敗時的 fallback
        setTriggerBaseUrl(`${window.location.origin}/trigger`);
      }

    } catch (err) {
      console.error(err);
      setLoadError(err.message);
      // 確保出錯時也有預設值
      setTriggerBaseUrl(`${window.location.origin}/trigger`);
    } finally {
      setLoadingOptions(false);
    }
  };

  useEffect(() => {
    fetchPageOptions();
  }, []);

  const handleConfirm = () => {
    // 確保有值，若無則再次 fallback
    const baseUrl = triggerBaseUrl || `${window.location.origin}/trigger`;

    if (!selectedOption) {
      enqueueSnackbar('請先選擇一個選項', { variant: 'warning' });
    } else {
      setOutputTextUrl(`${baseUrl}/page/${selectedOption}/99999_99999`)
      setOutputTextQrcode(`${baseUrl}/qrcode/${selectedOption}/uuid?uuid=99999_99999`);
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

  const handleOpenCreateDialog = () => {
    setCreatePageLabel('');
    setCreatePageValue('');
    setCreatePageTitle('');
    setCreateBgColor('#f2f2f2');
    setCreateBgImage('');
    setCreateFormTitle('登入');
    setCreateInputLabel('');
    setCreateIsEmail(true);
    setCreateBtnText('登入');
    setTemplateType('test');
    setCreateSvg('');
    setOpenCreateDialog(true);
  }

  const handleCloseCreateDialog = () => {
    setOpenCreateDialog(false);
  }

  const handleCreatePage = async () => {
    if (!createPageLabel || !createPageValue || !createPageTitle || !createFormTitle || !createInputLabel || !createBtnText) {
      enqueueSnackbar('請填寫所有必填欄位', { variant: 'warning' });
      return;
    }

    const formData = new FormData();
    formData.append('pageLabel', createPageLabel);
    formData.append('pageValue', createPageValue);
    formData.append('pageTitle', createPageTitle);
    formData.append('bgColor', createBgColor);
    formData.append('bgImage', createBgImage);
    formData.append('formTitle', createFormTitle);
    formData.append('inputLabel', createInputLabel);
    formData.append('isEmail', createIsEmail);
    formData.append('btnText', createBtnText);
    formData.append('templateType', templateType);
    formData.append('svgContent', createSvg);

    try {
      const response = await fetch('/api/trigget_page/create_page', {
        method: 'POST',
        body: formData,
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail || '操作失敗');
      }

      enqueueSnackbar('自訂頁面建立成功！', { variant: 'success' });
      handleCloseCreateDialog();
      fetchPageOptions();

    } catch (err) {
      console.error("操作失敗:", err);
      enqueueSnackbar(err.message, { variant: 'error' });
    }
  }

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
                      color="primary"
                      onClick={handleOpenCreateDialog}
                    >
                      新增自訂頁面
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
                                href={trigger_url + '/page/' + option.value + '/test'}
                                target="_blank"
                                rel="noopener noreferrer"
                                variant="outlined"
                                size="small"
                                onClick={(e) => e.stopPropagation()}
                              >
                                預覽
                              </Button>
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
                        const baseUrl = triggerBaseUrl || `${window.location.origin}/trigger`;
                        setOutputTextUrl(`${baseUrl}/page/from-url/99999_99999?url=${encodeURIComponent(directUrlInput)}`)
                        setOutputTextQrcode(`${baseUrl}/qrcode/from-url/uuid?uuid=99999_99999&url=${encodeURIComponent(directUrlInput)}`);
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
                    label="Qrcode網址(圖片網址)"
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
                  <Typography variant="body2" color="textSecondary">
                    說明：請將Url貼至「插入/編輯連結」的「網址」，將Qrcode網址貼至「插入/編輯 圖片」的「圖片網址」。
                    不要將下方的Qrcode圖片直接貼到郵件裡，會無法記錄觸發紀錄。
                  </Typography>
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

      {/* 新增自訂頁面 Dialog */}
      <Dialog open={openCreateDialog} onClose={handleCloseCreateDialog} fullWidth maxWidth="sm">
        <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          新增自訂頁面
          <IconButton onClick={handleCloseCreateDialog} edge="end">
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              required
              label="顯示名稱 (Label)"
              value={createPageLabel}
              onChange={(e) => setCreatePageLabel(e.target.value)}
              helperText="後台列表中顯示的名稱"
              fullWidth
            />
            <TextField
              required
              label="網頁代號 (Value)"
              value={createPageValue}
              onChange={(e) => setCreatePageValue(e.target.value.toLowerCase().trim())}
              helperText="網址中的 ID，只能包含小寫英文、數字、底線"
              fullWidth
            />
            <FormControl component="fieldset">
              <Typography variant="body1" gutterBottom>選擇版型：</Typography>
              <RadioGroup
                row
                name="templateType"
                value={templateType}
                onChange={(e) => setTemplateType(e.target.value)}
              >
                <FormControlLabel value="test" control={<Radio />} label="Test (預設)" />
                <FormControlLabel value="modern" control={<Radio />} label="Modern (新版)" />
              </RadioGroup>
            </FormControl>

            {templateType === 'modern' && (
              <TextField
                label="SVG 圖示 (XML 代碼)"
                value={createSvg}
                onChange={(e) => setCreateSvg(e.target.value)}
                helperText="貼上 SVG 代碼以替換預設圖示 (可選)"
                fullWidth
                multiline
                rows={3}
                placeholder={`<svg ...>...</svg>`}
              />
            )}
            <Divider />
            <TextField
              required
              label="網頁標題 (HTML Title)"
              value={createPageTitle}
              onChange={(e) => setCreatePageTitle(e.target.value)}
              helperText="瀏覽器分頁標籤上顯示的文字"
              fullWidth
            />
            <Stack direction="row" spacing={2} alignItems="center">
              <TextField
                required
                label="背景顏色 (Hex/Name)"
                value={createBgColor}
                onChange={(e) => setCreateBgColor(e.target.value)}
                fullWidth
              />
              <Box
                sx={{
                  width: 40,
                  height: 40,
                  backgroundColor: createBgColor,
                  border: '1px solid #ccc',
                  borderRadius: 1
                }}
              />
            </Stack>

            <TextField
              label="背景圖片 URL (可選)"
              value={createBgImage}
              onChange={(e) => setCreateBgImage(e.target.value)}
              helperText="如果填入，將覆蓋背景顏色"
              fullWidth
            />
            <TextField
              required
              label="表單標題"
              value={createFormTitle}
              onChange={(e) => setCreateFormTitle(e.target.value)}
              helperText="登入框上方的大標題"
              fullWidth
            />
            <TextField
              required
              label="輸入框標籤"
              value={createInputLabel}
              onChange={(e) => setCreateInputLabel(e.target.value)}
              helperText="例如：電子郵件地址, Email, 帳號, 員工編號"
              fullWidth
            />
            <FormControlLabel
              label="是否為電子郵件"
              control={
                <Checkbox
                  checked={createIsEmail}
                  onChange={(e) => setCreateIsEmail(e.target.checked)}
                />
              }
            />
            <TextField
              required
              label="按鈕文字"
              value={createBtnText}
              onChange={(e) => setCreateBtnText(e.target.value)}
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseCreateDialog}>取消</Button>
          <Button onClick={handleCreatePage} variant="contained" color="primary">
            建立
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};
export default CreateUrl;