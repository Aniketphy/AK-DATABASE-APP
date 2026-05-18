import os
from supabase import create_client, Client
from dotenv import load_dotenv
import pandas as pd
from typing import Dict, List, Any, Optional

load_dotenv()

class SupabaseClient:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        self.service_key = os.getenv("SUPABASE_SERVICE_KEY")
        
        if not self.url or not self.key:
            raise ValueError("Supabase credentials not found in .env file")
        
        self.client: Client = create_client(self.url, self.key)
        self.table_name = "real_estate_records"
        
    def create_table_if_not_exists(self):
        """Create the main table using SQL (run once in Supabase SQL editor)"""
        sql = """
        CREATE TABLE IF NOT EXISTS real_estate_records (
            id BIGSERIAL PRIMARY KEY,
            master_id TEXT UNIQUE,
            name TEXT,
            first_name TEXT,
            last_name TEXT,
            mobile TEXT,
            email TEXT,
            address TEXT,
            pincode TEXT,
            city TEXT,
            state TEXT,
            zone TEXT,
            cluster TEXT,
            region TEXT,
            gender TEXT,
            age_group TEXT,
            income_group TEXT,
            category TEXT,
            source_type TEXT,
            source_file TEXT,
            date_sourced DATE,
            date_added TIMESTAMP DEFAULT NOW(),
            is_duplicate BOOLEAN DEFAULT FALSE,
            duplicate_of TEXT,
            raw_data JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_mobile ON real_estate_records(mobile);
        CREATE INDEX IF NOT EXISTS idx_pincode ON real_estate_records(pincode);
        CREATE INDEX IF NOT EXISTS idx_category ON real_estate_records(category);
        CREATE INDEX IF NOT EXISTS idx_city ON real_estate_records(city);
        CREATE INDEX IF NOT EXISTS idx_date_added ON real_estate_records(date_added);
        """
        # Note: Run this SQL in Supabase SQL editor manually
        
    async def insert_records(self, records: List[Dict]) -> Dict:
        """Insert multiple records into Supabase"""
        try:
            result = self.client.table(self.table_name).insert(records).execute()
            return {"success": True, "count": len(result.data)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def check_existing_mobiles(self, mobiles: List[str]) -> set:
        """Check which mobiles already exist in database"""
        try:
            response = self.client.table(self.table_name)\
                .select("mobile")\
                .in_("mobile", mobiles)\
                .execute()
            return {record["mobile"] for record in response.data}
        except Exception as e:
            print(f"Error checking existing mobiles: {e}")
            return set()
    
    def search_records(self, query: str, filters: Dict = None, limit: int = 100) -> List[Dict]:
        """Search records with filters"""
        try:
            table = self.client.table(self.table_name)
            
            # Search across multiple fields
            if query:
                table = table.or_(
                    f"name.ilike.%{query}%,"
                    f"mobile.ilike.%{query}%,"
                    f"email.ilike.%{query}%,"
                    f"address.ilike.%{query}%,"
                    f"pincode.ilike.%{query}%"
                )
            
            # Apply filters
            if filters:
                for key, value in filters.items():
                    if value and value != "All":
                        table = table.eq(key, value)
            
            # Order and limit
            result = table.order("date_added", desc=True).limit(limit).execute()
            return result.data
        except Exception as e:
            print(f"Search error: {e}")
            return []
    
    def get_dashboard_stats(self) -> Dict:
        """Get dashboard statistics"""
        try:
            total = self.client.table(self.table_name).select("count", count="exact").execute()
            unique_mobiles = self.client.table(self.table_name)\
                .select("mobile", count="exact")\
                .neq("is_duplicate", True)\
                .execute()
            
            # Category breakdown
            categories = {}
            for cat in ["Non-Real Estate", "Property Seeker", "Real Estate Trade"]:
                count = self.client.table(self.table_name)\
                    .select("count", count="exact")\
                    .eq("category", cat)\
                    .execute()
                categories[cat] = count.count
            
            return {
                "total_records": total.count,
                "unique_records": unique_mobiles.count,
                "categories": categories
            }
        except Exception as e:
            print(f"Error getting stats: {e}")
            return {}
