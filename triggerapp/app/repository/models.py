from sqlalchemy import (
    Column, Integer, String, Boolean, BigInteger, Text
)
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from app.repository.database import Base

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

class SendLogDetail(Base):
    __tablename__ = "send_log_details"

    id = Column(BigInteger, primary_key=True, index=True)
    uuid = Column(Text, unique=True, nullable=False, index=True)
    sendtask_uuid = Column(String(36), nullable=False, index=True)
    
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
