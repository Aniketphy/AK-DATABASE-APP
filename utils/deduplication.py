from typing import List, Dict, Set
from difflib import SequenceMatcher

class Deduplication:
    def __init__(self, supabase_client):
        self.supabase = supabase_client
    
    def find_duplicates(self, new_records: List[Dict]) -> List[Dict]:
        """Find duplicates in new records compared to existing database"""
        
        # Extract all mobiles from new records
        mobiles = [r["mobile"] for r in new_records if r["mobile"]]
        
        # Check which mobiles already exist
        existing_mobiles = self.supabase.check_existing_mobiles(mobiles)
        
        # Mark duplicates
        for record in new_records:
            if record["mobile"] and record["mobile"] in existing_mobiles:
                record["is_duplicate"] = True
                record["duplicate_of"] = record["mobile"]  # Simplified - should find master record
        
        # Also check for name+address duplicates (without mobile)
        # This would require more sophisticated matching
        
        return new_records
    
    def merge_records(self, record1: Dict, record2: Dict) -> Dict:
        """Merge two duplicate records, preferring non-null values"""
        merged = record1.copy()
        
        for key in record2:
            if key in merged:
                if not merged[key] and record2[key]:
                    merged[key] = record2[key]
            else:
                merged[key] = record2[key]
        
        return merged
    
    def similarity_score(self, text1: str, text2: str) -> float:
        """Calculate similarity between two text strings"""
        if not text1 or not text2:
            return 0.0
        return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
