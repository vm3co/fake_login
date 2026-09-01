import { useState, useEffect, useRef } from 'react';
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
    Accordion,
    AccordionSummary,
    AccordionDetails,
    Stepper,
    Step,
    StepLabel,
    Switch,
    Select,
    MenuItem,
    InputLabel,
    Chip,
} from '@mui/material';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import UploadIcon from '@mui/icons-material/Upload';
import CloseIcon from '@mui/icons-material/Close';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import DownloadIcon from '@mui/icons-material/Download';
import FileCopyIcon from '@mui/icons-material/FileCopy';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';


const CreateUrl = ({ user, isAdmin }) => {
    const [selectedOption, setSelectedOption] = useState('');
    const [outputTextUrl, setOutputTextUrl] = useState('');
    const [outputTextQrcode, setOutputTextQrcode] = useState('');
    const { enqueueSnackbar } = useSnackbar();

    // 動態載入 pageOptions
    const [pageOptions, setPageOptions] = useState([]);
    const [loadingOptions, setLoadingOptions] = useState(true);
    const [loadError, setLoadError] = useState(null);

    // domain 清單
    const [domainList, setDomainList] = useState([]);

    // 彈跳視窗的 State
    const [openUploadDialog, setOpenUploadDialog] = useState(false);
    const [editMode, setEditMode] = useState(null);
    const [oldPageValue, setOldPageValue] = useState('');
    const [pageLabel, setPageLabel] = useState('');
    const [pageValue, setPageValue] = useState('');
    const [selectedFile, setSelectedFile] = useState(null);
    const [aiGenerationId, setAiGenerationId] = useState(null);
    const [uploadAllowedDomainId, setUploadAllowedDomainId] = useState('');

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
    const [createAllowedDomainId, setCreateAllowedDomainId] = useState('');

    // AI 生成彈跳視窗 State
    const [openAiDialog, setOpenAiDialog] = useState(false);
    const [aiPrompt, setAiPrompt] = useState('');
    const [aiRefUrl, setAiRefUrl] = useState('');
    const [aiModel, setAiModel] = useState('gpt_terra');
    const [aiImage, setAiImage] = useState(null);
    const [aiPageType, setAiPageType] = useState('field'); // 'field' 欄位觸發 | 'download' 下載按鍵觸發
    const [generating, setGenerating] = useState(false);
    const [aiProgress, setAiProgress] = useState(null);
    const [useDesign, setUseDesign] = useState(false);

    // AI 網頁微調與儲存彈跳視窗 State
    const [openTweakDialog, setOpenTweakDialog] = useState(false);
    const [aiRawHtml, setAiRawHtml] = useState('');
    const [previewHtml, setPreviewHtml] = useState('');
    const [tweakPageLabel, setTweakPageLabel] = useState('');
    const [tweakPageValue, setTweakPageValue] = useState('');
    const [tweakAllowedDomainId, setTweakAllowedDomainId] = useState('');
    const [tweakTitle, setTweakTitle] = useState('登入');
    const [tweakLogo, setTweakLogo] = useState(null);
    const [tweakMainTitle, setTweakMainTitle] = useState('');
    const [tweakGenerationId, setTweakGenerationId] = useState(null);
    const [tweakNewHtmlFile, setTweakNewHtmlFile] = useState(null);

    // [新增] Logo 微調相關 State
    const [logoRemoved, setLogoRemoved] = useState(false);
    const [hasExistingLogo, setHasExistingLogo] = useState(false);

    // 支援視覺輸入（圖片）的模型清單
    const VISION_MODELS = ['gemini', 'gpt_terra', 'gpt_sol', 'gchat_gpt55', 'gchat_gpt54', 'gchat_gpt54mini', 'gchat_gemma12b'];
    const supportsVision = VISION_MODELS.includes(aiModel);


    // 刪除確認視窗
    const [deleteConfirm, setDeleteConfirm] = useState(null);

    // 摺疊分組狀態：記錄哪些分組是展開的（key = owner uuid 或 '__system__'）
    const [expandedOwners, setExpandedOwners] = useState({});

    const abortControllerRef = useRef(null);

    const [triggerBaseUrl, setTriggerBaseUrl] = useState('');
    const [ethanHosts, setEthanHosts] = useState([]);
    const [selectedLinkBase, setSelectedLinkBase] = useState('');
    const [directUrlInput, setDirectUrlInput] = useState('');

    // Redirect Config State
    const [openRedirectDialog, setOpenRedirectDialog] = useState(false);
    const [redirectOption, setRedirectOption] = useState('warning'); // 'warning' or 'custom'
    const [customRedirectUrl, setCustomRedirectUrl] = useState('');

    // 圖片壓縮輔助函式
    const compressImageToBase64 = (file, maxWidth = 300, maxHeight = 300) => {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.readAsDataURL(file);
            reader.onload = (event) => {
                const img = new Image();
                img.src = event.target.result;
                img.onload = () => {
                    let width = img.width;
                    let height = img.height;

                    if (width > height) {
                        if (width > maxWidth) {
                            height = Math.round(height * (maxWidth / width));
                            width = maxWidth;
                        }
                    } else {
                        if (height > maxHeight) {
                            width = Math.round(width * (maxHeight / height));
                            height = maxHeight;
                        }
                    }

                    const canvas = document.createElement('canvas');
                    canvas.width = width;
                    canvas.height = height;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0, width, height);
                    
                    if (file.type === 'image/svg+xml') {
                         resolve(event.target.result);
                    } else {
                         resolve(canvas.toDataURL(file.type, 0.8));
                    }
                };
                img.onerror = (error) => reject(error);
            };
            reader.onerror = (error) => reject(error);
        });
    };

    useEffect(() => {
        let isMounted = true;

        const generatePreview = async () => {
            if (!aiRawHtml) return;

            const parser = new DOMParser();
            const dom = parser.parseFromString(aiRawHtml, "text/html");

            // 強制檢查並補上 <meta charset="UTF-8"> 防呆 (預防 LLM 幻覺)
            let metaCharset = dom.querySelector('meta[charset]');
            if (!metaCharset) {
                metaCharset = dom.createElement('meta');
                metaCharset.setAttribute('charset', 'UTF-8');
                dom.head.insertBefore(metaCharset, dom.head.firstChild);
            }

            if (tweakTitle) {
                dom.title = tweakTitle;
            }

            // [新增] 替換頁面主標題 (H1)
            if (tweakMainTitle) {
                const mainTitleElement = dom.getElementById('custom-main-title');
                if (mainTitleElement) {
                    mainTitleElement.textContent = tweakMainTitle;
                }
            }

            if (tweakLogo) {
                try {
                    const base64Image = await compressImageToBase64(tweakLogo);
                    if (!isMounted) return; // 防競態條件
                    
                    const logoContainer = dom.getElementById('custom-brand-logo');
                    
                    const img = dom.createElement('img');
                    img.setAttribute('src', base64Image);
                    img.setAttribute('style', 'max-height: 80px; width: auto; display: block; margin: 0 auto 1rem auto;');
                    img.setAttribute('alt', 'Brand Logo');

                    if (logoContainer) {
                        logoContainer.innerHTML = '';
                        logoContainer.appendChild(img);
                    } else {
                        // Fallback 機制：找不到指定 ID 時，放在 form 最上面
                        const loginForm = dom.getElementById('login-form') || dom.querySelector('form');
                        if (loginForm) {
                            loginForm.insertBefore(img, loginForm.firstChild);
                        }
                    }
                } catch (err) {
                    console.error("處理 Logo 預覽失敗", err);
                }
            } else if (logoRemoved) {
                const logoContainer = dom.getElementById('custom-brand-logo');
                if (logoContainer) {
                    logoContainer.innerHTML = '';
                }
            }

            if (!isMounted) return;

            // 防止 Quirks Mode，手動補回 DOCTYPE
            const finalHtmlString = `<!DOCTYPE html>\n${dom.documentElement.outerHTML}`;
            setPreviewHtml(finalHtmlString);
        };

        if (openTweakDialog) {
            generatePreview();
        }

        return () => {
            isMounted = false;
        };
    }, [tweakTitle, tweakMainTitle, tweakLogo, aiRawHtml, openTweakDialog, logoRemoved]);

    // 監聽是否有新的 HTML 檔案被上傳，若有則更新 aiRawHtml
    useEffect(() => {
        if (tweakNewHtmlFile) {
            const reader = new FileReader();
            reader.onload = (e) => {
                const newHtmlContent = e.target.result;
                setAiRawHtml(newHtmlContent); // 將 raw HTML 換成新上傳的內容
                // 從新的 HTML 中解析 title
                const parser = new DOMParser();
                const dom = parser.parseFromString(newHtmlContent, "text/html");
                setTweakTitle(dom.title || '登入');
                // [新增] 同時解析 H1 標題
                const mainTitleElement = dom.getElementById('custom-main-title');
                if (mainTitleElement) {
                    setTweakMainTitle(mainTitleElement.textContent);
                }
                // [新增] 同時解析 Logo 存在
                const logoContainer = dom.getElementById('custom-brand-logo');
                setHasExistingLogo(!!(logoContainer && logoContainer.querySelector('img')));
                setLogoRemoved(false); // 重置移除狀態
                setTweakLogo(null); // 清空舊 logo
            };
            reader.onerror = (err) => enqueueSnackbar(`讀取檔案失敗: ${err}`, { variant: 'error' });
            reader.readAsText(tweakNewHtmlFile);
        }
    }, [tweakNewHtmlFile]);

    // 載入 json & config
    const fetchPageOptions = async () => {
        setLoadingOptions(true);
        setLoadError(null);
        try {
            const accessToken = window.localStorage.getItem("accessToken");
            // 並行請求 config / pageOptions / domain list
            const [configRes, pagesRes, domainsRes] = await Promise.all([
                fetch('/api/trigger_page/config'),
                fetch('/api/trigger_page/get'),
                fetch('/api/domain/list', {
                    headers: { 'Authorization': `Bearer ${accessToken}` }
                })
            ]);

            if (!pagesRes.ok) {
                throw new Error('無法載入頁面列表');
            }

            const pagesData = await pagesRes.json();
            setPageOptions(pagesData);

            if (domainsRes.ok) {
                const domainsData = await domainsRes.json();
                setDomainList(domainsData.filter(d => d.is_active));
            } else {
                setDomainList([]);
            }

            if (configRes.ok) {
                const configData = await configRes.json();
                // 如果後端有回傳 triggerUrl 就用，否則 fallback 到預設 (window.location.origin + '/trigger')
                if (configData.triggerUrl) {
                    setTriggerBaseUrl(configData.triggerUrl);
                } else {
                    setTriggerBaseUrl(`${window.location.origin}/trigger`);
                }
                setEthanHosts(configData.ethanHosts || []);
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

    // 根據 page 綁定的 domain 決定 base URL
    const resolveBaseUrlForOption = (option) => {
        if (option && option.allowed_domain) {
            const proto = window.location.protocol || 'https:';
            return `${proto}//${option.allowed_domain}`;
        }
        return triggerBaseUrl || `${window.location.origin}/trigger`;
    };

    useEffect(() => {
        fetchPageOptions();
    }, []);

    const handleConfirm = () => {
        if (!selectedOption) {
            enqueueSnackbar('請先選擇一個選項', { variant: 'warning' });
            return;
        }
        // 根據選到的 page 找出對應 domain
        const selectedPage = pageOptions.find(o => o.value === selectedOption);
        const isBound = !!(selectedPage && selectedPage.allowed_domain);
        const defaultBase = triggerBaseUrl || `${window.location.origin}/trigger`;
        // 綁定頁面：base 用綁定 domain；未綁定頁面：base 用操作者選的鏡像網域
        // QR 圖網址一律跟 base 一致，讓「連結、QR 圖來源、QR 掃描後目標」三者同一個網域
        const baseUrl = isBound ? resolveBaseUrlForOption(selectedPage) : (selectedLinkBase || defaultBase);
        const qrBaseUrl = baseUrl;

        let urlSuffix = "";
        let qrSuffix = "";

        if (redirectOption === 'custom') {
            if (!customRedirectUrl) {
                enqueueSnackbar('請輸入自訂連結 URL', { variant: 'warning' });
                setOpenRedirectDialog(true);
                return;
            }
            urlSuffix = `?redirect_url=${encodeURIComponent(customRedirectUrl)}`;
            qrSuffix = `&redirect_url=${encodeURIComponent(customRedirectUrl)}`;
        } else if (redirectOption === 'password-wrong') {
            urlSuffix = `?redirect_url=password`;
            qrSuffix = `&redirect_url=password`;        
        } else if (redirectOption === 'self') {
            urlSuffix = `?redirect_url=self`;
            qrSuffix = `&redirect_url=self`;
        }

        setOutputTextUrl(`${baseUrl}/page/${selectedOption}/99999_99999${urlSuffix}`)
        setOutputTextQrcode(`${qrBaseUrl}/qrcode/${selectedOption}/uuid?uuid=99999_99999${qrSuffix}`);
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
    const handleOpenUploadDialog = async (option = null) => {
        if (option) {
            // [修改] 進入編輯模式，改為開啟 Tweak Dialog
            enqueueSnackbar('正在載入頁面原始碼...', { variant: 'info' });
            try {
                const accessToken = window.localStorage.getItem("accessToken");
                const response = await fetch(`/api/trigger_page/download?pageValue=${option.value}`, {
                    headers: { 'Authorization': `Bearer ${accessToken}` }
                });

                if (!response.ok) {
                    const errData = await response.json();
                    throw new Error(errData.detail || '無法下載頁面原始碼');
                }

                const htmlContent = await response.text();

                // 使用 DOMParser 提取現有 title
                const parser = new DOMParser();
                const dom = parser.parseFromString(htmlContent, "text/html");
                const existingTitle = dom.title || '登入';

                // [新增] 同時解析 H1 標題
                const mainTitleElement = dom.getElementById('custom-main-title');
                const existingMainTitle = mainTitleElement ? mainTitleElement.textContent : '';
                // [新增] 同時解析 Logo 存在
                const logoContainer = dom.getElementById('custom-brand-logo');
                const hasLogo = !!(logoContainer && logoContainer.querySelector('img'));


                // 設定 Tweak Dialog 的狀態
                setAiRawHtml(htmlContent);
                setPreviewHtml(htmlContent);
                setTweakPageLabel(option.label);
                setTweakPageValue(option.value);
                setTweakAllowedDomainId(option.allowed_domain_id ?? '');
                setTweakTitle(existingTitle);
                setTweakMainTitle(existingMainTitle);
                setTweakLogo(null);
                setTweakNewHtmlFile(null); // 清空
                setLogoRemoved(false);
                setHasExistingLogo(hasLogo);
                setTweakGenerationId(null); // 編輯模式沒有 generationId

                // 標記為編輯模式
                setEditMode(option.value);
                setOpenTweakDialog(true);

            } catch (err) {
                console.error("載入頁面失敗:", err);
                enqueueSnackbar(err.message, { variant: 'error' });
            }
        } else {
            // 舊的上傳檔案邏輯 (保留給未使用 AI 生成的管理者)
            setEditMode(null);
            setPageLabel('');
            setPageValue('');
            setOldPageValue('');
            setUploadAllowedDomainId('');
            setSelectedFile(null);
            setOpenUploadDialog(true);
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
        setCreateTemplateType('test');
        setCreateSvg('');
        setCreateAllowedDomainId('');
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
        setAiGenerationId(null);
        setUploadAllowedDomainId('');
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
        formData.append('allowedDomainId', uploadAllowedDomainId === '' ? '' : String(uploadAllowedDomainId));

        // 在"修改"模式下，檔案是可選的
        if (selectedFile) {
            formData.append('file', selectedFile);
        }

        // 若為 AI 生成的頁面，附上 generation_id 以便後端串接日誌
        if (aiGenerationId) {
            formData.append('generationId', aiGenerationId);
        }

        // 決定要呼叫哪個 API
        const isEdit = !!editMode;
        const apiUrl = isEdit ? '/api/trigger_page/update' : '/api/trigger_page/upload';

        try {
            const accessToken = window.localStorage.getItem("accessToken");
            const response = await fetch(apiUrl, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${accessToken}`
                },
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
        formData.append('allowedDomainId', createAllowedDomainId === '' ? '' : String(createAllowedDomainId));

        try {
            const accessToken = window.localStorage.getItem("accessToken");
            const response = await fetch('/api/trigger_page/create_page', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${accessToken}`
                },
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

    const handleOpenAiDialog = () => {
        setAiPrompt('');
        setAiRefUrl('');
        setAiImage(null);
        setAiPageType('field');
        setOpenAiDialog(true);
    };

    const handleCloseAiDialog = () => {
        if (generating) {
            if (window.confirm('AI頁面生成 正在執行中，關閉將會取消生成，確定要關閉嗎？')) {
                if (abortControllerRef.current) {
                    abortControllerRef.current.abort();
                }
                setOpenAiDialog(false);
                setAiProgress(null);
            }
        } else {
            setOpenAiDialog(false);
            setAiProgress(null);
        }
    };

    const handleGenerateWithAi = async () => {
        if (!aiPrompt) {
            enqueueSnackbar('請輸入提示詞 (Prompt)', { variant: 'warning' });
            return;
        }

        setGenerating(true);
        setAiProgress({ stage: 'starting', message: '準備中...' });

        const formData = new FormData();
        formData.append('prompt', aiPrompt);
        formData.append('pageType', aiPageType);
        formData.append('aiModel', aiModel);
        formData.append('useDesign', useDesign);
        if (aiRefUrl) formData.append('refUrl', aiRefUrl);
        if (aiImage) formData.append('image', aiImage);

        abortControllerRef.current = new AbortController();

        let endpoint = '/api/trigger_page/generate_with_ai_stream';

        try {
            const accessToken = window.localStorage.getItem("accessToken");
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${accessToken}`
                },
                body: formData,
                signal: abortControllerRef.current.signal
            });

            if (!response.ok) {
                const result = await response.json();
                throw new Error(result.detail || '生成失敗');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop(); // 保留不完整的部分

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const dataStr = line.slice(6);
                        if (!dataStr) continue;

                        const data = JSON.parse(dataStr);

                        if (data.type === 'progress') {
                            setAiProgress(data.data);
                        } else if (data.type === 'complete') {
                            setAiProgress(data.data);
                            const htmlContent = data.data.html;

                            // 保存原始 HTML，設定微調 Dialog 的預設值
                            setAiRawHtml(htmlContent);
                            setPreviewHtml(htmlContent);
                            setTweakGenerationId(data.data.generation_id || null);

                            const timestamp = new Date().getTime();
                            setTweakPageLabel(`AI 生成頁面 ${new Date().toLocaleTimeString()}`);
                            setTweakPageValue(`ai_${timestamp}`);
                            setTweakAllowedDomainId('');
                            setTweakTitle('登入');
                            setTweakLogo(null);

                            // [新增] 解析 HTML 內容以取得更精確的預設值
                            const parser = new DOMParser();
                            const dom = parser.parseFromString(htmlContent, "text/html");
                            const existingTitle = dom.title || '登入';
                            const mainTitleElement = dom.getElementById('custom-main-title');
                            const existingMainTitle = mainTitleElement ? mainTitleElement.textContent : '';
                            const logoContainer = dom.getElementById('custom-brand-logo');
                            const hasLogo = !!(logoContainer && logoContainer.querySelector('img'));

                            setTweakTitle(existingTitle);
                            setTweakMainTitle(existingMainTitle);

                            // 設定 Logo 相關狀態
                            setLogoRemoved(false);
                            setHasExistingLogo(hasLogo);


                            setOpenAiDialog(false);
                            setOpenTweakDialog(true);

                            enqueueSnackbar('AI 生成成功！請確認預覽並儲存頁面。', { variant: 'success' });
                        } else if (data.type === 'error') {
                            throw new Error(data.data.message);
                        }
                    }
                }
            }
        } catch (err) {
            if (err.name === 'AbortError') {
                console.log('AI生成頁面 已取消');
                enqueueSnackbar('AI生成頁面 已取消', { variant: 'info' });
            } else {
                console.error("AI生成頁面 失敗:", err);
                enqueueSnackbar(err.message, { variant: 'error' });
            }
        } finally {
            setGenerating(false);
            setAiProgress(null);
            abortControllerRef.current = null;
        }
    };

    const handleCloseTweakDialog = () => {
        setOpenTweakDialog(false);
        // 清空所有微調狀態
        setTweakLogo(null);
        setTweakMainTitle('');
        setTweakNewHtmlFile(null);
        setLogoRemoved(false);
        setHasExistingLogo(false);
    };

    const handleSaveTweak = async () => {
        if (!tweakPageLabel || !tweakPageValue) {
            enqueueSnackbar('請輸入網頁名稱和網址 ID', { variant: 'warning' });
            return;
        }

        try {
            // 利用最新的 previewHtml 來建立 File
            const blob = new Blob([previewHtml], { type: 'text/html;charset=utf-8' });
            const file = new File([blob], `${tweakPageValue}.html`, { type: 'text/html;charset=utf-8' });

            const formData = new FormData();
            const isEdit = !!editMode;

            formData.append('pageLabel', tweakPageLabel);
            formData.append('pageValue', tweakPageValue);
            formData.append('allowedDomainId', tweakAllowedDomainId === '' ? '' : String(tweakAllowedDomainId));
            formData.append('file', file);
            
            if (isEdit) {
                formData.append('oldPageValue', editMode);
            } else {
                formData.append('oldPageValue', '');
            }

            // 如果是 AI 新生成的，才帶上 generationId
            if (!isEdit && tweakGenerationId) {
                formData.append('generationId', tweakGenerationId);
            }

            const apiUrl = isEdit ? '/api/trigger_page/update' : '/api/trigger_page/upload';

            const accessToken = window.localStorage.getItem("accessToken");
            const response = await fetch(apiUrl, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${accessToken}`
                },
                body: formData,
            });

            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.detail || '儲存失敗');
            }

            enqueueSnackbar(isEdit ? '頁面修改成功！' : 'AI 頁面儲存成功！', { variant: 'success' });
            setOpenTweakDialog(false);
            fetchPageOptions();
            // 清除編輯模式
            setEditMode(null);

        } catch (err) {
            console.error("儲存失敗:", err);
            enqueueSnackbar(err.message, { variant: 'error' });
        }
    };

    // 監聽 beforeunload 以防止使用者在生成中意外離開
    useEffect(() => {
        const handleBeforeUnload = (e) => {
            if (generating) {
                e.preventDefault();
                e.returnValue = ''; // Chrome requires returnValue to be set
            }
        };

        window.addEventListener('beforeunload', handleBeforeUnload);

        return () => {
            window.removeEventListener('beforeunload', handleBeforeUnload);
        };
    }, [generating]);

    // [新增] 複製頁面處理函式
    const handleCopyPage = async (option) => {
        enqueueSnackbar('正在準備複製頁面...', { variant: 'info' });
        try {
            const accessToken = window.localStorage.getItem("accessToken");
            const response = await fetch(`/api/trigger_page/download?pageValue=${option.value}`, {
                headers: { 'Authorization': `Bearer ${accessToken}` }
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || '無法下載頁面原始碼');
            }

            const htmlContent = await response.text();

            const parser = new DOMParser();
            const dom = parser.parseFromString(htmlContent, "text/html");
            const existingTitle = dom.title || '登入';
            const mainTitleElement = dom.getElementById('custom-main-title');
            const existingMainTitle = mainTitleElement ? mainTitleElement.textContent : '';
            const logoContainer = dom.getElementById('custom-brand-logo');
            const hasLogo = !!(logoContainer && logoContainer.querySelector('img'));

            // 設定 Tweak Dialog 的狀態
            setAiRawHtml(htmlContent);
            setPreviewHtml(htmlContent);
            setTweakPageLabel(`${option.label} (副本)`);
            const timestamp = new Date().getTime();
            // 避免 value 變成 xxx_copy_123_copy_456
            const baseValue = option.value.replace(/_copy_\d+$/, '');
            setTweakPageValue(`${baseValue}_copy_${timestamp}`);
            setTweakAllowedDomainId(option.allowed_domain_id ?? '');
            setTweakTitle(existingTitle);
            setTweakMainTitle(existingMainTitle);
            setTweakLogo(null);
            setTweakNewHtmlFile(null);
            setTweakGenerationId(null);
            setLogoRemoved(false);
            setHasExistingLogo(hasLogo);

            // 複製不是編輯模式
            setEditMode(null);
            setOpenTweakDialog(true);

        } catch (err) {
            console.error("複製頁面失敗:", err);
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
            const accessToken = window.localStorage.getItem("accessToken");
            const response = await fetch('/api/trigger_page/delete', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${accessToken}`
                },
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

    const handleDownloadPage = async (option) => {
        try {
            const accessToken = window.localStorage.getItem("accessToken");
            // Use fetch to get the blob
            const response = await fetch(`/api/trigger_page/download?pageValue=${option.value}`, {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${accessToken}`
                }
            });

            if (!response.ok) {
                const result = await response.json();
                throw new Error(result.detail || '下載失敗');
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${option.value}.html`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            enqueueSnackbar('下載已開始', { variant: 'success' });

        } catch (err) {
            console.error("下載失敗:", err);
            enqueueSnackbar(err.message, { variant: 'error' });
        }
    };

    const handleOpenRedirectDialog = () => {
        setOpenRedirectDialog(true);
    };

    const handleCloseRedirectDialog = () => {
        setOpenRedirectDialog(false);
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
                                            網頁生成
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
                                            {(() => {
                                                // 按擁有者分組
                                                const groups = {};
                                                pageOptions.forEach((option) => {
                                                    const key = option.owner ?? '__system__';
                                                    if (!groups[key]) {
                                                        groups[key] = {
                                                            label: option.owner === null
                                                                ? '系統預設頁面'
                                                                : (option.owner_name || option.owner),
                                                            items: [],
                                                        };
                                                    }
                                                    groups[key].items.push(option);
                                                });

                                                // 排序：系統預設排最前面，其餘依擁有者名稱排序
                                                const sortedKeys = Object.keys(groups).sort((a, b) => {
                                                    if (a === '__system__') return -1;
                                                    if (b === '__system__') return 1;
                                                    return groups[a].label.localeCompare(groups[b].label);
                                                });

                                                return sortedKeys.map((ownerKey) => {
                                                    const group = groups[ownerKey];
                                                    const isExpanded = expandedOwners[ownerKey] ?? false; // 預設全部摺疊
                                                    // 若目前選取的選項在此分組內，強制展開
                                                    const hasSelected = group.items.some(o => o.value === selectedOption);

                                                    return (
                                                        <Accordion
                                                            key={ownerKey}
                                                            expanded={isExpanded || hasSelected}
                                                            onChange={() => setExpandedOwners(prev => ({
                                                                ...prev,
                                                                [ownerKey]: !(prev[ownerKey] ?? true),
                                                            }))}
                                                            disableGutters
                                                            elevation={0}
                                                            sx={{
                                                                border: '1px solid',
                                                                borderColor: 'divider',
                                                                borderRadius: '8px !important',
                                                                mb: 1,
                                                                '&:before': { display: 'none' },
                                                                overflow: 'hidden',
                                                            }}
                                                        >
                                                            <AccordionSummary
                                                                expandIcon={<ExpandMoreIcon />}
                                                                sx={{
                                                                    backgroundColor: ownerKey === '__system__'
                                                                        ? 'action.selected'
                                                                        : 'action.hover',
                                                                    borderRadius: 'inherit',
                                                                    minHeight: 44,
                                                                    '& .MuiAccordionSummary-content': { my: 0.5 },
                                                                }}
                                                            >
                                                                <Typography variant="subtitle2" fontWeight={600}>
                                                                    {group.label}
                                                                    <Typography
                                                                        component="span"
                                                                        variant="caption"
                                                                        color="text.secondary"
                                                                        sx={{ ml: 1 }}
                                                                    >
                                                                        ({group.items.length} 個頁面)
                                                                    </Typography>
                                                                </Typography>
                                                            </AccordionSummary>
                                                            <AccordionDetails sx={{ p: 1 }}>
                                                                <Stack spacing={1}>
                                                                    {group.items.map((option) => (
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
                                                                            {option.allowed_domain && (
                                                                                <Chip
                                                                                    label={option.allowed_domain}
                                                                                    size="small"
                                                                                    color="primary"
                                                                                    variant="outlined"
                                                                                    sx={{ mr: 1 }}
                                                                                />
                                                                            )}
                                                                            <Stack direction="row" spacing={0.5}>
                                                                                <Button
                                                                                    component={Link}
                                                                                    href={resolveBaseUrlForOption(option) + '/page/' + option.value + '/test'}
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
                                                                                    color="info"
                                                                                    onClick={(e) => { e.stopPropagation(); handleDownloadPage(option); }}
                                                                                    title="下載原始碼"
                                                                                >
                                                                                    <DownloadIcon fontSize="small" />
                                                                                </IconButton>
                                                                                <IconButton
                                                                                    size="small"
                                                                                    color="secondary"
                                                                                    onClick={(e) => { e.stopPropagation(); handleCopyPage(option); }}
                                                                                    title="複製"
                                                                                >
                                                                                    <FileCopyIcon fontSize="small" />
                                                                                </IconButton>
                                                                                {(() => {
                                                                                    const isSystemPage = option.owner === null;
                                                                                    const isOwner = user?.acct_uuid && user.acct_uuid === option.owner;
                                                                                    const canEdit = !isSystemPage && (isAdmin || isOwner);
                                                                                    return canEdit && (
                                                                                        <>
                                                                                            <IconButton
                                                                                                size="small"
                                                                                                color="primary"
                                                                                                onClick={(e) => { e.stopPropagation(); handleOpenUploadDialog(option); }}
                                                                                                title="編輯"
                                                                                            >
                                                                                                <EditIcon fontSize="small" />
                                                                                            </IconButton>
                                                                                            <IconButton
                                                                                                size="small"
                                                                                                color="error"
                                                                                                onClick={(e) => { e.stopPropagation(); handleOpenDeleteDialog(option); }}
                                                                                                title="刪除"
                                                                                            >
                                                                                                <DeleteIcon fontSize="small" />
                                                                                            </IconButton>
                                                                                        </>
                                                                                    );
                                                                                })()}
                                                                            </Stack>
                                                                        </Paper>
                                                                    ))}
                                                                </Stack>
                                                            </AccordionDetails>
                                                        </Accordion>
                                                    );
                                                });
                                            })()}
                                        </RadioGroup>
                                    </FormControl>
                                )}

                                <Box sx={{ mb: 1 }}>
                                    <Typography variant="body2" color="text.secondary">
                                        目前觸發後頁面：
                                        {redirectOption === 'warning' ? (
                                            <Link href={`${baseUrl}/warning`} target="_blank" rel="noopener noreferrer">
                                                警告頁面
                                            </Link>
                                        ) : redirectOption === 'self' ? (
                                            <span style={{ fontWeight: 'bold' }}>停留在目前頁面</span>
                                        ) : redirectOption === 'password-wrong' ? (
                                            <Link href={`${baseUrl}/password-wrong`} target="_blank" rel="noopener noreferrer">
                                                密碼錯誤頁面
                                            </Link>
                                        ) : (
                                            <Link href={customRedirectUrl} target="_blank" rel="noopener noreferrer">
                                                {customRedirectUrl || '尚未設定 URL'}
                                            </Link>
                                        )}
                                    </Typography>
                                </Box>
                                {ethanHosts.length > 0 && (
                                    <FormControl size="small"
                                        disabled={!!(pageOptions.find(o => o.value === selectedOption)?.allowed_domain)}
                                        sx={{ minWidth: 280 }}
                                    >
                                        <InputLabel id="link-base-label">產生連結使用的網域</InputLabel>
                                        <Select
                                            labelId="link-base-label"
                                            label="產生連結使用的網域"
                                            value={selectedLinkBase}
                                            onChange={(e) => setSelectedLinkBase(e.target.value)}
                                        >
                                            <MenuItem value=""><em>預設 ({triggerBaseUrl})</em></MenuItem>
                                            {ethanHosts.map((h) => (
                                                <MenuItem key={h} value={h}>{h}</MenuItem>
                                            ))}
                                        </Select>
                                        <Typography variant="caption" color="text.secondary" sx={{ ml: 1.5, mt: 0.5 }}>
                                            已綁定網域的頁面不受此設定影響
                                        </Typography>
                                    </FormControl>
                                )}
                                <Box sx={{ display: 'flex', gap: 2 }}>
                                    <Button
                                        variant="outlined"
                                        size="large"
                                        color="secondary"
                                        onClick={handleOpenRedirectDialog}
                                    >
                                        設定觸發後頁面
                                    </Button>
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
                                                // 跟「產生連結使用的網域」下拉接在一起；未選則用預設 base
                                                const fromUrlBase = selectedLinkBase || baseUrl;
                                                setOutputTextUrl(`${fromUrlBase}/page/from-url/99999_99999?url=${encodeURIComponent(directUrlInput)}`)
                                                setOutputTextQrcode(`${fromUrlBase}/qrcode/from-url/uuid?uuid=99999_99999&url=${encodeURIComponent(directUrlInput)}`);
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
                        <FormControl fullWidth margin="dense">
                            <InputLabel id="upload-domain-label">綁定網域 (Domain)</InputLabel>
                            <Select
                                labelId="upload-domain-label"
                                label="綁定網域 (Domain)"
                                value={uploadAllowedDomainId}
                                onChange={(e) => setUploadAllowedDomainId(e.target.value)}
                            >
                                <MenuItem value="">
                                    <em>使用預設 (TRIGGER_APP_URL)</em>
                                </MenuItem>
                                {domainList.map((d) => (
                                    <MenuItem key={d.id} value={d.id}>{d.label || d.domain} ({d.domain})</MenuItem>
                                ))}
                            </Select>
                            <Typography variant="caption" color="text.secondary" sx={{ ml: 1.5, mt: 0.5 }}>
                                綁定後，此頁面只接受該網域的請求；其他網域訪問會 404
                            </Typography>
                        </FormControl>
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
                        <FormControl fullWidth>
                            <InputLabel id="create-domain-label">綁定網域 (Domain)</InputLabel>
                            <Select
                                labelId="create-domain-label"
                                label="綁定網域 (Domain)"
                                value={createAllowedDomainId}
                                onChange={(e) => setCreateAllowedDomainId(e.target.value)}
                            >
                                <MenuItem value="">
                                    <em>使用預設 (TRIGGER_APP_URL)</em>
                                </MenuItem>
                                {domainList.map((d) => (
                                    <MenuItem key={d.id} value={d.id}>{d.label || d.domain} ({d.domain})</MenuItem>
                                ))}
                            </Select>
                            <Typography variant="caption" color="text.secondary" sx={{ ml: 1.5, mt: 0.5 }}>
                                綁定後，此頁面只接受該網域的請求；其他網域訪問會 404
                            </Typography>
                        </FormControl>
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
            {/* 設定觸發後頁面 Dialog */}
            <Dialog open={openRedirectDialog} onClose={handleCloseRedirectDialog} fullWidth maxWidth="xs">
                <DialogTitle>設定觸發後頁面</DialogTitle>
                <DialogContent>
                    <FormControl component="fieldset" fullWidth sx={{ mt: 1 }}>
                        <RadioGroup
                            aria-label="redirect-option"
                            name="redirect-option"
                            value={redirectOption}
                            onChange={(e) => setRedirectOption(e.target.value)}
                        >
                            <FormControlLabel
                                value="warning"
                                control={<Radio />}
                                label="警告頁面 (預設)"
                            />
                            {redirectOption === 'warning' && (
                                <Box sx={{ ml: 4, mb: 2 }}>
                                    <Button
                                        variant="outlined"
                                        size="small"
                                        onClick={() => window.open(`${baseUrl}/warning`, '_blank')}
                                    >
                                        預覽警告頁面
                                    </Button>
                                </Box>
                            )}

                            <FormControlLabel
                                value="password-wrong"
                                control={<Radio />}
                                label="密碼錯誤警告頁面"
                            />
                            {redirectOption === 'password-wrong' && (
                                <Box sx={{ ml: 4, mb: 2 }}>
                                    <Button
                                        variant="outlined"
                                        size="small"
                                        onClick={() => window.open(`${baseUrl}/password-wrong`, '_blank')}
                                    >
                                        預覽密碼錯誤警告頁面
                                    </Button>
                                </Box>
                            )}

                            <FormControlLabel
                                value="custom"
                                control={<Radio />}
                                label="自訂連結"
                            />
                            {redirectOption === 'custom' && (
                                <Box sx={{ ml: 4, mb: 1 }}>
                                    <TextField
                                        label="請輸入 URL"
                                        placeholder="https://example.com"
                                        fullWidth
                                        size="small"
                                        value={customRedirectUrl}
                                        onChange={(e) => setCustomRedirectUrl(e.target.value)}
                                        error={redirectOption === 'custom' && !customRedirectUrl}
                                        helperText={redirectOption === 'custom' && !customRedirectUrl ? "必須填寫網址" : ""}
                                    />
                                </Box>
                            )}

                            <FormControlLabel
                                value="self"
                                control={<Radio />}
                                label="停留在目前頁面"
                            />
                        </RadioGroup>
                    </FormControl>
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleCloseRedirectDialog}>確定</Button>
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

                        <FormControl component="fieldset">
                            <RadioGroup
                                row
                                aria-label="ai-model"
                                name="ai-model"
                                value={aiModel}
                                onChange={(e) => {
                                    const newModel = e.target.value;
                                    setAiModel(newModel);
                                    // 切換到不支援圖片的模型時，自動清掉已選的圖以免使用者誤會
                                    if (!VISION_MODELS.includes(newModel) && aiImage) {
                                        setAiImage(null);
                                        enqueueSnackbar('已切換至不支援圖片的模型，附圖已自動移除', { variant: 'info' });
                                    }
                                }}
                            >
                                <FormControlLabel value="gemini" control={<Radio />} label="Gemini (預設)" />
                                <FormControlLabel value="gpt_terra" control={<Radio />} label="GPT terra(liteLLM)" />
                                <FormControlLabel value="gpt_sol" control={<Radio />} label="GPT sol(liteLLM)" />
                                <FormControlLabel value="litellm" control={<Radio />} label="LiteLLM" />
                                <FormControlLabel value="gchat_gemma431b" control={<Radio />} label="GChat (Gemma-4-31B)" disabled />
                                <FormControlLabel value="gchat_gptoss" control={<Radio />} label="GChat (GPT-OSS 20B)" />
                                <FormControlLabel value="gchat_gemma12b" control={<Radio />} label="GChat (Gemma-4-12B)" />
                                <FormControlLabel value="gchat_gpt54mini" control={<Radio />} label="GChat (gpt-5.4-mini)" />
                                <FormControlLabel value="gchat_gpt54" control={<Radio />} label="GChat (gpt-5.4)" />
                                <FormControlLabel value="gchat_gpt55" control={<Radio />} label="GChat (gpt-5.5)" />
                            </RadioGroup>
                        </FormControl>

                        <FormControl component="fieldset">
                            <Typography variant="body2" color="text.secondary" gutterBottom>網頁類型：</Typography>
                            <RadioGroup
                                row
                                aria-label="ai-page-type"
                                name="ai-page-type"
                                value={aiPageType}
                                onChange={(e) => setAiPageType(e.target.value)}
                            >
                                <FormControlLabel
                                    value="field"
                                    control={<Radio disabled={generating} />}
                                    label="欄位（填入資訊後觸發）"
                                />
                                <FormControlLabel
                                    value="download"
                                    control={<Radio disabled={generating} />}
                                    label="下載按鍵（點擊後觸發）"
                                />
                            </RadioGroup>
                        </FormControl>

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
                            helperText="提供網址可協助 AI 更精確還原該網站的文字內容"
                        />

                        {aiRefUrl && (
                            <FormControlLabel
                                control={
                                    <Switch
                                        checked={useDesign}
                                        onChange={(e) => setUseDesign(e.target.checked)}
                                        disabled={generating}
                                        color="primary"
                                    />
                                }
                                label={
                                    <Box>
                                        <Typography variant="body1">啟用自動化設計解析 (DESIGN.md)</Typography>
                                        <Typography variant="caption" color="text.secondary">開啟後將啟動系統爬蟲擷取目標網址的色系、字體與圓角外觀。會需要較長的處理時間。</Typography>
                                    </Box>
                                }
                                sx={{ ml: 0, '& .MuiFormControlLabel-label': { ml: 1 } }}
                            />
                        )}

                        <Button
                            variant="outlined"
                            component="label"
                            disabled={generating || !supportsVision}
                            startIcon={<UploadIcon />}
                            fullWidth
                        >
                            上傳參考圖片 (Optional)
                            <input
                                type="file"
                                hidden
                                accept="image/*"
                                onChange={(e) => {
                                    if (e.target.files && e.target.files.length > 0) {
                                        setAiImage(e.target.files[0]);
                                    }
                                }}
                            />
                        </Button>
                        {!supportsVision && (
                            <Typography variant="caption" color="text.secondary" sx={{ mt: -1, ml: 1 }}>
                                此模型不支援圖片輸入（僅 Gemini / GPT / GChat (Gemma-4-31B, gpt-5.5) 可用）
                            </Typography>
                        )}
                        {aiImage && (
                            <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mt: 1, p: 1, border: '1px solid #ddd', borderRadius: 1 }}>
                                <Typography variant="body2" noWrap sx={{ maxWidth: '80%' }}>
                                    已選擇: {aiImage.name}
                                </Typography>
                                <IconButton size="small" onClick={() => setAiImage(null)} disabled={generating}>
                                    <CloseIcon fontSize="small" />
                                </IconButton>
                            </Stack>
                        )}

                        {generating && aiProgress && (
                            <Box sx={{ mt: 2, p: 2, border: '1px solid #eee', borderRadius: 2, backgroundColor: '#fafafa' }}>
                                <Stepper
                                    activeStep={
                                        aiProgress.stage === 'extracting' ? 0 :
                                            aiProgress.stage === 'extracted' ? 1 :
                                                aiProgress.stage === 'generating' ? 1 :
                                                    aiProgress.stage === 'done' ? 2 : 0
                                    }
                                    alternativeLabel
                                >
                                    <Step completed={['extracted', 'generating', 'done'].includes(aiProgress.stage)}>
                                        <StepLabel>解析目標網站</StepLabel>
                                    </Step>
                                    <Step completed={['done'].includes(aiProgress.stage)}>
                                        <StepLabel>AI 生成頁面</StepLabel>
                                    </Step>
                                    <Step completed={aiProgress.stage === 'done'}>
                                        <StepLabel>完成</StepLabel>
                                    </Step>
                                </Stepper>

                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', mt: 3, gap: 1.5 }}>
                                    {aiProgress.stage !== 'done' && <CircularProgress size={20} />}
                                    <Typography variant="body2" color="text.secondary">
                                        {aiProgress.message}
                                    </Typography>
                                </Box>
                            </Box>
                        )}
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

            {/* AI 生成網頁微調與儲存 Dialog */}
            <Dialog open={openTweakDialog} onClose={handleCloseTweakDialog} fullWidth maxWidth="md">
                <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    AI 生成頁面微調與儲存
                    <IconButton onClick={handleCloseTweakDialog} edge="end">
                        <CloseIcon />
                    </IconButton>
                </DialogTitle>
                <DialogContent>
                    <Grid container spacing={3} sx={{ pt: 1 }}>
                        <Grid item xs={12} md={5}>
                            <Stack spacing={2}>
                                <Typography variant="subtitle2" color="text.secondary">頁面基礎資訊</Typography>
                                <TextField
                                    required
                                    label="名稱"
                                    value={tweakPageLabel}
                                    onChange={(e) => setTweakPageLabel(e.target.value)}
                                    helperText="顯示在選項中的名稱"
                                    fullWidth
                                    size="small"
                                />
                                <TextField
                                    required
                                    label="網址 ID"
                                    value={tweakPageValue}
                                    onChange={(e) => setTweakPageValue(e.target.value.toLowerCase().trim())}
                                    helperText="用於 URL 的識別碼"
                                    fullWidth
                                    size="small"
                                />
                                <FormControl fullWidth size="small">
                                    <InputLabel id="tweak-domain-label">綁定網域 (Domain)</InputLabel>
                                    <Select
                                        labelId="tweak-domain-label"
                                        label="綁定網域 (Domain)"
                                        value={tweakAllowedDomainId}
                                        onChange={(e) => setTweakAllowedDomainId(e.target.value)}
                                    >
                                        <MenuItem value="">
                                            <em>使用預設 (TRIGGER_APP_URL)</em>
                                        </MenuItem>
                                        {domainList.map((d) => (
                                            <MenuItem key={d.id} value={d.id}>{d.label || d.domain} ({d.domain})</MenuItem>
                                        ))}
                                    </Select>
                                </FormControl>
                                
                                <Divider sx={{ my: 1 }} />

                                <Typography variant="subtitle2" color="text.secondary">內容微調</Typography>
                                <TextField
                                    label="網頁標題 (Title)"
                                    value={tweakTitle}
                                    onChange={(e) => setTweakTitle(e.target.value)}
                                    helperText="瀏覽器分頁上顯示的文字"
                                    fullWidth
                                    size="small"
                                />
                                <TextField
                                    label="頁面主標題 (H1)"
                                    value={tweakMainTitle}
                                    onChange={(e) => setTweakMainTitle(e.target.value)}
                                    helperText="頁面內容中的主要標題"
                                    fullWidth
                                    size="small"
                                />
                                <Button
                                    variant="outlined"
                                    component="label"
                                    startIcon={<UploadIcon />}
                                    fullWidth
                                >
                                    上傳自訂圖標 (Logo)
                                    <input
                                        type="file"
                                        hidden
                                        accept="image/png, image/jpeg, image/webp, image/svg+xml"
                                        onChange={(e) => {
                                            if (e.target.files && e.target.files.length > 0) {
                                                const file = e.target.files[0];
                                                setTweakLogo(file);
                                                // 當上傳新檔案時，取消"移除"狀態
                                                setLogoRemoved(false);
                                            }
                                        }}
                                    />
                                </Button>
                                { (tweakLogo || (hasExistingLogo && !logoRemoved)) && (
                                    <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mt: 1, p: 1, border: '1px solid #ddd', borderRadius: 1 }}>
                                        <Typography variant="body2" noWrap sx={{ maxWidth: '80%' }}>
                                            {tweakLogo ? `已選擇: ${tweakLogo.name}` : '目前頁面包含圖標'}
                                        </Typography>
                                        <IconButton size="small" onClick={() => { setTweakLogo(null); setLogoRemoved(true); }} title="移除圖標">
                                            <CloseIcon fontSize="small" />
                                        </IconButton>
                                    </Stack>
                                )}
                                
                                {editMode && (
                                    <>
                                    <Divider sx={{ my: 1 }} />
                                    <Button
                                        variant="outlined"
                                        color="secondary"
                                        component="label"
                                        startIcon={<UploadIcon />}
                                        fullWidth
                                    >
                                        上傳新 HTML 檔案覆蓋
                                        <input
                                            type="file"
                                            hidden
                                            accept=".html"
                                            onChange={(e) => {
                                                if (e.target.files && e.target.files.length > 0) {
                                                    setTweakNewHtmlFile(e.target.files[0]);
                                                }
                                            }}
                                        />
                                    </Button>
                                    {tweakNewHtmlFile && <Typography variant="caption" color="text.secondary">已選擇: {tweakNewHtmlFile.name}</Typography>}
                                    </>
                                )}

                            </Stack>
                        </Grid>
                        <Grid item xs={12} md={7}>
                            <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>即時預覽</Typography>
                            <Box sx={{
                                border: '1px solid #ccc',
                                borderRadius: 1,
                                height: '500px',
                                overflow: 'hidden',
                                position: 'relative'
                            }}>
                                <iframe
                                    srcDoc={previewHtml}
                                    title="Live Preview"
                                    style={{ width: '100%', height: '100%', border: 'none', backgroundColor: '#fff' }}
                                />
                            </Box>
                        </Grid>
                    </Grid>
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleCloseTweakDialog}>取消</Button>
                    <Button onClick={handleSaveTweak} variant="contained" color="primary">
                        確認並儲存
                    </Button>
                </DialogActions>
            </Dialog>
        </>
    );
};

export default CreateUrl;
