import pandas as pd
import re
from config.locations import PUNE_LOCATIONS, CITIES_INDIA, INDIAN_STATES
from typing import Dict, Tuple

class LocationIntel:
    def __init__(self):
        self.pune_locations = PUNE_LOCATIONS
        self.cities = CITIES_INDIA
        self.states = INDIAN_STATES
    
    def extract_location(self, address: str, pincode: str = "") -> Dict:
        """Extract location information from address and pincode"""
        result = {
            "city": "", "state": "", "pincode": "",
            "zone": "", "cluster": "", "region": ""
        }
        
        # If pincode is provided, use it first
        if pincode and pincode.isdigit():
            result["pincode"] = pincode
            # Map pincode to city
            for city, info in self.cities.items():
                if info["pincode_range"][0] <= int(pincode) <= info["pincode_range"][1]:
                    result["city"] = city
                    result["state"] = info["state"]
                    result["region"] = info["region"]
                    break
        
        # Extract from address if available
        if address:
            address_lower = address.lower()
            
            # Check for Pune areas
            for area, info in self.pune_locations.items():
                if area.lower() in address_lower:
                    result["city"] = "Pune"
                    result["zone"] = info["zone"]
                    result["cluster"] = info["cluster"]
                    if not result["pincode"]:
                        result["pincode"] = info["pincode"]
                    break
            
            # Check for other cities
            for city in self.cities.keys():
                if city.lower() in address_lower:
                    result["city"] = city
                    result["state"] = self.cities[city]["state"]
                    result["region"] = self.cities[city]["region"]
                    break
            
            # Extract pincode from address
            pincode_match = re.search(r'\b\d{6}\b', address)
            if pincode_match and not result["pincode"]:
                result["pincode"] = pincode_match.group()
        
        return result
    
    def map_pincode_to_location(self, pincode: str) -> Dict:
        """Map pincode to city, state, region"""
        if not pincode or not pincode.isdigit():
            return {"city": "", "state": "", "region": ""}
        
        pincode_int = int(pincode[:3])  # First 3 digits of pincode
        
        # Common pincode ranges for major cities
        if 400001 <= pincode_int <= 400099:
            return {"city": "Mumbai", "state": "Maharashtra", "region": "West"}
        elif 110001 <= pincode_int <= 110099:
            return {"city": "Delhi", "state": "Delhi", "region": "North"}
        elif 560001 <= pincode_int <= 560099:
            return {"city": "Bangalore", "state": "Karnataka", "region": "South"}
        elif 500001 <= pincode_int <= 500099:
            return {"city": "Hyderabad", "state": "Telangana", "region": "South"}
        elif 600001 <= pincode_int <= 600099:
            return {"city": "Chennai", "state": "Tamil Nadu", "region": "South"}
        elif 411001 <= pincode_int <= 411099:
            return {"city": "Pune", "state": "Maharashtra", "region": "West"}
        
        return {"city": "", "state": "", "region": ""}
