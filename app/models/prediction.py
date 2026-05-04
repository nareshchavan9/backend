from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class PredictionBase(BaseModel):
    prediction: str
    confidence: float
    notes: Optional[str] = ""

class PredictionCreate(PredictionBase):
    user_id: str
    image_path: str

class PredictionResponse(PredictionBase):
    id: str = Field(alias="_id")
    user_id: str
    image_path: str
    timestamp: datetime

    class Config:
        populate_by_name = True
