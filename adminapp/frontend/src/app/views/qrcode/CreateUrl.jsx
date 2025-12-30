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
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    CircularProgress,
    Grid,
    Alert,
    Checkbox,
} from '@mui/material';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import UploadIcon from '@mui/icons-material/Upload';
import CloseIcon from '@mui/icons-material/Close';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';


const CreateUrl = ({ isAdmin }) => {
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
    const [createTemplateType, setCreateTemplateType] = useState('test');
    const [createSvg, setCreateSvg] = useState('');

    // AI 生成彈跳視窗 State
    const [openAiDialog, setOpenAiDialog] = useState(false);
    const [aiPrompt, setAiPrompt] = useState('');
    const [aiRefUrl, setAiRefUrl] = useState('');
    const [generating, setGenerating] = useState(false);


    // 刪除確認視窗
    const [deleteConfirm, setDeleteConfirm] = useState(null);

    const [triggerBaseUrl, setTriggerBaseUrl] = useState('');
    const [directUrlInput, setDirectUrlInput] = useState('');

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

    // 彈跳視窗的處理函式
    const handleOpenUploadDialog = (option = null) => {
        if (option) {
            // 進入修改模式
            setEditMode(option.value);
            setPageLabel(option.label);
            setPageValue(option.value);
            setOldPageValue(option.value);
            setOpenUploadDialog(true); // Only open regular upload/edit dialog
        } else {
            // Only for upload new file
            setEditMode(null);
            setPageLabel('');
            setPageValue('');
            setOldPageValue('');
            setOpenUploadDialog(true);
        }
        setSelectedFile(null);
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
        setCreateTemplateType('test');
        setCreateSvg('');
        setOpenCreateDialog(true);
    }

    const handleCloseUploadDialog = () => {
        setOpenUploadDialog(false);
        // 關閉時清空表單
        setEditMode(null);
        setPageLabel('');
        setPageValue('');
        setOldPageValue('');
        setSelectedFile(null);
    };

    const handleCloseCreateDialog = () => {
        setOpenCreateDialog(false);
    }

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
        formData.append('templateType', createTemplateType);
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

    // AI 生成處理函式
    const handleOpenAiDialog = () => {
        setAiPrompt('');
        setAiRefUrl('');
        setOpenAiDialog(true);
    };

    const handleCloseAiDialog = () => {
        setOpenAiDialog(false);
    };

    const handleGenerateWithAi = async () => {
        if (!aiPrompt) {
            enqueueSnackbar('請輸入提示詞 (Prompt)', { variant: 'warning' });
            return;
        }

        setGenerating(true);
        const formData = new FormData();
        formData.append('prompt', aiPrompt);
        if (aiRefUrl) {
            formData.append('refUrl', aiRefUrl);
        }

        try {
            const response = await fetch('/api/trigget_page/generate_with_ai', {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                const result = await response.json();
                throw new Error(result.detail || '生成失敗');
            }

            const htmlContent = await response.text();

            // 成功生成後，關閉 AI Dialog，開啟 Upload Dialog，並將內容轉換為檔案
            setOpenAiDialog(false);

            // 建立一個 File 物件
            const blob = new Blob([htmlContent], { type: 'text/html' });
            const timestamp = new Date().getTime();
            const fileName = `ai_generated_${timestamp}.html`;
            const file = new File([blob], fileName, { type: 'text/html' });

            // 預設一些欄位
            setEditMode(null);
            setPageLabel(`AI 生成頁面 ${new Date().toLocaleTimeString()}`);
            setPageValue(`ai_${timestamp}`);
            setOldPageValue('');
            setSelectedFile(file);

            // 開啟上傳視窗確認
            setOpenUploadDialog(true);

            enqueueSnackbar('AI 生成成功！請確認並儲存頁面。', { variant: 'success' });

        } catch (err) {
            console.error("AI 生成失敗:", err);
            enqueueSnackbar(err.message, { variant: 'error' });
        } finally {
            setGenerating(false);
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

    const baseUrl = triggerBaseUrl || `${window.location.origin}/trigger`;

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
                                        <Stack direction="row" spacing={1}>
                                            <Button
                                                variant="contained"
                                                color="primary" // Different color
                                                onClick={handleOpenCreateDialog}
                                            >
                                                新增自訂頁面
                                            </Button>
                                            <Button
                                                variant="contained"
                                                color="success"
                                                startIcon={<AutoAwesomeIcon />}
                                                onClick={handleOpenAiDialog}
                                            >
                                                AI 生成頁面
                                            </Button>
                                            {isAdmin && (
                                                <Button
                                                    variant="contained"
                                                    color="secondary"
                                                    startIcon={<UploadIcon />}
                                                    onClick={() => handleOpenUploadDialog()}
                                                >
                                                    上傳頁面
                                                </Button>
                                            )}
                                        </Stack>
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
                                                                href={baseUrl + '/page/' + option.value + '/test'}
                                                                target="_blank"
                                                                rel="noopener noreferrer"
                                                                variant="outlined"
                                                                size="small"
                                                                onClick={(e) => e.stopPropagation()}
                                                            >
                                                                預覽
                                                            </Button>
                                                            {isAdmin && (
                                                                <>
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
                                                                </>
                                                            )}
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
                            label="名稱"
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
                            label="網址 ID"
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
                            label="名稱"
                            value={createPageLabel}
                            onChange={(e) => setCreatePageLabel(e.target.value)}
                            helperText="後台列表中顯示的名稱"
                            fullWidth
                        />
                        <TextField
                            required
                            label="網址 ID"
                            value={createPageValue}
                            onChange={(e) => setCreatePageValue(e.target.value.toLowerCase().trim())}
                            helperText="網址 ID，只能包含小寫英文、數字、底線"
                            fullWidth
                        />
                        <FormControl component="fieldset">
                            <Typography variant="body1" gutterBottom>選擇版型：</Typography>
                            <RadioGroup
                                row
                                name="templateType"
                                value={createTemplateType}
                                onChange={(e) => setCreateTemplateType(e.target.value)}
                            >
                                <FormControlLabel value="test" control={<Radio />} label="Test (預設)" />
                                <FormControlLabel value="modern" control={<Radio />} label="Modern (新版)" />
                            </RadioGroup>
                        </FormControl>

                        {createTemplateType === 'modern' && (
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
                                    borderRadius: 1,
                                    position: 'relative',
                                    overflow: 'hidden',
                                    cursor: 'pointer'
                                }}
                            >
                                <input
                                    type="color"
                                    value={createBgColor}
                                    onChange={(e) => setCreateBgColor(e.target.value)}
                                    style={{
                                        position: 'absolute',
                                        top: 0,
                                        left: 0,
                                        width: '100%',
                                        height: '100%',
                                        opacity: 0,
                                        cursor: 'pointer',
                                        padding: 0,
                                        border: 'none',
                                    }}
                                />
                            </Box>
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
            {/* AI 生成 Dialog */}
            <Dialog open={openAiDialog} onClose={handleCloseAiDialog} fullWidth maxWidth="sm">
                <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <AutoAwesomeIcon color="primary" />
                        AI 智慧生成頁面
                    </Box>
                    <IconButton onClick={handleCloseAiDialog} edge="end">
                        <CloseIcon />
                    </IconButton>
                </DialogTitle>
                <DialogContent>
                    <Stack spacing={2} sx={{ pt: 1 }}>
                        <Alert severity="info" sx={{ mb: 2 }}>
                            輸入您想要的頁面描述，AI 將自動為您生成包含社交功能的 HTML 頁面。<br />
                            例如：「一個深色背景的 Instagram 登入頁面」
                        </Alert>
                        <TextField
                            autoFocus
                            required
                            label="提示詞 (Prompt)"
                            placeholder="描述您想要的登入頁面外觀..."
                            multiline
                            rows={4}
                            fullWidth
                            variant="outlined"
                            onChange={(e) => setAiPrompt(e.target.value)}
                            disabled={generating}
                        />
                        <TextField
                            label="參考網址 (Optional)"
                            placeholder="例如：https://www.google.com"
                            fullWidth
                            variant="outlined"
                            value={aiRefUrl}
                            onChange={(e) => setAiRefUrl(e.target.value)}
                            disabled={generating}
                            helperText="提供網址可協助 AI 更精確還原該網站的設計風格"
                        />
                    </Stack>
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleCloseAiDialog} disabled={generating}>取消</Button>
                    <Button
                        onClick={handleGenerateWithAi}
                        variant="contained"
                        color="primary"
                        startIcon={generating ? <CircularProgress size={20} color="inherit" /> : <AutoAwesomeIcon />}
                        disabled={generating}
                    >
                        {generating ? '生成中...' : '開始生成'}
                    </Button>
                </DialogActions>
            </Dialog>
        </>
    );
};

export default CreateUrl;
