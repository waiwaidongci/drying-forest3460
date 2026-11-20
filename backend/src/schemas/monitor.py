from pydantic import BaseModel,Field
class PredictionInput(BaseModel):
    piece_id:str=Field(min_length=1,max_length=120)
    predicted_minutes:float=Field(gt=0,allow_inf_nan=False)
class FurnaceInput(BaseModel):
    name:str=Field(min_length=1,max_length=160)
    predictions:list[PredictionInput]=Field(min_length=1)
class PlanInput(BaseModel):
    name:str=Field(min_length=2,max_length=160)
    alpha:float=Field(gt=0,lt=1,allow_inf_nan=False)
    threshold_minutes:float=Field(gt=0,allow_inf_nan=False)
    furnaces:list[FurnaceInput]=Field(min_length=1)
class ReadingInput(BaseModel):
    furnace_id:int
    seq:int=Field(ge=1)
    actual_minutes:float=Field(gt=0,allow_inf_nan=False)
    idempotency_key:str|None=Field(default=None,max_length=120)
class CorrectionInput(BaseModel):
    furnace_id:int
    seq:int=Field(ge=1)
    corrected_minutes:float=Field(gt=0,allow_inf_nan=False)
    reason:str=Field(default='',max_length=600)
