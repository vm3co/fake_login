import { useState } from 'react';
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
} from '@mui/material';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import UploadIcon from '@mui/icons-material/Upload';

import pageOptions from '../../../../../backend/data/pageOptions.json';


const CreateUrl = () => {
  const [selectedOption, setSelectedOption] = useState('');
  const [outputTextUrl, setOutputTextUrl] = useState('');
  const [outputTextQrcode, setOutputTextQrcode] = useState('');
  const { enqueueSnackbar } = useSnackbar();

  // 彈跳視窗的 State
  const [openUploadDialog, setOpenUploadDialog] = useState(false);
  const [pageName, setPageName] = useState('');
  const [urlName, setUrlName] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);

  const trigger_url = import.meta.env.VITE_APP_BASE_URL;

  // ... 所有的 handle function (handleConfirm, handleCopyUrl, handleCopyQrcode) 保持不變 ...
  const handleConfirm = () => {
    const url_head = trigger_url + '/';
    const url_end = '/99999_99999';
    const url_qrcode_head = trigger_url + '/qrcode/';
    const url_qrcode_end = '/uuid?uuid=99999_99999';
    if (!selectedOption) {
      enqueueSnackbar('請先選擇一個選項', { variant: 'warning' });
    } else {
      setOutputTextUrl(url_head + selectedOption + url_end);
      setOutputTextQrcode(url_qrcode_head + selectedOption + url_qrcode_end);
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
  const handleOpenUploadDialog = () => {
    setOpenUploadDialog(true);
  };

  const handleCloseUploadDialog = () => {
    setOpenUploadDialog(false);
    // 關閉時清空表單
    setPageName('');
    setUrlName('');
    setSelectedFile(null);
  };

  const handleFileChange = (event) => {
    if (event.target.files && event.target.files.length > 0) {
      setSelectedFile(event.target.files[0]);
    }
  };

  const handleUpload = () => {
    if (!pageName || !urlName || !selectedFile) {
      enqueueSnackbar('請輸入網頁名稱、url顯示名稱並選擇檔案', { variant: 'warning' });
      return;
    }

    // --- 模擬上傳邏輯 ---
    // 在這裡，你未來會呼叫 API
    console.log('開始上傳...');
    console.log('網頁名稱:', pageName);
    console.log('url顯示名稱:', urlName);
    console.log('檔案:', selectedFile.name);

    // 模擬 FormData
    const formData = new FormData();
    formData.append('pageName', pageName);
    formData.append('urlName', urlName);
    formData.append('file', selectedFile);

    // 假設上傳成功
    // axios.post('/api/upload-page', formData).then(...)
    
    enqueueSnackbar('上傳成功！', { variant: 'success' });
    handleCloseUploadDialog();
    // --- 模擬結束 ---
  };


  return (
    <>
      <Card sx={{ maxWidth: 700, mx: 'auto', mt: 4, borderRadius: 3, boxShadow: 3, position: 'relative' }}>
        <Button
          variant="contained"
          color="secondary"
          startIcon={<UploadIcon />}
          onClick={handleOpenUploadDialog}
          sx={{
            position: 'absolute',
            top: 16,
            right: 16,
            zIndex: 10 // 確保在 CardContent 之上
          }}
        >
          上傳頁面
        </Button>

        <CardContent>
          {/* 使用 Stack 進行垂直佈局和間距控制 */}
          <Stack spacing={3}>
            <Box>
              <Typography variant="h5" component="h1" gutterBottom>
                產生 QR Code 網址
              </Typography>
              <Typography variant="h6" component="h2" sx={{ color: 'text.secondary' }}>
                請選擇登入頁面版型：
              </Typography>
            </Box>

            <FormControl component="fieldset" fullWidth>
              <RadioGroup
                aria-label="trigger-page-template"
                name="option"
                value={selectedOption}
                onChange={(e) => setSelectedOption(e.target.value)}
              >
                {/* 使用 Stack 來堆疊選項 */}
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
                        '&:hover': {
                          backgroundColor: 'action.hover'
                        },
                        // 如果被選中，顯示主題色的邊框
                        ...(selectedOption === option.value && {
                          borderColor: 'primary.main',
                          boxShadow: (theme) => `0 0 0 1px ${theme.palette.primary.main}`,
                        })
                      }}
                      // 點擊 Paper 任何地方都可以選中
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
                      <Button
                        component={Link} //
                        href={trigger_url + '/' + option.value + '/test'}
                        target="_blank"
                        rel="noopener noreferrer"
                        variant="outlined"
                        size="small"
                        // 阻止點擊「預覽」時觸發 Paper 的 onClick
                        onClick={(e) => e.stopPropagation()} 
                      >
                        預覽
                      </Button>
                    </Paper>
                  ))}
                </Stack>
              </RadioGroup>
            </FormControl>

            <Box>
              <Button variant="contained" size="large" onClick={handleConfirm}>
                產生網址
              </Button>
            </Box>
            
            {/* 將結果區塊用 Divider 隔開 */}
            {outputTextUrl && (
              <Box>
                <Divider sx={{ mb: 3 }} />
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
                </Stack>
              </Box>
            )}
          </Stack>
        </CardContent>
      </Card>
      <Dialog open={openUploadDialog} onClose={handleCloseUploadDialog} fullWidth maxWidth="xs">
        <DialogTitle>上傳新頁面版型</DialogTitle>
        <DialogContent>
          {/* 使用 Stack 讓表單有間距 */}
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              autoFocus
              margin="dense"
              id="pageName"
              label="網頁名稱"
              type="text"
              fullWidth
              variant="outlined"
              value={pageName}
              onChange={(e) => setPageName(e.target.value)}
            />
            <TextField
              autoFocus
              margin="dense"
              id="urlName"
              label="url顯示名稱(限英文、數字、底線)"
              type="text"
              fullWidth
              variant="outlined"
              value={urlName}
              onChange={(e) => setUrlName(e.target.value)}
            />
            <Button
              variant="outlined"
              component="label" // 關鍵：讓 Button 觸發 file input
            >
              上傳檔案
              <input
                type="file"
                hidden
                onChange={handleFileChange}
                // 限制檔案類型 (可選)
                accept=".html,.htm,.php,.asp,.aspx,.xml" 
              />
            </Button>
            {/* 顯示已選擇的檔案名稱 */}
            {selectedFile && (
              <Typography variant="body2" color="text.secondary">
                已選擇: {selectedFile.name}
              </Typography>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseUploadDialog}>取消</Button>
          <Button onClick={handleUpload} variant="contained">上傳</Button>
        </DialogActions>
      </Dialog>
    </>
  );
};
export default CreateUrl;