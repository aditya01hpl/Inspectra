import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.preprocessing import normalize
import json
import os

class SemanticSearch:
    def __init__(self, db_manager):
        self.db = db_manager
        self.model = SentenceTransformer('nomic-ai/nomic-embed-text-v1', trust_remote_code=True)
        self.index, self.mapping = self.load_index()
    
    def load_index(self):
        """Load or create FAISS index"""
        index_file = "vehicle_inspections_faiss.index"
        mapping_file = "faiss_mapping.json"
        
        if os.path.exists(index_file) and os.path.exists(mapping_file):
            index = faiss.read_index(index_file)
            with open(mapping_file, "r") as f:
                mapping = json.load(f)
            print("Loaded existing FAISS index")
            return index, mapping
        
        print("Building new FAISS index...")
        return self.build_index()
    
    def build_index(self):
        """Create FAISS index from damage descriptions"""
        records = self.db.execute_query(
            "SELECT id, damage_descriptions FROM inspections"
        )
        
        if not records:
            raise Exception("No records for indexing")
        
        # Prepare embeddings
        texts = [rec["damage_descriptions"] for rec in records]
        embeddings = self.model.encode(texts, convert_to_tensor=False)
        embeddings = normalize(embeddings, norm='l2', axis=1)
        
        # Create index
        dimension = embeddings.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index.add(embeddings.astype(np.float32))
        
        # Save artifacts
        faiss.write_index(index, "vehicle_inspections_faiss.index")
        mapping = {str(i): rec["id"] for i, rec in enumerate(records)}
        with open("faiss_mapping.json", "w") as f:
            json.dump(mapping, f)
        
        print(f"Built index with {len(records)} records")
        return index, mapping
    
    def search(self, query, k=5):
        """Perform semantic search"""
        # Embed query
        query_embed = self.model.encode([query], convert_to_tensor=False)
        query_embed = normalize(query_embed, norm='l2', axis=1).astype(np.float32)
        
        # Search index
        distances, indices = self.index.search(query_embed, k)
        
        # Get matching record IDs
        record_ids = [self.mapping[str(idx)] for idx in indices[0]]
        
        # Retrieve full records
        placeholders = ','.join(['%s'] * len(record_ids))
        results = self.db.execute_query(
            f"SELECT id, vin, damage_descriptions, source_file "
            f"FROM inspections WHERE id IN ({placeholders})",
            record_ids
        )
        
        return results