-- sendtasks
CREATE TABLE IF NOT EXISTS sendtasks (
    id SERIAL PRIMARY KEY,
    sendtask_uuid VARCHAR(36) UNIQUE NOT NULL,
    sendtask_id TEXT NOT NULL,
    sendtask_owner_gid TEXT[] NOT NULL,
    person_count INT,            -- 測試人數
    pre_test_end_ut BIGINT,      -- 前期測試結束時間
    pre_test_start_ut BIGINT,    -- 前期測試開始時間
    pre_send_end_ut BIGINT,      -- 停止寄送日期
    sendtask_create_ut BIGINT,   -- 創建時間
    test_end_ut BIGINT,          -- 任務結束時間
    test_start_ut BIGINT,        -- 任務開始時間
    stop_time_new BIGINT,        -- 延長停止寄送時間
    is_pause BOOLEAN, -- 是否暫停
    pre_test_enable BOOLEAN, -- 是否有前測
    is_archived BOOLEAN DEFAULT FALSE -- 用於標記該任務是否已超過 14 天 (超過 標記為true)
);

-- send_log_details (取代動態 Table)
CREATE TABLE IF NOT EXISTS send_log_details (
    id BIGSERIAL PRIMARY KEY,
    uuid TEXT UNIQUE NOT NULL,                -- 受測者唯一識別碼 (對應主系統的 uuid)
    sendtask_uuid VARCHAR(36) NOT NULL,-- 關聯回任務主表
    
    -- 主系統同步過來的基本資料
    target_email TEXT,
    person_info TEXT,
    template_uuid TEXT,
    plan_time BIGINT,
    send_time BIGINT,
    send_res TEXT,
    
    -- 主系統同步過來的觸發紀錄
    access_time BIGINT[],
    access_src TEXT[],
    access_dev TEXT[],
    click_time BIGINT[],
    click_src TEXT[],
    click_dev TEXT[],
    file_time BIGINT[],
    file_src TEXT[],
    file_dev TEXT[],

    -- Dashboard 系統獨有的觸發紀錄 (偽裝網頁)
    second_access_time BIGINT[],     -- 網頁開啟紀錄
    second_access_src TEXT[],
    second_access_dev TEXT[],
    second_qrcode_time BIGINT[],      -- QR Code 開啟紀錄
    second_qrcode_src TEXT[],
    second_qrcode_dev TEXT[],
    second_input_time BIGINT[],       -- 輸入紀錄
    second_input_src TEXT[],
    second_input_dev TEXT[],
    second_input_info TEXT[],  -- 建議存 JSON 字串或 TEXT Array


    -- 索引優化
    CONSTRAINT fk_sendtask FOREIGN KEY(sendtask_uuid) REFERENCES sendtasks(sendtask_uuid) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_details_sendtask_uuid ON send_log_details(sendtask_uuid);
CREATE INDEX IF NOT EXISTS idx_details_uuid ON send_log_details(uuid);

-- sendlog_stats 
CREATE TABLE IF NOT EXISTS sendlog_stats (
    sendtask_uuid VARCHAR(36) PRIMARY KEY,
    totalplanned BIGINT,
    totalsend BIGINT,
    totalsuccess BIGINT,
    totalfailed BIGINT,
    totaltriggered BIGINT,
    todayunsend BIGINT,
    todaysend BIGINT,
    todaysuccess BIGINT,
    todayfailed BIGINT,
    today_earliest_plan_time BIGINT,
    today_latest_plan_time BIGINT,
    all_earliest_plan_time BIGINT,
    all_latest_plan_time BIGINT
);

-- accts
CREATE TABLE IF NOT EXISTS accts (
    id SERIAL PRIMARY KEY,
    acct_uuid VARCHAR(36) UNIQUE NOT NULL,
    acct_id TEXT NOT NULL,
    acct_full_name TEXT NOT NULL,
    acct_full_name_2nd TEXT,
    acct_email TEXT NOT NULL,
    acct_locale_code TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    acct_create_ut BIGINT,
    acct_update_ut BIGINT,
    acct_update_scrt_ut BIGINT,
    acct_last_login_ut BIGINT,
    acct_last_login_info TEXT,
    admin_role BOOLEAN,
    agent_role BOOLEAN,
    orgs TEXT[]
);

-- users
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    acct_uuid VARCHAR(36) UNIQUE NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- customer accounts
CREATE TABLE IF NOT EXISTS customer_accts (
    id SERIAL PRIMARY KEY,
    customer_uuid VARCHAR(36) UNIQUE NOT NULL,  -- 客戶專屬 UUID（去連字號格式）
    customer_name TEXT UNIQUE NOT NULL,
    customer_full_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    sendtasks JSONB DEFAULT '[]'::jsonb,
    acct_uuid VARCHAR(36) NOT NULL,
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- mtmpl
CREATE TABLE IF NOT EXISTS mtmpl (
    id SERIAL PRIMARY KEY,
    mtmpl_uuid VARCHAR(36) NOT NULL,
    mtmpl_title TEXT NOT NULL,
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- notifications
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    title TEXT,
    subtitle TEXT,
    heading TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    path TEXT,
    icon_name TEXT,
    icon_color TEXT,
    details TEXT,
    is_read BOOLEAN DEFAULT FALSE
);

-- login_logs
CREATE TABLE IF NOT EXISTS login_logs (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    action TEXT NOT NULL, -- 'login', 'logout'
    status TEXT NOT NULL, -- 'success', 'failed'
    ip_address TEXT,
    details TEXT,
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- trigger_pages
CREATE TABLE IF NOT EXISTS trigger_pages (
    id SERIAL PRIMARY KEY,
    page_value VARCHAR(255) UNIQUE NOT NULL,
    page_label TEXT NOT NULL,
    owner_uuid VARCHAR(36), -- NULL 表示系統預設頁面
    page_type TEXT DEFAULT 'custom', -- 'system', 'custom', 'ai'
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- customer_tasks（追蹤客戶建立的專案與任務狀態）
CREATE TABLE IF NOT EXISTS customer_tasks (
    id SERIAL PRIMARY KEY,
    customer_uuid VARCHAR(36) NOT NULL,
    testcase_uuid VARCHAR(36) UNIQUE NOT NULL,
    sendtask_uuid VARCHAR(36),
    task_name VARCHAR(255),
    task_type VARCHAR(20),
    status VARCHAR(20) DEFAULT 'created',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_customer_tasks_customer_uuid ON customer_tasks(customer_uuid);