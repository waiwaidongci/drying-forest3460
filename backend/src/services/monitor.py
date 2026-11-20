import math
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from ..models.monitor import MonitorPlan,MonitorFurnace,MonitorPrediction,MonitorReading,MonitorCorrection
from ..utils.serialization import now
from .audit import log
from .monitor_sprt import FurnaceEngine,alarm_boundary,is_inaccurate

def get_plan(db,plan_id):
    p=db.get(MonitorPlan,plan_id)
    if not p:raise HTTPException(404,'未找到炉序监控方案')
    return p

def create_plan(db,user,data):
    names=[f.name.strip() for f in data.furnaces]
    if len(set(names))!=len(names):raise HTTPException(422,'炉名不能重复')
    for f in data.furnaces:
        pieces=[p.piece_id.strip() for p in f.predictions]
        if len(set(pieces))!=len(pieces):raise HTTPException(422,f'{f.name.strip()}的试件编号不能重复')
    plan=MonitorPlan(name=data.name.strip(),alpha=data.alpha,threshold_minutes=data.threshold_minutes,furnace_count=len(data.furnaces),alarm_boundary=alarm_boundary(len(data.furnaces),data.alpha),created_by=user.email,created_at=now())
    db.add(plan)
    try:db.flush()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'方案名称已存在')
    for position,f in enumerate(data.furnaces,1):
        furnace=MonitorFurnace(plan_id=plan.id,name=f.name.strip(),position=position,total=len(f.predictions))
        db.add(furnace);db.flush()
        for seq,p in enumerate(f.predictions,1):
            db.add(MonitorPrediction(plan_id=plan.id,furnace_id=furnace.id,seq=seq,piece_id=p.piece_id.strip(),predicted_minutes=p.predicted_minutes))
    log(db,user,'monitor.plan_created',plan.id,f'{plan.name} · {plan.furnace_count}炉 · 误报上限{plan.alpha} · 阈值{plan.threshold_minutes}分钟')
    db.commit()
    return plan_detail(db,plan.id)

def list_plans(db):
    out=[]
    for p in db.scalars(select(MonitorPlan).order_by(MonitorPlan.id.desc())):
        furnaces=db.scalars(select(MonitorFurnace).where(MonitorFurnace.plan_id==p.id)).all()
        out.append({'id':p.id,'name':p.name,'alpha':p.alpha,'threshold_minutes':p.threshold_minutes,'furnace_count':p.furnace_count,'alarmed_count':sum(1 for f in furnaces if f.alarmed),'created_at':p.created_at})
    return out

def furnace_status(db,plan,f):
    checked_seq=f.next_seq-1
    checked_piece=None
    if checked_seq>=1:
        checked_piece=db.scalar(select(MonitorPrediction.piece_id).where(MonitorPrediction.furnace_id==f.id,MonitorPrediction.seq==checked_seq))
    buffered=sorted(db.scalars(select(MonitorReading.seq).where(MonitorReading.furnace_id==f.id,MonitorReading.state=='buffered')))
    return {'id':f.id,'name':f.name,'position':f.position,'total':f.total,'counted':f.counted,'inaccurate_count':f.inaccurate_count,'next_seq':f.next_seq,'checked_seq':checked_seq or None,'checked_piece':checked_piece,'llr':round(f.llr,6),'lr':round(math.exp(f.llr),4) if -50<f.llr<50 else None,'alarmed':f.alarmed,'alarm_seq':f.alarm_seq,'alarm_piece':f.alarm_piece,'alarmed_at':f.alarmed_at,'buffered':buffered,'done':f.counted>=f.total}

def plan_detail(db,plan_id):
    p=get_plan(db,plan_id)
    furnaces=db.scalars(select(MonitorFurnace).where(MonitorFurnace.plan_id==p.id).order_by(MonitorFurnace.position))
    return {'id':p.id,'name':p.name,'alpha':p.alpha,'threshold_minutes':p.threshold_minutes,'furnace_count':p.furnace_count,'alarm_ratio':round(p.furnace_count/p.alpha,4),'alarm_boundary':round(p.alarm_boundary,6),'created_by':p.created_by,'created_at':p.created_at,'furnaces':[furnace_status(db,p,f) for f in furnaces]}

def _drain(db,plan,furnace):
    """按清单顺序计入该炉已连续到达的实测；缺号只阻塞本炉。

    在持有炉行锁的事务内调用：并发补报被串行化，计入不会跳号；
    中断后状态已持久化，重试由唯一约束与序号去重保证不重复计入。
    返回 {'counted':[...], 'alarm':{...}|None}。
    """
    engine=FurnaceEngine(plan.alarm_boundary,next_seq=furnace.next_seq,llr=furnace.llr,counted=furnace.counted,inaccurate_count=furnace.inaccurate_count,alarmed=furnace.alarmed,alarm_seq=furnace.alarm_seq)
    rows=db.scalars(select(MonitorReading).where(MonitorReading.furnace_id==furnace.id,MonitorReading.state=='buffered').order_by(MonitorReading.seq)).all()
    for r in rows:engine.buffer(r.seq,r.inaccurate)
    counted,first_alarm=engine.drain()
    if not counted:return {'counted':[],'alarm':None}
    stamp=now()
    for r in rows:
        if r.seq in counted:r.state='counted';r.counted_at=stamp
    furnace.next_seq=engine.next_seq;furnace.counted=engine.counted;furnace.inaccurate_count=engine.inaccurate_count;furnace.llr=engine.llr
    alarm=None
    if first_alarm is not None:
        furnace.alarmed=True;furnace.alarm_seq=first_alarm;furnace.alarmed_at=stamp
        furnace.alarm_piece=db.scalar(select(MonitorPrediction.piece_id).where(MonitorPrediction.furnace_id==furnace.id,MonitorPrediction.seq==first_alarm))
        alarm={'furnace':furnace.name,'seq':first_alarm,'piece':furnace.alarm_piece,'llr':round(engine.llr,6)}
    return {'counted':counted,'alarm':alarm}

def _locked_furnace(db,plan,furnace_id):
    f=db.scalar(select(MonitorFurnace).where(MonitorFurnace.id==furnace_id,MonitorFurnace.plan_id==plan.id).with_for_update())
    if not f:raise HTTPException(404,'方案中无此炉')
    return f

def submit_reading(db,user,plan_id,data):
    plan=get_plan(db,plan_id)
    furnace=_locked_furnace(db,plan,data.furnace_id)
    prediction=db.scalar(select(MonitorPrediction).where(MonitorPrediction.furnace_id==furnace.id,MonitorPrediction.seq==data.seq))
    if not prediction:raise HTTPException(422,f'{furnace.name}清单共{furnace.total}件，无序号{data.seq}')
    existing=db.scalar(select(MonitorReading).where(MonitorReading.furnace_id==furnace.id,MonitorReading.seq==data.seq))
    if existing:
        if abs(existing.actual_minutes-data.actual_minutes)<1e-9:
            return {'result':'duplicate','message':f'{furnace.name}第{data.seq}件已上报过，重复上报未计入','alarm':None,'furnace':furnace_status(db,plan,furnace)}
        if existing.state=='counted':
            db.add(MonitorCorrection(plan_id=plan.id,furnace_id=furnace.id,seq=existing.seq,piece_id=existing.piece_id,old_minutes=existing.actual_minutes,new_minutes=data.actual_minutes,reason='补报读数更正',actor=user.email,created_at=now()))
            log(db,user,'monitor.reading_corrected',f'{plan.id}/{furnace.id}/{existing.seq}',f'{furnace.name}第{existing.seq}件 {existing.actual_minutes}→{data.actual_minutes}分钟；已计入读数与既有报警不变')
            db.commit()
            return {'result':'correction_logged','message':'该件已计入，报警仍按当时读数；更正已留痕','alarm':None,'furnace':furnace_status(db,plan,furnace)}
        existing.actual_minutes=data.actual_minutes
        existing.inaccurate=is_inaccurate(data.actual_minutes,prediction.predicted_minutes,plan.threshold_minutes)
        existing.actor=user.email
        db.flush()
        outcome=_drain(db,plan,furnace)
        if outcome['alarm']:log(db,user,'monitor.alarm',plan.id,f"{outcome['alarm']['furnace']}第{outcome['alarm']['seq']}件首次报警")
        db.commit()
        return {'result':'updated_pending','message':'缓冲中的读数已更新','alarm':outcome['alarm'],'furnace':furnace_status(db,plan,furnace)}
    reading=MonitorReading(plan_id=plan.id,furnace_id=furnace.id,seq=data.seq,piece_id=prediction.piece_id,actual_minutes=data.actual_minutes,inaccurate=is_inaccurate(data.actual_minutes,prediction.predicted_minutes,plan.threshold_minutes),state='buffered',idempotency_key=(data.idempotency_key or None),actor=user.email,received_at=now())
    db.add(reading)
    try:db.flush()
    except IntegrityError:
        db.rollback()
        again=db.scalar(select(MonitorReading).where(MonitorReading.furnace_id==furnace.id,MonitorReading.seq==data.seq))
        if again:return {'result':'duplicate','message':f'{furnace.name}第{data.seq}件已上报过，重复上报未计入','alarm':None,'furnace':furnace_status(db,plan,furnace)}
        raise HTTPException(409,'幂等键已被其他上报使用，请更换')
    outcome=_drain(db,plan,furnace)
    if outcome['alarm']:log(db,user,'monitor.alarm',plan.id,f"{outcome['alarm']['furnace']}第{outcome['alarm']['seq']}件首次报警")
    db.commit()
    if data.seq in outcome['counted']:
        message=f'{furnace.name}第{data.seq}件已计入（{"失准" if reading.inaccurate else "在阈值内"}）'
    else:
        message=f'{furnace.name}缺第{furnace.next_seq}件，第{data.seq}件已暂存等待补报'
    return {'result':'counted' if data.seq in outcome['counted'] else 'buffered','message':message,'alarm':outcome['alarm'],'furnace':furnace_status(db,plan,furnace)}

def submit_correction(db,user,plan_id,data):
    plan=get_plan(db,plan_id)
    furnace=_locked_furnace(db,plan,data.furnace_id)
    reading=db.scalar(select(MonitorReading).where(MonitorReading.furnace_id==furnace.id,MonitorReading.seq==data.seq))
    if not reading:raise HTTPException(404,'该序号尚无实测上报')
    if reading.state!='counted':raise HTTPException(422,'该序号尚未计入，请直接重新上报读数')
    if abs(reading.actual_minutes-data.corrected_minutes)<1e-9:raise HTTPException(422,'更正读数与已计入读数一致')
    db.add(MonitorCorrection(plan_id=plan.id,furnace_id=furnace.id,seq=reading.seq,piece_id=reading.piece_id,old_minutes=reading.actual_minutes,new_minutes=data.corrected_minutes,reason=data.reason.strip() or '读数更正',actor=user.email,created_at=now()))
    log(db,user,'monitor.reading_corrected',f'{plan.id}/{furnace.id}/{reading.seq}',f'{furnace.name}第{reading.seq}件 {reading.actual_minutes}→{data.corrected_minutes}分钟；已计入读数与既有报警不变')
    db.commit()
    return {'result':'correction_logged','message':'更正已留痕；已计入读数与既有报警保持不变','alarm':None,'furnace':furnace_status(db,plan,furnace)}

def list_corrections(db,plan_id):
    plan=get_plan(db,plan_id)
    names={f.id:f.name for f in db.scalars(select(MonitorFurnace).where(MonitorFurnace.plan_id==plan.id))}
    rows=db.scalars(select(MonitorCorrection).where(MonitorCorrection.plan_id==plan.id).order_by(MonitorCorrection.id.desc()))
    return [{'id':c.id,'furnace':names.get(c.furnace_id,str(c.furnace_id)),'seq':c.seq,'piece_id':c.piece_id,'old_minutes':c.old_minutes,'new_minutes':c.new_minutes,'reason':c.reason,'actor':c.actor,'created_at':c.created_at} for c in rows]
