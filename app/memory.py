from typing import Dict, List
from datetime import datetime, timedelta

class ConversationMemory:
    def __init__(self, ttl_minutes=60):
        self.sessions: Dict[str, Dict] = {}
        self.ttl = timedelta(minutes=ttl_minutes)
        
    def _clean_expired(self):
        now = datetime.now()
        expired = [sid for sid, data in self.sessions.items() 
                  if now - data['last_accessed'] > self.ttl]
        for sid in expired:
            del self.sessions[sid]
    
    def add_message(self, session_id: str, role: str, content: str):
        self._clean_expired()
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                'history': [],
                'created': datetime.now()
            }
            
        self.sessions[session_id]['history'].append({
            'role': role,
            'content': content,
            'timestamp': datetime.now()
        })
        self.sessions[session_id]['last_accessed'] = datetime.now()
        
    def get_history(self, session_id: str, max_messages=10) -> List[Dict]:
        self._clean_expired()
        if session_id not in self.sessions:
            return []
        return self.sessions[session_id]['history'][-max_messages:]
    
    def clear_session(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]