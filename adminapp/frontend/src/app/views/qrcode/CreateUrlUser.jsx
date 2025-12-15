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
  CircularProgress,
  Grid,
  Alert,
} from '@mui/material';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';


const CreateUrl = () => {
  const [selectedOption, setSelectedOption] = useState('');
  const [outputTextUrl, setOutputTextUrl] = useState('');
  const [outputTextQrcode, setOutputTextQrcode] = useState('');
  const { enqueueSnackbar } = useSnackbar();

  // 動態載入 pageOptions
  const [pageOptions, setPageOptions] = useState([]);
  const [loadingOptions, setLoadingOptions] = useState(true);
  const [loadError, setLoadError] = useState(null);

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
    </>
  );
};
export default CreateUrl;