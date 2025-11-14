from .database import DatabaseManager
from .semantic_search import SemanticSearch
from .llm_interface import LLMInterface
from .memory import ConversationMemory
import json
from typing import Dict, List, Optional
from datetime import datetime, date


def clean_datetime(obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: clean_datetime(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean_datetime(i) for i in obj]
        else:
            return obj
        
class VehicleChatbot:
    def __init__(self, db_config=None):
        self.db = DatabaseManager(db_config)
        self.semantic = SemanticSearch(self.db)
        self.llm = LLMInterface()
        self.schema = self.db.get_schema_info()
        self.memory = ConversationMemory()
        self.query_cache = {}
        self.error_count = 0

    def _is_destructive_query(self, query: str) -> bool:
        destructive_keywords = ["delete", "drop", "truncate", "alter", "update", "insert"]
        return any(keyword in query.lower() for keyword in destructive_keywords)

    def process_query(self, query: str, session_id: str = None) -> str:
        """Main query processing pipeline"""
        try:
            # Check cache and initialize
            cached = self._get_cached_response(query)
            if cached:
                return cached

            if self._is_destructive_query(query):
                return "I can only provide read-only inspection data."

            print(f"\n{'='*50}\nProcessing: '{query}'\n{'='*50}")

            # Route query
            routing = self._route_query(query)
            semantic_matches = self._get_semantic_matches(query, routing)

            # Execute query flow
            response = self._execute_query_flow(query, routing, semantic_matches, session_id)
            self.error_count = 0
            return response

        except Exception as e:
            self.error_count += 1
            return self._handle_error(e, query, session_id)

    def _get_cached_response(self, query: str) -> Optional[str]:
        """cache lookup"""
        normalized = query.lower().strip()
        for cached_query, response in self.query_cache.items():
            if cached_query.lower().strip() == normalized:
                return response
        return None

    def _route_query(self, query: str) -> Dict:
        """Handle query routing with logging"""
        routing = self.llm.route_query(query, self.schema)
        print(f"[ROUTE] {'Semantic' if routing['use_semantic'] else 'SQL'}: {routing['reason']}")
        return routing

    def _get_semantic_matches(self, query: str, routing: Dict) -> Optional[List]:
        """Perform semantic search if needed"""
        if routing.get("use_semantic", False):
            matches = self.semantic.search(query)
            print(f"[SEMANTIC] Found {len(matches)} matches")
            return matches
        return None

    def _execute_query_flow(self, query: str, routing: Dict, 
                          semantic_matches: Optional[List], 
                          session_id: Optional[str]) -> str:
        """Full query execution workflow"""
        sql = self.llm.generate_sql(query, self.schema, semantic_matches)
        if not sql:
            return "I need more details to answer that."

        print(f"[SQL] {sql}")
        results = self.db.execute_query(sql)
        if not results:
            return self._handle_empty_results(query, session_id)
        results = clean_datetime(results)
        history = self.memory.get_history(session_id) if session_id else None
        history = clean_datetime(history) if history else None
        print(f"[RESULTS] {len(results)} records")
        enrichment = self._enrich_results(results, semantic_matches)
        enrichment = clean_datetime(self._enrich_results(results, semantic_matches))
        response = self.llm.format_response(query, results, enrichment, 
                                          history)

        self._update_state(query, response, session_id)
        print(f"[RESPONSE] {response}")
        return response

    def _enrich_results(self, results: List, semantic_matches: Optional[List]) -> Dict:
        """Enhanced result enrichment"""
        if not results:
            return {}

        enrichment = {
            "source_files": set(),
            "damage_types": {},
            "inspectors": {}
        }

        for rec in results:
            # Source files
            if src := rec.get("source_file"):
                enrichment["source_files"].add(src)
            
            # Damage analysis
            if damage := rec.get("damage_descriptions", ""):
                damage_type = damage.split('-')[0].strip().lower()
                enrichment["damage_types"][damage_type] = enrichment["damage_types"].get(damage_type, 0) + 1
            
            # Inspector analysis
            if inspector := rec.get("inspector_name", ""):
                enrichment["inspectors"][inspector.lower()] = enrichment["inspectors"].get(inspector.lower(), 0) + 1

        return {
            "source_files": [{"file": f} for f in sorted(enrichment["source_files"])[:3]],
            "top_damage": max(enrichment["damage_types"].items(), key=lambda x: x[1], default=("none", 0)),
            "top_inspector": max(enrichment["inspectors"].items(), key=lambda x: x[1], default=("unknown", 0)),
            "record_count": len(results)
        }

    def _handle_empty_results(self, query: str, session_id: Optional[str]) -> str:
        """Intelligent empty result handling"""
        if self.error_count > 2:
            return "I'm having trouble finding that information. Please try different criteria."

        history = self.memory.get_history(session_id) if session_id else []
        suggestion = self._generate_suggestion(query, history)
        return f"No matching records found. {suggestion}"

    def _generate_suggestion(self, query: str, history: List) -> str:
        """Context-aware query suggestions"""
        query_lower = query.lower()
        if "vin" in query_lower:
            return "Please verify the VIN number."
        elif any(word in query_lower for word in ["date", "month", "year"]):
            return "Try adjusting the date range."
        elif history:
            last_query = history[-1].get("content", "").lower()
            if "model" in last_query:
                return "Try specifying the manufacturer (e.g., 'Ford F150')."
        return "Try being more specific with your criteria."

    def _update_state(self, query: str, response: str, session_id: Optional[str]):
        """Update conversation state"""
        self.query_cache[query] = response
        if session_id:
            self.memory.add_message(session_id, "assistant", response)

    def _handle_error(self, error: Exception, query: str, session_id: Optional[str]) -> str:
        """User-friendly error handling"""
        error_msg = str(error).lower()
        
        if "connection" in error_msg:
            msg = "Our systems are temporarily unavailable. Please try again later."
        elif any(word in error_msg for word in ["syntax", "sql"]):
            msg = "I didn't understand that request. Please try rephrasing."
        else:
            msg = "An unexpected error occurred. Please try again."

        if session_id:
            self.memory.add_message(session_id, "system", f"Error: {error_msg[:100]}")

        print(f"[ERROR] {error}")
        return msg

    def close(self):
        """Cleanup resources"""
        self.db.close()