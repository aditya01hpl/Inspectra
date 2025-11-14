from pydantic import BaseModel
from typing import List, Dict, Optional

class Message(BaseModel):
    role: str  # "user", "assistant", or "system"
    content: str
    timestamp: str

class Session(BaseModel):
    session_id: str
    created: str
    last_accessed: str
    history: List[Message]