from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class ChatMessageBase(BaseModel):
    text: str
    sender: str  # 'user' or 'bot'

class ChatMessageCreate(ChatMessageBase):
    user_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ChatMessageResponse(ChatMessageBase):
    id: str = Field(alias="_id")
    user_id: str
    timestamp: datetime

    class Config:
        populate_by_name = True
