import pandas as pd
import re
from config.keywords import TRADE_KEYWORDS, SEEKER_KEYWORDS

class DataClassifier:
    def __init__(self):
        self.trade_keywords = TRADE_KEYWORDS
        self.seeker_keywords = SEEKER_KEYWORDS
    
    def classify_record(self, record: dict) -> str:
        """Classify record into 3 categories"""
        # Combine all text fields for analysis
        text_to_analyze = " ".join([
            str(record.get("name", "")),
            str(record.get("address", "")),
            str(record.get("notes", "")),
            str(record.get("source_type", ""))
        ]).lower()
        
        # Check for Trade (brokers, agents, developers)
        if any(keyword in text_to_analyze for keyword in self.trade_keywords):
            return "Real Estate Trade"
        
        # Check for Property Seeker (leads, enquiries)
        if any(keyword in text_to_analyze for keyword in self.seeker_keywords):
            return "Property Seeker"
        
        # MSEB data is typically Non-Real Estate
        if "mseb" in text_to_analyze or "consumer" in text_to_analyze:
            return "Non-Real Estate"
        
        # Default to Non-Real Estate if no clear signals
        return "Non-Real Estate"
    
    def infer_gender(self, name: str) -> str:
        """Infer gender from name (basic implementation)"""
        if pd.isna(name):
            return ""
        
        name_lower = name.lower()
        
        # Common Indian name patterns
        male_patterns = ['kumar', 'singh', 'sharma', 'verma', 'patel']
        female_patterns = ['kumari', 'devi', 'bai', 'ben']
        
        if any(pattern in name_lower for pattern in male_patterns):
            return "Male"
        elif any(pattern in name_lower for pattern in female_patterns):
            return "Female"
        
        return ""
    
    def infer_age_group(self, age: any) -> str:
        """Infer age group from age or DOB"""
        if pd.isna(age):
            return ""
        
        try:
            age_int = int(age)
            if age_int < 18:
                return "Under 18"
            elif age_int < 30:
                return "18-29"
            elif age_int < 45:
                return "30-44"
            elif age_int < 60:
                return "45-59"
            else:
                return "60+"
        except:
            return ""
    
    def infer_income_group(self, income: any) -> str:
        """Infer income group from income data"""
        if pd.isna(income):
            return ""
        
        try:
            income_int = float(income)
            # Assuming monthly income in INR
            if income_int < 25000:
                return "Low (<25k)"
            elif income_int < 50000:
                return "Lower-Middle (25k-50k)"
            elif income_int < 100000:
                return "Middle (50k-1L)"
            elif income_int < 250000:
                return "Upper-Middle (1L-2.5L)"
            else:
                return "High (>2.5L)"
        except:
            return ""
