from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
from datetime import datetime
import os
from dotenv import load_dotenv
from .database import DatabaseManager
from .chatbot import VehicleChatbot
from .memory import ConversationMemory

# Load environment variables
load_dotenv()

app = FastAPI()

# Database configuration
DB_CONFIG = {
    "dbname": "vehicle_inspection_db",
    "user": "postgres",
    "password": "1234",
    "host": "localhost",
    "port": "5432"
}

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
db = DatabaseManager(DB_CONFIG)
chatbot = VehicleChatbot()
memory = ConversationMemory()

class ChatRequest(BaseModel):
    query: str
    session_id: str = None

class ChatResponse(BaseModel):
    response: str
    session_id: str
    timestamp: str

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    try:
        session_id = request.session_id or str(uuid.uuid4())
        response = chatbot.process_query(request.query, session_id)
        return ChatResponse(
            response=response,
            session_id=session_id,
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/session/{session_id}/clear")
async def clear_session(session_id: str):
    memory.clear_session(session_id)
    return {"status": "session cleared"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)