-- tasks
CREATE TABLE IF NOT EXISTS sendtasks (
    id SERIAL PRIMARY KEY,
    sendtask_id TEXT NOT NULL,
    sendtask_uuid VARCHAR(36) NOT NULL,
    sendtask_create_ut BIGINT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE 
);