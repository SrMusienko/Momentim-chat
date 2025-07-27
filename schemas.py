from pydantic import BaseModel
from datetime import datetime

class MessageCreate(BaseModel):
    content: str

class MessageResponse(BaseModel):
    id: int
    chat_id: int
    sender: str
    content: str
    timestamp: datetime

    class Config:
        from_attributes = True
        orm_mode = True

class ChatResponse(BaseModel):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True
        orm_mode = True