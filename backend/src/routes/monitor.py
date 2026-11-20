from fastapi import APIRouter,Depends
from ..config.database import db_session
from ..schemas.monitor import PlanInput,ReadingInput,CorrectionInput
from ..services.auth import current_user,writer
from ..controllers.monitor import MonitorController as C
router=APIRouter()
@router.get('/monitor/plans')
def plans(db=Depends(db_session),u=Depends(current_user)):return C.list(db)
@router.post('/monitor/plans')
def create(data:PlanInput,db=Depends(db_session),u=Depends(writer)):return C.create(db,u,data)
@router.get('/monitor/plans/{id}')
def detail(id:int,db=Depends(db_session),u=Depends(current_user)):return C.detail(db,id)
@router.post('/monitor/plans/{id}/readings')
def reading(id:int,data:ReadingInput,db=Depends(db_session),u=Depends(writer)):return C.reading(db,u,id,data)
@router.post('/monitor/plans/{id}/corrections')
def correct(id:int,data:CorrectionInput,db=Depends(db_session),u=Depends(writer)):return C.correct(db,u,id,data)
@router.get('/monitor/plans/{id}/corrections')
def corrections(id:int,db=Depends(db_session),u=Depends(current_user)):return C.corrections(db,id)
