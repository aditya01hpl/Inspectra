import requests
import json
import re
from typing import Dict, List, Optional


class LLMInterface:
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL = "qwen2.5-coder:3b"

    TEXT_COLUMNS = {
        'inspector_name': True,
        'ramp': True,
        'mfg_model': True,
        'damage_comments': True,
        'vehicle_comments': True,
        'damage_descriptions': True
    }

    EXAMPLE_QUERIES = [
        ("on which date maximum number of damages inspected?",
         "SELECT inspection_date, COUNT(*) as damage_count FROM inspections GROUP BY inspection_date ORDER BY damage_count DESC LIMIT 1"),
        ("which model has most damages?",
         "SELECT mfg_model, COUNT(*) as damage_count FROM inspections GROUP BY mfg_model ORDER BY damage_count DESC LIMIT 1"),
        ("Give me the VIN Number also the service history for VIN number ending with Number 9771",
         "SELECT vin, inspection_date, ramp, damage_descriptions FROM inspections WHERE vin LIKE '%9771' ORDER BY inspection_date DESC"),
        ("Which VIN Number is inspected for maximum number of times?",
         "SELECT vin, COUNT(*) as inspection_count FROM inspections GROUP BY vin ORDER BY inspection_count DESC LIMIT 1"),
        ("which was the last location for VIN '1FTFW4L80SFB31494'",
         "SELECT ramp FROM inspections WHERE vin = '1FTFW4L80SFB31494' ORDER BY inspection_date DESC LIMIT 1"),
        ("how many ramps VIN '1C6SRFJPXSN679771' has passed through",
         "SELECT COUNT(DISTINCT ramp) as ramp_count FROM inspections WHERE vin = '1C6SRFJPXSN679771'"),
        ("Give me most common damage types",
         "SELECT split_part(damage_descriptions, '-', 3) as damage_type, COUNT(*) as count FROM inspections GROUP BY damage_type ORDER BY count DESC LIMIT 5"),
        ("which vehicle part has maximum number of damages reported till date, what is that number",
         "SELECT split_part(damage_descriptions, '-', 1) || ',' || split_part(damage_descriptions, '-', 2) as part, COUNT(*) as damage_count FROM inspections GROUP BY part ORDER BY damage_count DESC LIMIT 1"),
        ("What damages were found on VIN 1C6SRFJPXSN679771",
         "SELECT damage_descriptions FROM inspections WHERE vin = '1C6SRFJPXSN679771' ORDER BY inspection_date DESC"),
        ("how many vehicles inspected by bryan?",
         "SELECT COUNT(*) as vehicle_count, source_file FROM inspections WHERE inspector_name ILIKE '%bryan%' GROUP BY source_file")
    ]

    def __init__(self):
        self._ensure_ollama_running()

    def _ensure_ollama_running(self):
        """Verify connection to Ollama server"""
        try:
            requests.get("http://localhost:11434", timeout=2)
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                "Ollama server not running. Please start it with 'ollama serve'")

    def _preprocess_query(self, query: str) -> str:
        """Normalize and sanitize user query"""
        query = query.lower().strip()
        return re.sub(r"[^a-z0-9\s\-_']", "", query)

    def generate(self, prompt: str, system: Optional[str] = None, json_mode: bool = False) -> Optional[str]:
        """Generate response with strict temperature control"""
        payload = {
            "model": self.MODEL,
            "prompt": prompt,
            "system": system,
            "format": "json" if json_mode else "",
            "stream": False,
            "options": {
                "temperature": 0.1
            }
        }

        try:
            response = requests.post(self.OLLAMA_URL, json=payload, timeout=60)
            response.raise_for_status()
            return response.json().get("response")
        except Exception as e:
            print(f"LLM Error: {str(e)}")
            return None

    def route_query(self, query: str, schema: Dict) -> Dict:
        """Determine query routing with case-insensitive handling"""
        processed_query = self._preprocess_query(query)
        prompt = f"""
        STRICT RULES:
        1. Use SQL for: counts, dates, VINs, models, locations, inspector names, service history/journey
        2. Use Semantic ONLY for: vague damage descriptions without identifiers
        3. NEVER use semantic if query contains: VIN, date, count, model, ramp, inspector
        
        Schema: {json.dumps(schema, indent=2)}
        Query: "{processed_query}"
        
        Respond ONLY with JSON: {{"use_semantic": bool, "reason": str}}
        """

        response = self.generate(prompt, json_mode=True)
        try:
            return json.loads(response) if response else {"use_semantic": False, "reason": "Fallback"}
        except json.JSONDecodeError:
            return {"use_semantic": False, "reason": "Invalid response"}

    def generate_sql(self, query: str, schema: Dict, semantic_matches: Optional[List] = None) -> Optional[str]:
        """Generate SQL with strict formatting rules"""
        processed_query = self._preprocess_query(query)

        context = f"""
        STRICT RULES:
        1. For text columns ({', '.join(self.TEXT_COLUMNS.keys())}):
           - Always use: column ILIKE '%value%'
           - Values must be lowercase
        2. For exact matches (VINs, dates):
           - Use: column = 'value'
        3. Include `source_file` in the SELECT clause unless the query uses aggregate functions and including it would require a `GROUP BY`. In such cases, omit `source_file` to avoid SQL errors.
        4. Date format: YYYY-MM-DD
        5. Never use JOINs
        6. Always add LIMIT 1000
        7. All the generated SQL queries should be compatible for postgresql v17
        
        Example Solutions:
        {self._get_example_solutions()}
        
        Schema: {json.dumps(schema, indent=2)}
        {"Semantic Matches: " + json.dumps(semantic_matches)[:500] if semantic_matches else ""}
        
        Query: "{processed_query}"
        Generate ONLY the PostgreSQL query:
        """

        raw_sql = self.generate(context)
        return self._clean_sql(raw_sql) if raw_sql else None

    def _get_example_solutions(self) -> str:
        """Format example queries with solutions"""
        return "\n".join([f"- {q[0]}\n  {q[1]};" for q in self.EXAMPLE_QUERIES])

    def _clean_sql(self, raw_sql: str) -> str:
        """Enforce SQL formatting rules"""
        sql = re.sub(r"```(sql)?|```", "", raw_sql).strip()

        # Enforce ILIKE for text columns
        for col in self.TEXT_COLUMNS:
            sql = re.sub(
                rf"{col}\s*=\s*'([^']+)'",
                f"{col} ILIKE '%\\1%'",
                sql,
                flags=re.IGNORECASE
            )

        # Ensure required clauses
        if "SELECT" not in sql.upper():
            sql = f"SELECT * {sql}"
        if "LIMIT" not in sql.upper():
            sql += " LIMIT 1000"

        return sql.split(';')[0] + ';'

    def _summarize_results(self, results: List[Dict], max_rows: int = 5) -> str:
        """Summarize top few rows of results for LLM formatting"""
        if not results:
            return "No records found."

        sample = results[:max_rows]
        keys = list(sample[0].keys())
        summary_lines = []

        for row in sample:
            line = ", ".join(
                f"{k}: {str(row.get(k, ''))}" for k in keys if k != "source_file")
            summary_lines.append(f"- {line}")

        return f"Record count {len(results)}, few sample records records are:\n" + "\n".join(summary_lines)

    def format_response(self, query: str, results: List, enrichment: Dict, history: Optional[List] = None) -> str:
        """Generate professional, contextual responses"""

        # History as short summary or question trail only — not full JSON
        history_context = ""
        if history:
            history_context = "Previous questions asked:\n" + "\n".join(
                f"- {h.get('question', '')}" for h in history[-3:]
            )

        context = f"""
        RESPONSE RULES:
        1. Structure:
        - Direct answer first 
        - Relevant statistics
        - Source context
        2. Tone: Professional, helpful
        3. Length: 3-7 sentences
        4. NEVER show: Empty lists, SQL, technical errors

        Current Query: {query}
        Results Summary: {self._summarize_results(results)}
        Sources: {enrichment.get('source_files', ['Unknown'])[:3]}
        Top Damage: {enrichment.get('top_damage', ('None', 0))[0]}
        Historical Context (use only if relevant): {history_context}
        Write a clear, concise, and helpful response based only on the current query and results. If the results contain sample records and they are very long, include only a few key details(vin, inspection_date, damage_descriptions) as examples. Do not infer anything beyond the data.:
        """

        response = self.generate(context)
        return self._polish_response(response or "I couldn't find that information. Please try rephrasing.")

    def _polish_response(self, response: str) -> str:
        """Ensure responses are client-ready"""
        response = re.sub(r"\[\d+\srecords?\]|\[\]|```", "", response)
        response = response.replace("From []", "").replace(
            "Found 1 record", "Found 1 inspection record")
        return response[0].upper() + response[1:] if response else "No results found"
