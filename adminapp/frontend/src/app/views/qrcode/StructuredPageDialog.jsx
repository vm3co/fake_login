import { useEffect, useRef, useState } from 'react';
import { useSnackbar } from 'notistack';
import {
    Alert,
    Box,
    Button,
    Checkbox,
    CircularProgress,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Divider,
    FormControl,
    FormControlLabel,
    Grid,
    IconButton,
    InputLabel,
    MenuItem,
    Paper,
    Radio,
    RadioGroup,
    Select,
    Stack,
    TextField,
    Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import CloseIcon from '@mui/icons-material/Close';
import DeleteIcon from '@mui/icons-material/Delete';
import UploadIcon from '@mui/icons-material/Upload';

import {
    applyFieldType,
    buildStructuredPreview,
    createStructuredField,
    createStructuredSpec,
    exampleForField,
    FIELD_TYPES,
    MASK_MODES,
    MAX_STRUCTURED_FIELDS,
    updateStructuredHtml,
    validateStructuredDraft,
} from './structuredPageUtils';

const VISION_MODELS = ['gemini', 'gpt_terra', 'gpt_sol', 'gchat_gpt55', 'gchat_gpt54', 'gchat_gpt54mini', 'gchat_gemma12b'];
const MODEL_OPTIONS = [
    ['gemini', 'Gemini'],
    ['gpt_terra', 'GPT terra (LiteLLM)'],
    ['gpt_sol', 'GPT sol (LiteLLM)'],
    ['litellm', 'LiteLLM'],
    ['gchat_gptoss', 'GChat (GPT-OSS 20B)'],
    ['gchat_gemma12b', 'GChat (Gemma-4-12B)'],
    ['gchat_gpt54mini', 'GChat (gpt-5.4-mini)'],
    ['gchat_gpt54', 'GChat (gpt-5.4)'],
    ['gchat_gpt55', 'GChat (gpt-5.5)'],
];

const compressImageToDataUrl = (file, maxWidth = 300, maxHeight = 300) => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
        const image = new Image();
        image.onload = () => {
            const scale = Math.min(1, maxWidth / image.width, maxHeight / image.height);
            const canvas = document.createElement('canvas');
            canvas.width = Math.max(1, Math.round(image.width * scale));
            canvas.height = Math.max(1, Math.round(image.height * scale));
            const context = canvas.getContext('2d');
            context.drawImage(image, 0, 0, canvas.width, canvas.height);
            resolve(canvas.toDataURL(file.type, 0.8));
        };
        image.onerror = reject;
        image.src = reader.result;
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
});

const parseSseChunk = (buffer) => {
    const events = buffer.split('\n\n');
    return { complete: events.pop(), events };
};

const draftSnapshot = ({
    pageLabel,
    pageValue,
    allowedDomainId,
    spec,
    templateType,
    backgroundColor,
    backgroundImage,
    logoData,
    sourceHasUploadLogo,
}) => JSON.stringify({
    pageLabel: pageLabel.trim(),
    pageValue: pageValue.trim(),
    allowedDomainId: allowedDomainId === '' ? '' : String(allowedDomainId),
    pageTitle: spec.page_title,
    mainTitle: spec.main_title,
    description: spec.description,
    submitText: spec.submit_text,
    logoMode: spec.logo_mode,
    logoData: logoData || null,
    sourceHasUploadLogo: Boolean(sourceHasUploadLogo),
    templateType,
    backgroundColor,
    backgroundImage,
    fields: spec.fields.map((field) => ({
        id: field.id,
        label: field.label,
        type: field.type,
        required: field.required,
        mask_mode: field.mask_mode,
        keep_chars: field.keep_chars ?? null,
        custom_rule: field.custom_rule || '',
        validation_pattern: field.validation_pattern || '',
    })),
});

const StructuredPageDialog = ({
    open,
    mode,
    initialData,
    domainList,
    onClose,
    onSaved,
    onAutoSaved,
}) => {
    const { enqueueSnackbar } = useSnackbar();
    const isAi = mode === 'ai';
    const isEdit = mode === 'edit';
    const isCopy = mode === 'copy';
    const abortControllerRef = useRef(null);
    const fieldNameRefs = useRef(new Map());
    const pageValueCheckRef = useRef(0);

    const [pageLabel, setPageLabel] = useState('');
    const [pageValue, setPageValue] = useState('');
    const [allowedDomainId, setAllowedDomainId] = useState('');
    const [spec, setSpec] = useState(() => createStructuredSpec(isAi ? 'ai' : 'none'));
    const [revision, setRevision] = useState(1);
    const [sourceHtml, setSourceHtml] = useState('');
    const [previewHtml, setPreviewHtml] = useState('');
    const [templateType, setTemplateType] = useState('classic');
    const [backgroundColor, setBackgroundColor] = useState('#edf2ef');
    const [backgroundImage, setBackgroundImage] = useState('');
    const [stylePrompt, setStylePrompt] = useState('');
    const [model, setModel] = useState('gpt_terra');
    const [referenceImage, setReferenceImage] = useState(null);
    const [logoFile, setLogoFile] = useState(null);
    const [logoData, setLogoData] = useState(null);
    const [sourceHasUploadLogo, setSourceHasUploadLogo] = useState(false);
    const [generationId, setGenerationId] = useState(null);
    const [generating, setGenerating] = useState(false);
    const [saving, setSaving] = useState(false);
    const [progress, setProgress] = useState('');
    const [pageValueStatus, setPageValueStatus] = useState({ state: 'idle', message: '' });
    const [previewKey, setPreviewKey] = useState(0);
    const [persistedPageValue, setPersistedPageValue] = useState(null);
    const [persistedDraftSnapshot, setPersistedDraftSnapshot] = useState('');

    const effectiveEdit = isEdit || Boolean(persistedPageValue);
    const currentPersistedPageValue = persistedPageValue || initialData?.pageValue || '';

    useEffect(() => {
        if (!open) return;
        const defaultSpec = createStructuredSpec(isAi ? 'ai' : 'none');
        setPageLabel(initialData?.pageLabel || '');
        setPageValue(initialData?.pageValue || '');
        setAllowedDomainId(initialData?.allowedDomainId ?? '');
        setSpec(initialData?.pageSpec ? structuredClone(initialData.pageSpec) : defaultSpec);
        setRevision(initialData?.specRevision || 1);
        setSourceHtml(initialData?.html || '');
        if (initialData?.html) {
            const document = new DOMParser().parseFromString(initialData.html, 'text/html');
            setSourceHasUploadLogo(
                initialData?.pageSpec?.logo_mode === 'upload'
                && !!document.querySelector('#custom-brand-logo img')
            );
        } else {
            setSourceHasUploadLogo(false);
        }
        setPreviewHtml(initialData?.html || buildStructuredPreview(defaultSpec));
        setTemplateType('classic');
        setBackgroundColor('#edf2ef');
        setBackgroundImage('');
        setStylePrompt('');
        setReferenceImage(null);
        setLogoFile(null);
        setLogoData(null);
        setGenerationId(null);
        setProgress('');
        setPageValueStatus({ state: 'idle', message: '' });
        setPreviewKey(0);
        setPersistedPageValue(isEdit ? (initialData?.pageValue || null) : null);
        setPersistedDraftSnapshot(initialData?.pageSpec ? draftSnapshot({
            pageLabel: initialData.pageLabel || '',
            pageValue: initialData.pageValue || '',
            allowedDomainId: initialData.allowedDomainId ?? '',
            spec: initialData.pageSpec,
            templateType: 'classic',
            backgroundColor: '#edf2ef',
            backgroundImage: '',
            logoData: null,
            sourceHasUploadLogo: initialData.pageSpec.logo_mode === 'upload'
                && Boolean(new DOMParser().parseFromString(initialData.html || '', 'text/html').querySelector('#custom-brand-logo img')),
        }) : '');
    }, [open, initialData, isAi, isEdit]);

    useEffect(() => {
        if (!open) return undefined;
        const candidate = pageValue.trim();
        if (!candidate) {
            setPageValueStatus({
                state: 'idle',
                message: effectiveEdit ? '留空會保留目前網址 ID' : '留空會在儲存時自動產生',
            });
            return undefined;
        }
        if (!/^[a-z0-9_]+$/.test(candidate)) {
            setPageValueStatus({ state: 'invalid', message: '只能包含小寫字母、數字和底線' });
            return undefined;
        }

        const controller = new AbortController();
        const checkSequence = ++pageValueCheckRef.current;
        const timer = window.setTimeout(async () => {
            setPageValueStatus({ state: 'checking', message: '正在檢查網址 ID...' });
            try {
                const params = new URLSearchParams({ pageValue: candidate });
                if (effectiveEdit && currentPersistedPageValue) params.set('currentPageValue', currentPersistedPageValue);
                const response = await fetch(`/api/trigger_page/structured/page-value-availability?${params}`, {
                    headers: { Authorization: `Bearer ${window.localStorage.getItem('accessToken')}` },
                    signal: controller.signal,
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || '無法檢查網址 ID');
                if (checkSequence !== pageValueCheckRef.current) return;
                setPageValueStatus(result.available
                    ? { state: 'available', message: '網址 ID 可使用' }
                    : { state: 'unavailable', message: '網址 ID 已被使用' });
            } catch (error) {
                if (error.name !== 'AbortError' && checkSequence === pageValueCheckRef.current) {
                    setPageValueStatus({ state: 'error', message: error.message });
                }
            }
        }, 350);
        return () => {
            pageValueCheckRef.current += 1;
            window.clearTimeout(timer);
            controller.abort();
        };
    }, [open, pageValue, effectiveEdit, currentPersistedPageValue]);

    const confirmPageValueAvailable = async () => {
        const candidate = pageValue.trim();
        if (!candidate) return true;
        if (!/^[a-z0-9_]+$/.test(candidate)) {
            enqueueSnackbar('網址 ID 只能包含小寫字母、數字和底線', { variant: 'warning' });
            return false;
        }
        const params = new URLSearchParams({ pageValue: candidate });
        if (effectiveEdit && currentPersistedPageValue) params.set('currentPageValue', currentPersistedPageValue);
        try {
            const response = await fetch(`/api/trigger_page/structured/page-value-availability?${params}`, {
                headers: { Authorization: `Bearer ${window.localStorage.getItem('accessToken')}` },
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || '無法檢查網址 ID');
            if (!result.available) {
                setPageValueStatus({ state: 'unavailable', message: '網址 ID 已被使用' });
                enqueueSnackbar('網址 ID 已被使用，請更換後再試', { variant: 'warning' });
                return false;
            }
            setPageValueStatus({ state: 'available', message: '網址 ID 可使用' });
            return true;
        } catch (error) {
            setPageValueStatus({ state: 'error', message: error.message });
            enqueueSnackbar(error.message, { variant: 'error' });
            return false;
        }
    };

    useEffect(() => {
        if (!open) return;
        try {
            if (sourceHtml) {
                const nextRevision = effectiveEdit ? revision + 1 : 1;
                setPreviewHtml(updateStructuredHtml(sourceHtml, spec, nextRevision, logoData));
            } else {
                setPreviewHtml(buildStructuredPreview(spec, logoData));
            }
        } catch (error) {
            setProgress(error.message);
        }
    }, [open, sourceHtml, spec, revision, effectiveEdit, logoData]);

    const autoSaveGeneratedPage = async (html, normalizedSpec, generatedId) => {
        setSaving(true);
        try {
            const body = new FormData();
            const isExistingPage = Boolean(persistedPageValue);
            const nextRevision = isExistingPage ? revision + 1 : 1;
            const finalHtml = updateStructuredHtml(html, normalizedSpec, nextRevision, logoData);
            body.append('pageLabel', pageLabel.trim());
            body.append('pageValue', pageValue.trim());
            body.append('allowedDomainId', allowedDomainId === '' ? '' : String(allowedDomainId));
            body.append('pageSpec', JSON.stringify(normalizedSpec));
            body.append('file', new File([finalHtml], `${pageValue.trim() || persistedPageValue || 'structured-page'}.html`, { type: 'text/html;charset=utf-8' }));

            if (isExistingPage) {
                body.append('oldPageValue', persistedPageValue);
                body.append('specRevision', String(revision));
            } else {
                body.append('source', 'ai');
                body.append('generationId', generatedId);
            }

            const response = await fetch(
                isExistingPage ? '/api/trigger_page/structured/update' : '/api/trigger_page/structured/create',
                {
                method: 'POST',
                headers: { Authorization: `Bearer ${window.localStorage.getItem('accessToken')}` },
                body,
                },
            );
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || '自動儲存失敗');

            setPageValue(result.pageValue);
            setPersistedPageValue(result.pageValue);
            setRevision(result.specRevision || 1);
            setSpec(result.pageSpec || normalizedSpec);
            setSourceHtml(finalHtml);
            setPreviewHtml(finalHtml);
            setPreviewKey((current) => current + 1);
            setGenerationId(null);
            setProgress(`生成完成，已自動${isExistingPage ? '更新' : '儲存'}（網址 ID：${result.pageValue}）`);
            setPersistedDraftSnapshot(draftSnapshot({
                pageLabel: pageLabel.trim(),
                pageValue: result.pageValue,
                allowedDomainId,
                spec: result.pageSpec || normalizedSpec,
                templateType,
                backgroundColor,
                backgroundImage,
                logoData,
                sourceHasUploadLogo: Boolean(logoData) || sourceHasUploadLogo,
            }));
            enqueueSnackbar(`AI 頁面已自動${isExistingPage ? '更新' : '儲存'}（網址 ID：${result.pageValue}）`, { variant: 'success' });
            onAutoSaved?.();
            onClose();
            return result;
        } finally {
            setSaving(false);
        }
    };

    useEffect(() => () => abortControllerRef.current?.abort(), []);

    const updateField = (index, patch) => {
        setSpec((current) => ({
            ...current,
            fields: current.fields.map((field, fieldIndex) => fieldIndex === index ? { ...field, ...patch } : field),
        }));
    };

    const changeFieldType = (index, nextType) => {
        const field = spec.fields[index];
        if (field.type === 'custom' && nextType !== 'custom') {
            const confirmed = window.confirm('此欄位為 AI 特殊指定內容。儲存轉換後，無法透過欄位編輯器恢復原特殊規則。確定轉換嗎？');
            if (!confirmed) return;
        }
        setSpec((current) => ({
            ...current,
            fields: current.fields.map((item, fieldIndex) => fieldIndex === index ? applyFieldType(item, nextType) : item),
        }));
    };

    const addField = () => {
        if (spec.fields.length >= MAX_STRUCTURED_FIELDS) return;
        const nextField = createStructuredField();
        setSpec((current) => ({ ...current, fields: [...current.fields, nextField] }));
        window.requestAnimationFrame(() => {
            const input = fieldNameRefs.current.get(nextField.id);
            input?.focus();
            input?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        });
    };

    const removeField = (index) => {
        if (spec.fields.length <= 1) return;
        const field = spec.fields[index];
        if (field.type === 'custom') {
            const confirmed = window.confirm('此欄位為 AI 特殊指定內容。儲存刪除後，無法透過欄位編輯器重新新增相同類型。確定移除？');
            if (!confirmed) return;
        }
        setSpec((current) => ({
            ...current,
            fields: current.fields.filter((_, fieldIndex) => fieldIndex !== index),
        }));
    };

    const moveField = (index, offset) => {
        const nextIndex = index + offset;
        if (nextIndex < 0 || nextIndex >= spec.fields.length) return;
        setSpec((current) => {
            const fields = [...current.fields];
            [fields[index], fields[nextIndex]] = [fields[nextIndex], fields[index]];
            return { ...current, fields };
        });
    };

    const changeLogoMode = (nextMode) => {
        setSpec((current) => ({ ...current, logo_mode: nextMode }));
        if (nextMode !== 'upload') {
            setLogoFile(null);
            setLogoData(null);
        }
    };

    const handleLogoFile = async (file) => {
        if (!file) return;
        if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) {
            enqueueSnackbar('Logo 只支援 PNG、JPEG、WebP，且不可超過 5 MiB', { variant: 'warning' });
            return;
        }
        setLogoFile(file);
        try {
            setLogoData(await compressImageToDataUrl(file));
        } catch {
            setLogoFile(null);
            setLogoData(null);
            enqueueSnackbar('Logo 圖片無法讀取', { variant: 'error' });
        }
    };

    const handleGenerate = async () => {
        const validationError = validateStructuredDraft({ pageLabel, pageValue, spec });
        if (validationError) {
            enqueueSnackbar(validationError, { variant: 'warning' });
            return;
        }
        if (!stylePrompt.trim()) {
            enqueueSnackbar('請填寫網頁風格說明', { variant: 'warning' });
            return;
        }
        if (spec.logo_mode === 'upload' && !logoData) {
            enqueueSnackbar('請選擇 Logo 圖片', { variant: 'warning' });
            return;
        }
        if (!await confirmPageValueAvailable()) return;

        setGenerating(true);
        setProgress(sourceHtml ? '正在重新生成；新結果通過驗證前會保留上次有效預覽' : '正在準備 AI 生成...');
        abortControllerRef.current = new AbortController();
        const body = new FormData();
        body.append('prompt', stylePrompt);
        body.append('pageType', 'field');
        body.append('aiModel', model);
        body.append('useDesign', 'false');
        body.append('pageSpec', JSON.stringify(spec));
        body.append('pageValue', pageValue.trim());
        if (referenceImage) body.append('image', referenceImage);

        try {
            const response = await fetch('/api/trigger_page/generate_with_ai_stream', {
                method: 'POST',
                headers: { Authorization: `Bearer ${window.localStorage.getItem('accessToken')}` },
                body,
                signal: abortControllerRef.current.signal,
            });
            if (!response.ok) {
                const result = await response.json();
                throw new Error(result.detail || '生成失敗');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let completed = false;
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const parsed = parseSseChunk(buffer);
                buffer = parsed.complete;
                for (const event of parsed.events) {
                    if (!event.startsWith('data: ')) continue;
                    const payload = JSON.parse(event.slice(6));
                    if (payload.type === 'progress') setProgress(payload.data.message);
                    if (payload.type === 'error') throw new Error(payload.data.message);
                    if (payload.type === 'complete') {
                        const normalizedSpec = payload.data.pageSpec || spec;
                        const html = updateStructuredHtml(payload.data.html, normalizedSpec, 1, logoData);
                        const generatedId = payload.data.generation_id || null;
                        setSpec(normalizedSpec);
                        setSourceHtml(html);
                        setPreviewHtml(html);
                        setPreviewKey((current) => current + 1);
                        setGenerationId(generatedId);
                        setProgress('生成完成，正在自動儲存...');
                        if (!generatedId) throw new Error('生成完成但缺少 generation ID，無法自動儲存');
                        try {
                            await autoSaveGeneratedPage(html, normalizedSpec, generatedId);
                        } catch (saveError) {
                            setProgress(`生成完成，但自動儲存失敗：${saveError.message}。請使用右下角按鈕重試儲存。`);
                            enqueueSnackbar(`生成完成，但自動儲存失敗：${saveError.message}`, { variant: 'error' });
                        }
                        completed = true;
                    }
                }
            }
            if (!completed) throw new Error('AI 生成連線已結束，但未收到完成結果，請重試');
        } catch (error) {
            if (error.name !== 'AbortError') {
                enqueueSnackbar(error.message, { variant: 'error' });
                setProgress(error.message);
            }
        } finally {
            setGenerating(false);
            abortControllerRef.current = null;
        }
    };

    const handleSave = async () => {
        const validationError = validateStructuredDraft({ pageLabel, pageValue, spec });
        if (validationError) {
            enqueueSnackbar(validationError, { variant: 'warning' });
            return;
        }
        if (isAi && !sourceHtml) {
            enqueueSnackbar('請先完成 AI 生成', { variant: 'warning' });
            return;
        }
        if (spec.logo_mode === 'upload' && !logoData && !sourceHasUploadLogo) {
            enqueueSnackbar('請選擇 Logo 圖片', { variant: 'warning' });
            return;
        }
        if (!await confirmPageValueAvailable()) return;
        const currentDraftSnapshot = draftSnapshot({
            pageLabel,
            pageValue,
            allowedDomainId,
            spec,
            templateType,
            backgroundColor,
            backgroundImage,
            logoData,
            sourceHasUploadLogo,
        });
        const hasPersistedChanges = Boolean(persistedDraftSnapshot)
            && persistedDraftSnapshot !== currentDraftSnapshot;
        if (hasPersistedChanges && !window.confirm('頁面設定已有修改。若包含欄位異動，可能影響修改前後記錄的欄位判讀。確定儲存嗎？')) return;

        setSaving(true);
        try {
            const body = new FormData();
            body.append('pageLabel', pageLabel.trim());
            body.append('pageValue', pageValue.trim());
            body.append('allowedDomainId', allowedDomainId === '' ? '' : String(allowedDomainId));
            body.append('pageSpec', JSON.stringify(spec));

            let endpoint = '/api/trigger_page/structured/create';
            if (effectiveEdit) {
                endpoint = '/api/trigger_page/structured/update';
                const finalHtml = updateStructuredHtml(sourceHtml, spec, revision + 1, logoData);
                body.append('oldPageValue', currentPersistedPageValue);
                body.append('specRevision', String(revision));
                body.append('file', new File([finalHtml], `${pageValue.trim() || currentPersistedPageValue}.html`, { type: 'text/html;charset=utf-8' }));
            } else if (isAi || isCopy) {
                const finalHtml = updateStructuredHtml(sourceHtml, spec, 1, logoData);
                body.append('source', isCopy ? 'copy' : 'ai');
                body.append('file', new File([finalHtml], `${pageValue.trim() || 'structured-page'}.html`, { type: 'text/html;charset=utf-8' }));
                if (isCopy) body.append('sourcePageValue', initialData.sourcePageValue || initialData.pageValue);
                if (generationId) body.append('generationId', generationId);
            } else {
                body.append('source', 'custom');
                body.append('templateType', templateType);
                body.append('bgColor', backgroundColor);
                body.append('bgImage', backgroundImage);
                if (logoData) body.append('logoData', logoData);
            }

            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { Authorization: `Bearer ${window.localStorage.getItem('accessToken')}` },
                body,
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || '儲存失敗');
            enqueueSnackbar(`${effectiveEdit ? '結構化頁面更新成功' : '結構化頁面建立成功'}（網址 ID：${result.pageValue}）`, { variant: 'success' });
            onSaved();
        } catch (error) {
            enqueueSnackbar(error.message, { variant: 'error' });
        } finally {
            setSaving(false);
        }
    };

    const availableTypes = isAi && !sourceHtml ? [...FIELD_TYPES, { value: 'custom', label: '指定內容' }] : FIELD_TYPES;
    const dialogTitle = { ai: 'AI 指定生成需求', edit: '編輯結構化頁面', copy: '複製結構化頁面' }[mode] || '新增自訂頁面';
    const showPreview = !isAi || Boolean(sourceHtml && previewHtml);

    return (
        <Dialog
            open={open}
            onClose={(_event, reason) => {
                if (reason !== 'backdropClick' && !generating && !saving) onClose();
            }}
            fullWidth
            maxWidth="xl"
        >
            <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    {isAi && <AutoAwesomeIcon color="success" />}
                    {dialogTitle}
                </Box>
                <IconButton onClick={onClose} disabled={generating || saving} aria-label="關閉"><CloseIcon /></IconButton>
            </DialogTitle>
            <DialogContent dividers>
                <Grid container spacing={3}>
                    <Grid item xs={12} lg={showPreview ? 7 : 12}>
                        <Stack spacing={2.25}>
                            <Alert severity="info">
                                各欄位依遮罩設定在瀏覽器內轉換後才送出。預設最多 10 個欄位。
                            </Alert>
                            <Grid container spacing={2}>
                                <Grid item xs={12} md={6}><TextField required fullWidth disabled={generating} label="名稱" value={pageLabel} onChange={(event) => setPageLabel(event.target.value)} helperText="後台列表顯示名稱" /></Grid>
                                <Grid item xs={12} md={6}>
                                    <TextField
                                        fullWidth
                                        disabled={generating}
                                        label="網址 ID（選填）"
                                        value={pageValue}
                                        onChange={(event) => setPageValue(event.target.value.toLowerCase().trim())}
                                        error={['invalid', 'unavailable', 'error'].includes(pageValueStatus.state)}
                                        color={pageValueStatus.state === 'available' ? 'success' : 'primary'}
                                        helperText={pageValueStatus.message || '小寫英文、數字、底線；留空由系統自動產生'}
                                    />
                                </Grid>
                                <Grid item xs={12} md={6}><TextField required fullWidth disabled={generating} label="分頁標題" value={spec.page_title} onChange={(event) => setSpec({ ...spec, page_title: event.target.value })} /></Grid>
                                <Grid item xs={12} md={6}><TextField required fullWidth disabled={generating} label="網頁標題（H1）" value={spec.main_title} onChange={(event) => setSpec({ ...spec, main_title: event.target.value })} /></Grid>
                            </Grid>
                            <TextField fullWidth multiline minRows={2} disabled={generating} label="說明文字（可省略）" value={spec.description} onChange={(event) => setSpec({ ...spec, description: event.target.value })} />
                            <TextField required fullWidth disabled={generating} label="提交按鈕文字" value={spec.submit_text} onChange={(event) => setSpec({ ...spec, submit_text: event.target.value })} />
                            <FormControl fullWidth>
                                <InputLabel id="structured-domain-label">綁定網域</InputLabel>
                                <Select disabled={generating} labelId="structured-domain-label" label="綁定網域" value={allowedDomainId} onChange={(event) => setAllowedDomainId(event.target.value)}>
                                    <MenuItem value=""><em>使用預設網域</em></MenuItem>
                                    {domainList.map((domain) => <MenuItem key={domain.id} value={domain.id}>{domain.label || domain.domain} ({domain.domain})</MenuItem>)}
                                </Select>
                            </FormControl>

                            <Divider />
                            <Stack direction="row" justifyContent="space-between" alignItems="center">
                                <Box><Typography variant="h6">欄位設定</Typography><Typography variant="caption" color="text.secondary">{spec.fields.length} / {MAX_STRUCTURED_FIELDS} 個欄位</Typography></Box>
                            </Stack>
                            {spec.fields.map((field, index) => (
                                <Paper key={field.id} variant="outlined" sx={{ p: 2, borderRadius: 1 }}>
                                    <Stack spacing={1.5}>
                                        <Stack direction="row" justifyContent="space-between" alignItems="center">
                                            <Typography variant="subtitle2">欄位 {index + 1}</Typography>
                                            <Stack direction="row">
                                                <IconButton size="small" onClick={() => moveField(index, -1)} disabled={generating || index === 0} title="上移"><ArrowUpwardIcon fontSize="small" /></IconButton>
                                                <IconButton size="small" onClick={() => moveField(index, 1)} disabled={generating || index === spec.fields.length - 1} title="下移"><ArrowDownwardIcon fontSize="small" /></IconButton>
                                                <IconButton size="small" color="error" onClick={() => removeField(index)} disabled={generating || spec.fields.length === 1} title="刪除欄位"><DeleteIcon fontSize="small" /></IconButton>
                                            </Stack>
                                        </Stack>
                                        <Grid container spacing={1.5}>
                                            <Grid item xs={12} md={5}><TextField required fullWidth disabled={generating} size="small" label="欄位名稱" value={field.label} inputRef={(node) => { if (node) fieldNameRefs.current.set(field.id, node); else fieldNameRefs.current.delete(field.id); }} onChange={(event) => updateField(index, { label: event.target.value })} /></Grid>
                                            <Grid item xs={12} md={4}>
                                                <FormControl fullWidth size="small"><InputLabel id={`field-type-${field.id}`}>欄位類型</InputLabel><Select disabled={generating} labelId={`field-type-${field.id}`} label="欄位類型" value={field.type} onChange={(event) => changeFieldType(index, event.target.value)}>
                                                    {field.type === 'custom' && !availableTypes.some((type) => type.value === 'custom') && <MenuItem value="custom">指定內容（既有）</MenuItem>}
                                                    {availableTypes.map((type) => <MenuItem key={type.value} value={type.value}>{type.label}</MenuItem>)}
                                                </Select></FormControl>
                                            </Grid>
                                            <Grid item xs={12} md={3}><FormControlLabel control={<Checkbox disabled={generating} checked={field.required} onChange={(event) => updateField(index, { required: event.target.checked })} />} label="必填" /></Grid>
                                        </Grid>
                                        {field.type === 'custom' && (
                                            <TextField fullWidth size="small" label="指定內容規格" value={field.custom_rule} disabled={generating || !!sourceHtml} onChange={(event) => updateField(index, { custom_rule: event.target.value })} helperText={sourceHtml ? '儲存後特殊規則為唯讀；可刪除或轉成固定類型' : '限單一欄位的長度、字元或格式說明'} />
                                        )}
                                        <Grid container spacing={1.5} alignItems="center">
                                            <Grid item xs={12} md={6}>
                                                <FormControl fullWidth size="small"><InputLabel id={`mask-mode-${field.id}`}>遮罩方式</InputLabel><Select disabled={generating} labelId={`mask-mode-${field.id}`} label="遮罩方式" value={field.mask_mode} onChange={(event) => updateField(index, { mask_mode: event.target.value, keep_chars: ['keep_start', 'keep_end'].includes(event.target.value) ? (field.keep_chars || 1) : null })}>
                                                    {MASK_MODES.map((mask) => (<MenuItem key={mask.value} value={mask.value}>{mask.label}</MenuItem>))}
                                                </Select></FormControl>
                                            </Grid>
                                            {['keep_start', 'keep_end'].includes(field.mask_mode) && <Grid item xs={12} md={3}><TextField fullWidth disabled={generating} size="small" type="number" label="保留碼數" inputProps={{ min: 1, max: 100 }} value={field.keep_chars || 1} onChange={(event) => updateField(index, { keep_chars: Number(event.target.value) })} /></Grid>}
                                            <Grid item xs={12} md={3}><Typography variant="caption" color="text.secondary">示意：{exampleForField(field)}</Typography></Grid>
                                        </Grid>
                                    </Stack>
                                </Paper>
                            ))}
                            <Button startIcon={<AddIcon />} onClick={addField} disabled={generating || spec.fields.length >= MAX_STRUCTURED_FIELDS} sx={{ alignSelf: 'flex-start' }}>
                                新增欄位
                            </Button>

                            <Divider />
                            <Typography variant="h6">Logo</Typography>
                            <RadioGroup row value={spec.logo_mode} onChange={(event) => changeLogoMode(event.target.value)}>
                                {isAi && <FormControlLabel value="ai" control={<Radio disabled={generating} />} label="AI 生成（預設）" />}
                                {!isAi && spec.logo_mode === 'ai' && <FormControlLabel value="ai" control={<Radio disabled={generating} />} label="保留既有 AI Logo" />}
                                <FormControlLabel value="none" control={<Radio disabled={generating} />} label="留空" />
                                <FormControlLabel value="upload" control={<Radio disabled={generating} />} label="上傳自訂 Logo" />
                            </RadioGroup>
                            {spec.logo_mode === 'upload' && (
                                <Button variant="outlined" component="label" startIcon={<UploadIcon />} disabled={generating}>
                                    {logoFile ? logoFile.name : '選擇 Logo 圖片'}
                                    <input hidden type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => handleLogoFile(event.target.files?.[0])} />
                                </Button>
                            )}

                            {!isAi && !isEdit && !isCopy && (
                                <>
                                    <Typography variant="h6">固定版型</Typography>
                                    <RadioGroup row value={templateType} onChange={(event) => setTemplateType(event.target.value)}>
                                        <FormControlLabel value="classic" control={<Radio />} label="Classic" />
                                        <FormControlLabel value="modern" control={<Radio />} label="Modern" />
                                    </RadioGroup>
                                    <Grid container spacing={2} alignItems="center">
                                        <Grid item xs={12} md={5}><TextField fullWidth label="背景顏色" value={backgroundColor} onChange={(event) => setBackgroundColor(event.target.value)} /></Grid>
                                        <Grid item xs={12} md={7}><TextField fullWidth label="背景圖片 URL（可省略）" value={backgroundImage} onChange={(event) => setBackgroundImage(event.target.value)} /></Grid>
                                    </Grid>
                                </>
                            )}

                            {isAi && (
                                <>
                                    <Divider />
                                    <Typography variant="h6">AI 外觀設定</Typography>
                                    <TextField required fullWidth multiline minRows={3} label="網頁風格說明" value={stylePrompt} onChange={(event) => setStylePrompt(event.target.value)} disabled={generating} />
                                    <FormControl fullWidth><InputLabel id="structured-model-label">AI 模型</InputLabel><Select labelId="structured-model-label" label="AI 模型" value={model} onChange={(event) => { setModel(event.target.value); if (!VISION_MODELS.includes(event.target.value)) setReferenceImage(null); }}>
                                        {MODEL_OPTIONS.map(([value, label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}
                                    </Select></FormControl>
                                    <Button variant="outlined" component="label" startIcon={<UploadIcon />} disabled={!VISION_MODELS.includes(model) || generating}>
                                        {referenceImage ? referenceImage.name : '上傳參考圖片（可省略）'}
                                        <input hidden type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => {
                                            const file = event.target.files?.[0] || null;
                                            if (file && (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024)) {
                                                enqueueSnackbar('參考圖片只支援 PNG、JPEG、WebP，且不可超過 5 MiB', { variant: 'warning' });
                                                event.target.value = '';
                                                return;
                                            }
                                            setReferenceImage(file);
                                        }} />
                                    </Button>
                                    <Button variant="contained" color="success" startIcon={generating ? <CircularProgress size={18} color="inherit" /> : <AutoAwesomeIcon />} onClick={handleGenerate} disabled={generating || saving}>
                                        {generating ? (progress || '正在生成頁面...') : (sourceHtml ? '重新生成頁面' : '開始生成頁面')}
                                    </Button>
                                </>
                            )}
                        </Stack>
                    </Grid>
                    {showPreview && <Grid item xs={12} lg={5}>
                        <Box sx={{ position: { lg: 'sticky' }, top: 8 }}>
                            <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>即時預覽</Typography>
                            <Box sx={{ height: { xs: 480, lg: 'calc(100vh - 190px)' }, minHeight: 480, border: '1px solid', borderColor: 'divider', borderRadius: 1, overflow: 'hidden', bgcolor: '#fff' }}>
                                <iframe key={previewKey} title="結構化頁面預覽" srcDoc={previewHtml} sandbox="" style={{ width: '100%', height: '100%', border: 0 }} />
                            </Box>
                        </Box>
                    </Grid>}
                </Grid>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose} disabled={generating || saving}>取消</Button>
                <Button variant="contained" onClick={handleSave} disabled={generating || saving || (isAi && !sourceHtml)} startIcon={saving ? <CircularProgress size={18} color="inherit" /> : null}>
                    {saving ? '儲存中...' : '確認並儲存'}
                </Button>
            </DialogActions>
        </Dialog>
    );
};

export default StructuredPageDialog;