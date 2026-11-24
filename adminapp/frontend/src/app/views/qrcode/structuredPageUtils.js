export const MAX_STRUCTURED_FIELDS = 10;

export const FIELD_TYPES = [
    { value: 'text', label: '純文字' },
    { value: 'email', label: 'Email' },
    { value: 'password', label: '密碼' },
    { value: 'national_id', label: '身分證字號' },
    { value: 'phone', label: '電話' },
];

export const MASK_MODES = [
    { value: 'none', label: '不遮罩' },
    { value: 'full', label: '全部遮罩' },
    { value: 'keep_start', label: '保留前 N 碼' },
    { value: 'keep_end', label: '保留後 N 碼' },
];

export const createStructuredField = () => ({
    id: `field_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    label: '',
    type: 'text',
    required: true,
    mask_mode: 'full',
    keep_chars: null,
    custom_rule: '',
    validation_pattern: '',
});

export const createStructuredSpec = (logoMode = 'none') => ({
    version: 1,
    page_title: '',
    main_title: '',
    description: '',
    submit_text: '送出',
    logo_mode: logoMode,
    fields: [createStructuredField()],
});

export const applyFieldType = (field, nextType) => {
    return {
        ...field,
        type: nextType,
        keep_chars: ['keep_start', 'keep_end'].includes(field.mask_mode) ? (field.keep_chars || 1) : null,
        custom_rule: nextType === 'custom' ? field.custom_rule : '',
        validation_pattern: nextType === 'custom' ? field.validation_pattern : '',
    };
};

export const maskPreviewValue = (value, field) => {
    const characters = Array.from(value || '');
    if (!characters.length || field.mask_mode === 'none') return characters.join('');
    if (field.mask_mode === 'full' || characters.length === 1) return '*'.repeat(characters.length);

    const requested = Number.parseInt(field.keep_chars, 10) || 1;
    const visibleCount = characters.length > requested ? requested : characters.length - 1;
    const hidden = '*'.repeat(characters.length - visibleCount);
    if (field.mask_mode === 'keep_start') {
        return characters.slice(0, visibleCount).join('') + hidden;
    }
    return hidden + characters.slice(-visibleCount).join('');
};

export const exampleForField = (field) => {
    const value = {
        email: 'name@example.com',
        password: 'example123',
        national_id: 'A123456789',
        phone: '0912345678',
        custom: 'ABC123456',
    }[field.type] || 'example123';
    return maskPreviewValue(value, field);
};

export const validateStructuredDraft = ({ pageLabel, pageValue, spec }) => {
    if (!pageLabel.trim() || !spec.page_title.trim() || !spec.main_title.trim()) {
        return '請填寫名稱、分頁標題與網頁標題';
    }
    if (pageValue.trim() && !/^[a-z0-9_]+$/.test(pageValue.trim())) return '網址 ID 只能包含小寫字母、數字和底線';
    if (!spec.submit_text.trim()) return '請填寫提交按鈕文字';
    if (!spec.fields.length || spec.fields.length > MAX_STRUCTURED_FIELDS) {
        return `欄位數量必須介於 1 到 ${MAX_STRUCTURED_FIELDS} 個`;
    }
    for (const [index, field] of spec.fields.entries()) {
        if (!field.label.trim()) return `請填寫第 ${index + 1} 個欄位名稱`;
        if (field.type === 'custom' && !field.custom_rule.trim()) return `請填寫第 ${index + 1} 個指定內容規格`;
        if (['keep_start', 'keep_end'].includes(field.mask_mode)) {
            const count = Number(field.keep_chars);
            if (!Number.isInteger(count) || count < 1 || count > 100) {
                return `第 ${index + 1} 個欄位的保留碼數必須介於 1 到 100`;
            }
        }
    }
    return null;
};

const setAttributeIf = (element, name, value) => {
    if (value !== null && value !== undefined && value !== '') element.setAttribute(name, String(value));
};

const createFieldNode = (document, field) => {
    const wrapper = document.createElement('div');
    wrapper.className = 'structured-field';
    wrapper.dataset.structuredFieldRow = field.id;

    const label = document.createElement('label');
    label.setAttribute('for', `structured-input-${field.id}`);
    label.append(document.createTextNode(field.label));
    if (field.required) {
        const mark = document.createElement('span');
        mark.className = 'structured-required';
        mark.setAttribute('aria-hidden', 'true');
        mark.textContent = '*';
        label.append(mark);
    }

    const input = document.createElement('input');
    input.id = `structured-input-${field.id}`;
    input.type = { email: 'email', password: 'password', phone: 'tel' }[field.type] || 'text';
    input.dataset.structuredFieldId = field.id;
    input.dataset.fieldType = field.type;
    input.dataset.maskMode = field.mask_mode;
    if (field.keep_chars) input.dataset.keepChars = String(field.keep_chars);
    input.autocomplete = 'off';
    input.required = field.required;

    if (field.type === 'national_id') {
        input.pattern = '[A-Za-z][12][0-9]{8}';
        input.maxLength = 10;
        input.inputMode = 'text';
        input.title = '請輸入英文字母、1 或 2，再接 8 個數字';
    } else if (field.type === 'phone') {
        input.pattern = '09[0-9]{8}';
        input.maxLength = 10;
        input.inputMode = 'numeric';
        input.title = '請輸入 09 開頭的 10 位數手機號碼';
    } else if (field.type === 'custom') {
        setAttributeIf(input, 'pattern', field.validation_pattern);
        setAttributeIf(input, 'title', field.custom_rule);
    }

    wrapper.append(label, input);
    return wrapper;
};

export const updateStructuredHtml = (html, spec, revision, logoData = null) => {
    const document = new DOMParser().parseFromString(html, 'text/html');
    const mainTitle = document.getElementById('custom-main-title');
    const description = document.getElementById('structured-description');
    const form = document.getElementById('structured-form');
    const fields = document.getElementById('structured-fields');
    const submit = document.getElementById('structured-submit');
    const logo = document.getElementById('custom-brand-logo');
    if (!mainTitle || !description || !form || !fields || !submit || !logo) {
        throw new Error('頁面缺少結構化編輯所需的固定節點');
    }

    document.title = spec.page_title;
    mainTitle.textContent = spec.main_title;
    description.textContent = spec.description;
    submit.textContent = spec.submit_text;
    form.dataset.specRevision = String(revision);
    fields.replaceChildren(...spec.fields.map((field) => createFieldNode(document, field)));

    if (spec.logo_mode === 'none') {
        logo.replaceChildren();
    } else if (spec.logo_mode === 'upload' && logoData) {
        const image = document.createElement('img');
        image.src = logoData;
        image.alt = 'Brand Logo';
        logo.replaceChildren(image);
    }
    return `<!DOCTYPE html>\n${document.documentElement.outerHTML}`;
};

export const buildStructuredPreview = (spec, logoData = null) => {
    const shell = `<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="UTF-8"><style>
        *{box-sizing:border-box}body{margin:0;min-height:100vh;padding:28px 16px;display:grid;place-items:center;background:#edf2ef;color:#15251f;font-family:Georgia,"Times New Roman",serif}.structured-card{width:min(100%,480px);padding:32px;border:1px solid #b7c6bf;border-top:5px solid #0b6b5c;border-radius:6px;background:#fff;box-shadow:0 18px 50px rgba(21,37,31,.14)}#custom-brand-logo img{display:block;max-width:180px;max-height:80px;margin:0 auto 20px}h1{text-align:center;margin:0;font-size:2rem}#structured-description{text-align:center;color:#52625b;line-height:1.6;margin:10px 0 24px}#structured-description:empty{display:none}.structured-field{margin-bottom:17px}.structured-field label{display:block;font-weight:700;margin-bottom:7px}.structured-required{color:#b42318;margin-left:4px}.structured-field input{width:100%;min-height:44px;border:1px solid #98aaa2;border-radius:4px;padding:10px 12px;font:inherit}button{width:100%;min-height:46px;border:0;border-radius:4px;background:#0b6b5c;color:#fff;font:700 1rem Georgia,"Times New Roman",serif}@media(max-width:560px){body{place-items:start center;padding:16px 10px}.structured-card{padding:24px 18px}h1{font-size:1.65rem}}
    </style></head><body><main class="structured-card"><div id="custom-brand-logo"></div><h1 id="custom-main-title"></h1><p id="structured-description"></p><form id="structured-form"><div id="structured-fields"></div><button id="structured-submit" type="button"></button></form></main></body></html>`;
    return updateStructuredHtml(shell, spec, 1, logoData);
};