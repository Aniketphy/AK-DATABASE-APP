import pandas as pd
import numpy as np
from typing import Dict, List, Any, Tuple
from datetime import datetime
import hashlib
from utils.data_cleaning import DataCleaner
from utils.location_intel import LocationIntel
from utils.classification import DataClassifier

class DataIngestion:
    def __init__(self):
        self.cleaner = DataCleaner()
        self.location_intel = LocationIntel()
        self.classifier = DataClassifier()
    
    def detect_columns(self, df: pd.DataFrame) -> Dict[str, str]:
        """Detect which columns contain what type of data"""
        column_mapping = {
            "name": ["name", "full name", "consumer name", "applicant", "customer name"],
            "mobile": ["mobile", "phone", "contact", "phone number", "cell"],
            "email": ["email", "e-mail", "email id", "mail"],
            "address": ["address", "residence", "property address", "location"],
            "pincode": ["pincode", "pin", "zip", "postal code"],
            "city": ["city", "town", "locality"],
            "gender": ["gender", "sex"],
            "age": ["age", "age group"],
            "income": ["income", "salary"]
        }
        
        detected = {}
        df_columns_lower = {col.lower(): col for col in df.columns}
        
        for data_type, patterns in column_mapping.items():
            for pattern in patterns:
                if pattern in df_columns_lower:
                    detected[data_type] = df_columns_lower[pattern]
                    break
        
        return detected
    
    def process_file(self, file_path: str, intake_data: Dict) -> Tuple[List[Dict], Dict]:
        """Process an Excel file and return cleaned records"""
        
        # Read Excel file
        try:
            df = pd.read_excel(file_path)
        except Exception as e:
            return [], {"success": False, "error": f"Failed to read file: {str(e)}"}
        
        # Detect columns
        column_mapping = self.detect_columns(df)
        
        # Process each row
        processed_records = []
        stats = {"total": len(df), "processed": 0, "errors": 0}
        
        for idx, row in df.iterrows():
            try:
                record = self.process_row(row, column_mapping, intake_data)
                if record:
                    processed_records.append(record)
                    stats["processed"] += 1
            except Exception as e:
                stats["errors"] += 1
                continue
        
        stats["success"] = True
        return processed_records, stats
    
    def process_row(self, row: pd.Series, column_mapping: Dict, intake_data: Dict) -> Dict:
        """Process a single row of data"""
        
        # Extract basic data
        name = row.get(column_mapping.get("name", ""), "") if column_mapping.get("name") else ""
        mobile_raw = row.get(column_mapping.get("mobile", ""), "") if column_mapping.get("mobile") else ""
        email_raw = row.get(column_mapping.get("email", ""), "") if column_mapping.get("email") else ""
        address_raw = row.get(column_mapping.get("address", ""), "") if column_mapping.get("address") else ""
        
        # Clean data
        mobile, is_valid_mobile = self.cleaner.clean_mobile(mobile_raw)
        if not is_valid_mobile:
            mobile = ""
        
        email, is_placeholder = self.cleaner.clean_email(email_raw)
        
        # Split name
        name_parts = self.cleaner.split_name(name)
        
        # Location intelligence
        location_info = self.location_intel.extract_location(address_raw, "")
        
        # Classification
        record_for_classification = {
            "name": name,
            "address": address_raw,
            "source_type": intake_data.get("source", "")
        }
        category = self.classifier.classify_record(record_for_classification)
        
        # Generate master ID
        unique_string = f"{mobile}_{name}_{email}" if mobile else f"{name}_{address_raw}"
        master_id = hashlib.md5(unique_string.encode()).hexdigest()
        
        # Build final record
        record = {
            "master_id": master_id,
            "name": name,
            "first_name": name_parts["first"],
            "last_name": name_parts["last"],
            "mobile": mobile,
            "email": email,
            "address": self.cleaner.clean_address(address_raw),
            "pincode": location_info.get("pincode", ""),
            "city": location_info.get("city", ""),
            "state": location_info.get("state", ""),
            "zone": location_info.get("zone", ""),
            "cluster": location_info.get("cluster", ""),
            "region": location_info.get("region", ""),
            "category": category,
            "source_type": intake_data.get("source", ""),
            "source_file": intake_data.get("file_name", ""),
            "date_sourced": intake_data.get("date_sourced", datetime.now().date()),
            "raw_data": row.to_dict(),
            "is_duplicate": False
        }
        
        return record
