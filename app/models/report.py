from pydantic import BaseModel
from datetime import datetime

class ReportMetadata(BaseModel):
    report_id: str
    prediction_id: str
    user_id: str
    generated_at: datetime
    file_type: str = "pdf"
