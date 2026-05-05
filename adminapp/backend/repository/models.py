from sqlalchemy import (
    Column, Integer, String, Boolean, BigInteger, Text, 
    TIMESTAMP, ForeignKey, JSON, ARRAY
)
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB, ARRAY as PG_ARRAY
from backend.repository.database import Base

class SendTask(Base):
    __tablename__ = "sendtasks"

    id = Column(Integer, primary_key=True, index=True)
    sendtask_uuid = Column(String(36), unique=True, nullable=False, index=True)
    sendtask_id = Column(Text, nullable=False)
    sendtask_owner_gid = Column(PG_ARRAY(Text), nullable=False)
    person_count = Column(Integer)
    pre_test_end_ut = Column(BigInteger)
    pre_test_start_ut = Column(BigInteger)
    pre_send_end_ut = Column(BigInteger)
    sendtask_create_ut = Column(BigInteger)
    test_end_ut = Column(BigInteger)
    test_start_ut = Column(BigInteger)
    stop_time_new = Column(BigInteger)
    is_pause = Column(Boolean)
    pre_test_enable = Column(Boolean)
    is_archived = Column(Boolean, default=False)
    send_end_ut     = Column(BigInteger, nullable=True)
    sendtask_public = Column(Boolean, nullable=True)
    server_url      = Column(Text, nullable=True)

class SendLogDetail(Base):
    __tablename__ = "send_log_details"

    id = Column(BigInteger, primary_key=True, index=True)
    uuid = Column(Text, unique=True, nullable=False, index=True)
    sendtask_uuid = Column(String(36), ForeignKey("sendtasks.sendtask_uuid", ondelete="CASCADE"), nullable=False, index=True)
    
    target_email = Column(Text)
    person_info = Column(Text)
    template_uuid = Column(Text)
    plan_time = Column(BigInteger)
    send_time = Column(BigInteger)
    send_res = Column(Text)
    
    access_time = Column(PG_ARRAY(BigInteger))
    access_src = Column(PG_ARRAY(Text))
    access_dev = Column(PG_ARRAY(Text))
    click_time = Column(PG_ARRAY(BigInteger))
    click_src = Column(PG_ARRAY(Text))
    click_dev = Column(PG_ARRAY(Text))
    file_time = Column(PG_ARRAY(BigInteger))
    file_src = Column(PG_ARRAY(Text))
    file_dev = Column(PG_ARRAY(Text))

    second_access_time = Column(PG_ARRAY(BigInteger))
    second_access_src = Column(PG_ARRAY(Text))
    second_access_dev = Column(PG_ARRAY(Text))
    second_qrcode_time = Column(PG_ARRAY(BigInteger))
    second_qrcode_src = Column(PG_ARRAY(Text))
    second_qrcode_dev = Column(PG_ARRAY(Text))
    second_input_time = Column(PG_ARRAY(BigInteger))
    second_input_src = Column(PG_ARRAY(Text))
    second_input_dev = Column(PG_ARRAY(Text))
    second_input_info = Column(PG_ARRAY(Text))
    order_no           = Column(Integer, nullable=True)
    template_order     = Column(Integer, nullable=True)
    template_selection = Column(Integer, nullable=True)
    trigger_man        = Column(Integer, nullable=True)

class SendLogStats(Base):
    __tablename__ = "sendlog_stats"

    sendtask_uuid = Column(String(36), primary_key=True, index=True)
    totalplanned = Column(BigInteger)
    totalsend = Column(BigInteger)
    totalsuccess = Column(BigInteger)
    totalfailed = Column(BigInteger)
    totaltriggered = Column(BigInteger)
    todayunsend = Column(BigInteger)
    todaysend = Column(BigInteger)
    todaysuccess = Column(BigInteger)
    todayfailed = Column(BigInteger)
    today_earliest_plan_time = Column(BigInteger)
    today_latest_plan_time = Column(BigInteger)
    all_earliest_plan_time = Column(BigInteger)
    all_latest_plan_time = Column(BigInteger)

class Acct(Base):
    __tablename__ = "accts"

    id = Column(Integer, primary_key=True, index=True)
    acct_uuid = Column(String(36), unique=True, nullable=False, index=True)
    acct_id = Column(Text, nullable=False)
    acct_full_name = Column(Text, nullable=False)
    acct_full_name_2nd = Column(Text)
    acct_email = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    orgs = Column(PG_ARRAY(Text))

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    acct_uuid = Column(String(36), unique=True, nullable=False, index=True)
    username = Column(Text, unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=False)
    email = Column(Text)
    full_name = Column(Text)
    orgs = Column(PG_ARRAY(Text))
    create_time = Column(TIMESTAMP, server_default=func.now())
    is_active = Column(Boolean, default=True)

class CustomerAcct(Base):
    __tablename__ = "customer_accts"

    id = Column(Integer, primary_key=True, index=True)
    customer_uuid = Column(String(36), unique=True, nullable=False, index=True)
    customer_name = Column(Text, unique=True, nullable=False, index=True)
    customer_full_name = Column(Text, nullable=False)
    password_hash = Column(Text, nullable=False)
    sendtasks = Column(JSONB, default=list)
    acct_uuid = Column(String(36), nullable=False)
    create_time = Column(TIMESTAMP, server_default=func.now())
    is_active = Column(Boolean, default=True)
    task_creation_enabled = Column(Boolean, default=False)  # 控制客戶是否可使用「新增任務」功能
    task_creation_org_uuid = Column(String(36), nullable=True)  # 控制客戶「新增任務」對應的組織

class Mtmpl(Base):
    __tablename__ = "mtmpl"

    id = Column(Integer, primary_key=True, index=True)
    mtmpl_uuid = Column(String(64), unique=True, nullable=False, index=True)
    mtmpl_name = Column(Text)
    mtmpl_tag = Column(PG_ARRAY(Text))
    mtmpl_title = Column(Text)
    mtmpl_content = Column(Text)
    mtmpl_activate = Column(Boolean, default=True)
    mtmpl_mail_attached = Column(PG_ARRAY(Text))
    mtmpl_create_ut = Column(BigInteger)
    mtmpl_update_ut = Column(BigInteger)
    mtmpl_owner_gid = Column(PG_ARRAY(Text))
    mtmpl_public = Column(Boolean, default=False)
    mtmpl_plain = Column(Boolean, default=False)
    mtmpl_embedded_img = Column(Boolean, default=False)
    mtmpl_readonly = Column(Boolean, default=False)
    mail_from = Column(Text)
    mail_from_address = Column(Text)
    create_time = Column(TIMESTAMP, server_default=func.now())

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(Text, nullable=False, index=True)
    title = Column(Text)
    subtitle = Column(Text)
    heading = Column(Text)
    timestamp = Column(TIMESTAMP, server_default=func.now())
    path = Column(Text)
    icon_name = Column(Text)
    icon_color = Column(Text)
    details = Column(Text)
    is_read = Column(Boolean, default=False)

class LoginLog(Base):
    __tablename__ = "login_logs"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(Text, nullable=False, index=True)
    action = Column(Text, nullable=False)
    status = Column(Text, nullable=False)
    ip_address = Column(Text)
    details = Column(Text)
    create_time = Column(TIMESTAMP, server_default=func.now())

class TriggerPage(Base):
    __tablename__ = "trigger_pages"

    id = Column(Integer, primary_key=True, index=True)
    page_value = Column(String(255), unique=True, nullable=False, index=True)
    page_label = Column(Text, nullable=False)
    owner_uuid = Column(String(36), index=True)
    page_type = Column(Text, default='custom')
    create_time = Column(TIMESTAMP, server_default=func.now())

class SystemConfig(Base):
    __tablename__ = "system_config"

    id = Column(Integer, primary_key=True, index=True)
    config_key = Column(Text, unique=True, nullable=False, index=True)
    config_value = Column(Text, nullable=True)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

class CustomerTask(Base):
    """追蹤客戶建立的專案與任務狀態"""
    __tablename__ = "customer_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_uuid = Column(String(36), nullable=False, index=True)   # 客戶 UUID
    sendtask_uuid = Column(String(36), unique=True, nullable=False)  # 任務/專案 UUID（testcase_uuid 與 sendtask_uuid 相同）
    task_name = Column(String(255))                                   # 任務名稱
    task_type = Column(String(20))                                    # pre / official
    status = Column(String(20), default='created')                    # created / active / stopped / deleted
    created_at = Column(TIMESTAMP, server_default=func.now())
