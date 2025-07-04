-- sendtasks
CREATE TABLE IF NOT EXISTS sendtasks (
    id SERIAL PRIMARY KEY,
    sendtask_uuid VARCHAR(36) UNIQUE NOT NULL,
    sendtask_id TEXT NOT NULL,
    sendtask_owner_gid TEXT[] NOT NULL,
    pre_test_end_ut BIGINT,      -- 前期測試結束時間
    pre_test_start_ut BIGINT,    -- 前期測試開始時間
    pre_send_end_ut BIGINT,      -- 停止寄送日期
    sendtask_create_ut BIGINT,   -- 創建時間
    test_end_ut BIGINT,          -- 任務結束時間
    test_start_ut BIGINT,        -- 任務開始時間
    stop_time_new BIGINT,        -- 延長停止寄送時間
    is_pause BOOLEAN, -- 是否暫停
    is_active BOOLEAN DEFAULT TRUE 
);

-- accts
CREATE TABLE IF NOT EXISTS accts (
    id SERIAL PRIMARY KEY,
    acct_uuid VARCHAR(36) NOT NULL,
    acct_id TEXT NOT NULL,
    acct_full_name TEXT NOT NULL,
    acct_full_name_2nd TEXT,
    acct_email TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    orgs TEXT[]
);

-- users
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email TEXT,
    full_name TEXT,
    orgs TEXT[],
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- sendlog_stats 
CREATE TABLE IF NOT EXISTS sendlog_stats (
    sendtask_uuid VARCHAR(36) PRIMARY KEY,
    totalplanned BIGINT,
    totalsuccess BIGINT,
    today_earliest_plan_time BIGINT,
    today_latest_plan_time BIGINT,
    all_earliest_plan_time BIGINT,
    all_latest_plan_time BIGINT,
    todayunsend BIGINT,
    todaysend BIGINT,
    todaysuccess BIGINT,
    totalsend BIGINT
);