from sqlalchemy import Column,Integer,String,Float,Boolean,ForeignKey,UniqueConstraint
from ..config.database import Base
class MonitorPlan(Base):
    __tablename__='monitor_plans'
    id=Column(Integer,primary_key=True)
    name=Column(String(160),unique=True,nullable=False)
    alpha=Column(Float,nullable=False)
    threshold_minutes=Column(Float,nullable=False)
    furnace_count=Column(Integer,nullable=False)
    alarm_boundary=Column(Float,nullable=False)  # ln(炉数/误报上限)
    created_by=Column(String(120),nullable=False)
    created_at=Column(String(40),nullable=False)
class MonitorFurnace(Base):
    __tablename__='monitor_furnaces'
    __table_args__=(UniqueConstraint('plan_id','name',name='uq_monitor_furnace_name'),)
    id=Column(Integer,primary_key=True)
    plan_id=Column(Integer,ForeignKey('monitor_plans.id'),nullable=False)
    name=Column(String(160),nullable=False)
    position=Column(Integer,nullable=False)
    total=Column(Integer,nullable=False)
    next_seq=Column(Integer,nullable=False,default=1)
    counted=Column(Integer,nullable=False,default=0)
    inaccurate_count=Column(Integer,nullable=False,default=0)
    llr=Column(Float,nullable=False,default=0.0)
    alarmed=Column(Boolean,nullable=False,default=False)
    alarm_seq=Column(Integer,nullable=True)
    alarm_piece=Column(String(120),nullable=True)
    alarmed_at=Column(String(40),nullable=True)
class MonitorPrediction(Base):
    __tablename__='monitor_predictions'
    __table_args__=(UniqueConstraint('furnace_id','seq',name='uq_monitor_prediction_seq'),)
    id=Column(Integer,primary_key=True)
    plan_id=Column(Integer,ForeignKey('monitor_plans.id'),nullable=False)
    furnace_id=Column(Integer,ForeignKey('monitor_furnaces.id'),nullable=False)
    seq=Column(Integer,nullable=False)
    piece_id=Column(String(120),nullable=False)
    predicted_minutes=Column(Float,nullable=False)
class MonitorReading(Base):
    __tablename__='monitor_readings'
    __table_args__=(UniqueConstraint('furnace_id','seq',name='uq_monitor_reading_seq'),UniqueConstraint('idempotency_key',name='uq_monitor_reading_key'),)
    id=Column(Integer,primary_key=True)
    plan_id=Column(Integer,ForeignKey('monitor_plans.id'),nullable=False)
    furnace_id=Column(Integer,ForeignKey('monitor_furnaces.id'),nullable=False)
    seq=Column(Integer,nullable=False)
    piece_id=Column(String(120),nullable=False)
    actual_minutes=Column(Float,nullable=False)
    inaccurate=Column(Boolean,nullable=False)
    state=Column(String(20),nullable=False,default='buffered')  # buffered待补 / counted已计入
    idempotency_key=Column(String(120),nullable=True)
    actor=Column(String(120),nullable=False)
    received_at=Column(String(40),nullable=False)
    counted_at=Column(String(40),nullable=True)
class MonitorCorrection(Base):
    __tablename__='monitor_corrections'
    id=Column(Integer,primary_key=True)
    plan_id=Column(Integer,ForeignKey('monitor_plans.id'),nullable=False)
    furnace_id=Column(Integer,ForeignKey('monitor_furnaces.id'),nullable=False)
    seq=Column(Integer,nullable=False)
    piece_id=Column(String(120),nullable=False)
    old_minutes=Column(Float,nullable=False)
    new_minutes=Column(Float,nullable=False)
    reason=Column(String(600),default='')
    actor=Column(String(120),nullable=False)
    created_at=Column(String(40),nullable=False)
