import psycopg2
import json

class DatabaseManager:
    def __init__(self, config):
        self.config = config or {
            "dbname": "vehicle_inspection_db",
            "user": "postgres",
            "password": "1234",  
            "host": "localhost",
            "port": "5432"
        }
        self.conn = self.connect()
        self.schema = self.get_schema_info()
    
    def connect(self):
        """Establish PostgreSQL connection"""
        return psycopg2.connect(**self.config)
    
    def get_schema_info(self):
        """Retrieve schema with descriptions"""
        return {
            "table": "inspections",
            "columns": [
                {"name": "record_id", "desc": "Unique identifier for each inspection record"},
                {"name": "vin", "desc": "Vehicle Identification Number (17-character code)"},
                {"name": "inspection_date", "desc": "Date of inspection"},
                {"name": "inspection_time", "desc": "Time of inspection"},
                {"name": "inspection_type", "desc": "Two-character inspection category code"},
                {"name": "inspector_name", "desc": "Full name of inspector"},
                {"name": "ramp", "desc": "Facility location where inspection took place"},
                {"name": "railcar_number", "desc": "Railcar identifier (starts with carrier prefix)"},
                {"name": "bay_location", "desc": "Code for specific bay/stall in yard"},
                {"name": "mfg_model", "desc": "Manufacturer and model (comma separated)"},
                {"name": "damage_comments", "desc": "Brief damage description comments."},
                {"name": "vehicle_comments", "desc": "General vehicle condition remarks"},
                {"name": "damage_count", "desc": "Number of distinct damage instances"},
                {"name": "aiag_codes", "desc": "AIAG-standard damage codes (space separated)"},
                {"name": "damage_descriptions", "desc": "Standardized damage label descriptions along with vehicle part and severity."},
                {"name": "source_file", "desc": "Original PDF/document source filename"}
            ]
        }
    
    def execute_query(self, sql, params=None):
        """Execute SQL query and return serializable results"""
        with self.conn.cursor() as cur:
            try:
                self.conn.rollback() 
                cur.execute(sql, params)
                
                if cur.description:
                    columns = [desc[0] for desc in cur.description]
                    results = []
                    for row in cur.fetchall():
                        row_dict = {}
                        for i, col in enumerate(columns):
                            value = row[i]
                            
                            if hasattr(value, 'isoformat'):  
                                row_dict[col] = value.isoformat()
                            else:
                                row_dict[col] = value
                        results.append(row_dict)
                    return results
                return []
            except Exception as e:
                print(f"SQL error: {e}")
                self.conn.rollback()
                return None  # Differentiate between empty results and errors
    
    def close(self):
        """Close database connection"""
        self.conn.close()