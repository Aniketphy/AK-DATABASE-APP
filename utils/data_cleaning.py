import pandas as pd
import numpy as np
import re
import phonenumbers
from typing import Dict, Any, Tuple

class DataCleaner:
    @staticmethod
    def clean_mobile(number: str) -> Tuple[str, bool]:
        """Clean and standardize mobile numbers"""
        if pd.isna(number):
            return "", False
        
        number = str(number).strip()
        # Remove special characters
        number = re.sub(r'[^0-9+]', '', number)
        
        # Handle country codes
        if number.startswith('+91'):
            number = number[3:]
        elif number.startswith('91'):
            number = number[2:]
        elif number.startswith('0'):
            number = number[1:]
        
        # Check if valid Indian mobile number
        if len(number) == 10 and number.isdigit():
            return number, True
        elif len(number) == 12 and number.isdigit():
            return number[-10:], True
        
        return "", False
    
    @staticmethod
    def clean_email(email: str) -> Tuple[str, bool]:
        """Clean and validate email"""
        if pd.isna(email):
            return "", False
        
        email = str(email).lower().strip()
        
        # Flag placeholder emails
        placeholder_patterns = [
            r'email_\d+@email\.com',
            r'test@.*\.com',
            r'user\d+@example\.com'
        ]
        
        is_placeholder = any(re.match(pattern, email) for pattern in placeholder_patterns)
        
        # Basic email validation
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        is_valid = bool(re.match(email_pattern, email))
        
        return email if is_valid else "", is_placeholder
    
    @staticmethod
    def split_name(full_name: str) -> Dict[str, str]:
        """Split full name into first, middle, last"""
        if pd.isna(full_name):
            return {"first": "", "middle": "", "last": ""}
        
        name_parts = str(full_name).strip().split()
        
        if len(name_parts) == 1:
            return {"first": name_parts[0], "middle": "", "last": ""}
        elif len(name_parts) == 2:
            return {"first": name_parts[0], "middle": "", "last": name_parts[1]}
        else:
            return {
                "first": name_parts[0],
                "middle": " ".join(name_parts[1:-1]),
                "last": name_parts[-1]
            }
    
    @staticmethod
    def standardize_pincode(pincode: str) -> str:
        """Standardize pincode to 6 digits"""
        if pd.isna(pincode):
            return ""
        
        pincode = str(pincode).strip()
        pincode = re.sub(r'[^0-9]', '', pincode)
        
        if len(pincode) >= 6:
            return pincode[:6]
        return ""
    
    @staticmethod
    def clean_address(address: str) -> str:
        """Clean and standardize address"""
        if pd.isna(address):
            return ""
        
        address = str(address).strip()
        # Remove extra spaces
        address = re.sub(r'\s+', ' ', address)
        # Capitalize properly (but keep common abbreviations)
        words = address.split()
        words = [w.capitalize() if w.lower() not in ['and', 'of', 'the', 'in', 'at'] else w.lower() for w in words]
        
        return ' '.join(words)
