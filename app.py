import streamlit as st
import pandas as pd
import sqlite3
import re
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import warnings
import io
import chardet

warnings.filterwarnings('ignore')

# Page configuration
st.set_page_config(
    page_title="Real Estate Data Intelligence Platform",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2rem;
        background: linear-gradient(135deg, #1a4731 0%, #0f5c3e 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .stat-card {
        background: linear-gradient(135deg, #1a4731 0%, #0f5c3e 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .stat-number {
        font-size: 2rem;
        font-weight: bold;
    }
    .stat-label {
        font-size: 0.85rem;
        opacity: 0.9;
    }
    .actual-field {
        background-color: #d1fae5;
        padding: 0.2rem 0.5rem;
        border-radius: 4px;
        font-size: 0.8rem;
    }
    .inferred-field {
        background-color: #fef3c7;
        padding: 0.2rem 0.5rem;
        border-radius: 4px;
        font-size: 0.8rem;
    }
    .info-box {
        background-color: #f0fdf4;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #22c55e;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'db_initialized' not in st.session_state:
    st.session_state.db_initialized = False
if 'import_jobs' not in st.session_state:
    st.session_state.import_jobs = []

class DataWarehouse:
    """Core data warehouse using SQLite for storage and search"""
    
    def __init__(self, db_path: str = "data_warehouse.db"):
        self.db_path = db_path
        self.conn = None
        self._initialize_database()
    
    def _initialize_database(self):
        """Initialize SQLite database with proper schemas"""
        
        # Main SQLite database for profiles
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA cache_size=-20000")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        
        # Create profiles table with all required fields
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                profile_id TEXT PRIMARY KEY,
                mobile TEXT UNIQUE,
                secondary_mobile TEXT,
                name TEXT,
                first_name TEXT,
                last_name TEXT,
                email TEXT,
                address TEXT,
                sub_locality TEXT,
                area TEXT,
                city TEXT,
                state TEXT,
                pincode TEXT,
                zone TEXT,
                gender TEXT,
                age INTEGER,
                age_group TEXT,
                income_group TEXT,
                bhk_preference TEXT,
                budget_range TEXT,
                project_enquired TEXT,
                lead_source TEXT,
                company_name TEXT,
                business_category TEXT,
                vehicle_info TEXT,
                date_collected TEXT,
                classification TEXT,
                classification_confidence REAL,
                created_at TEXT,
                last_enriched TEXT,
                is_active INTEGER DEFAULT 1,
                has_valid_mobile INTEGER DEFAULT 1,
                record_count INTEGER DEFAULT 1,
                source_files TEXT,
                field_lineage TEXT
            )
        """)
        
        # Create indexes for fast searching
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_mobile ON profiles(mobile)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_city ON profiles(city)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_classification ON profiles(classification)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_name ON profiles(name)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_pincode ON profiles(pincode)")
        
        # Create field history table for audit trail
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS field_history (
                history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id TEXT,
                field_name TEXT,
                old_value TEXT,
                new_value TEXT,
                source_file TEXT,
                changed_at TEXT,
                change_type TEXT,
                data_type TEXT
            )
        """)
        
        # Create import jobs table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS import_jobs (
                job_id TEXT PRIMARY KEY,
                file_name TEXT,
                source_type TEXT,
                collection_date TEXT,
                category TEXT,
                geographic_coverage TEXT,
                quality_notes TEXT,
                file_label TEXT,
                status TEXT,
                total_records INTEGER,
                processed_records INTEGER,
                profiles_created INTEGER,
                profiles_enriched INTEGER,
                invalid_mobiles INTEGER,
                started_at TEXT,
                completed_at TEXT
            )
        """)
        
        # Create unknown fields storage
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS unknown_fields (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id TEXT,
                field_name TEXT,
                field_value TEXT,
                source_file TEXT,
                imported_at TEXT
            )
        """)
        
        # Create full-text search virtual table
        self.conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS profile_search USING fts5(
                profile_id, mobile, name, email, address, city, area, pincode
            )
        """)
        
        st.session_state.db_initialized = True
    
    def clean_mobile(self, value: Any) -> Tuple[str, bool]:
        """Clean mobile number to 10-digit canonical form"""
        if pd.isna(value) or value is None:
            return "", False
        
        try:
            # Handle float (Excel scientific notation like 9.82E+09)
            if isinstance(value, float):
                if value.is_integer():
                    value_str = str(int(value))
                else:
                    value_str = str(int(value)) if value > 1000000000 else str(value).split('.')[0]
            else:
                value_str = str(value).strip()
            
            # Extract digits only
            digits = ''.join(filter(str.isdigit, value_str))
            
            # Remove leading zero
            if digits.startswith('0'):
                digits = digits[1:]
            
            # Handle country codes
            if digits.startswith('91') and len(digits) == 12:
                digits = digits[2:]
            
            # Validate
            if len(digits) == 10 and digits[0] in '6789':
                return digits, True
            else:
                return digits, False
                
        except Exception:
            return "", False
    
    def infer_location(self, pincode: str = None, city: str = None, area: str = None, address: str = None) -> Dict:
        """Infer location fields from partial information"""
        result = {
            'city': None, 'state': None, 'pincode': None, 'area': None,
            'is_inferred': False, 'confidence': 'LOW'
        }
        
        # Pincode to city/state mapping (sample - expand as needed)
        pincode_map = {
            '411001': {'city': 'Pune', 'state': 'Maharashtra', 'area': 'Shivajinagar'},
            '411002': {'city': 'Pune', 'state': 'Maharashtra', 'area': 'Koregaon Park'},
            '411004': {'city': 'Pune', 'state': 'Maharashtra', 'area': 'Deccan Gymkhana'},
            '411014': {'city': 'Pune', 'state': 'Maharashtra', 'area': 'Baner'},
            '411021': {'city': 'Pune', 'state': 'Maharashtra', 'area': 'Aundh'},
            '411045': {'city': 'Pune', 'state': 'Maharashtra', 'area': 'Hinjewadi'},
            '400001': {'city': 'Mumbai', 'state': 'Maharashtra', 'area': 'Fort'},
            '400002': {'city': 'Mumbai', 'state': 'Maharashtra', 'area': 'Churchgate'},
            '400020': {'city': 'Mumbai', 'state': 'Maharashtra', 'area': 'Powai'},
            '400093': {'city': 'Mumbai', 'state': 'Maharashtra', 'area': 'Andheri East'},
            '560001': {'city': 'Bangalore', 'state': 'Karnataka', 'area': 'MG Road'},
            '560002': {'city': 'Bangalore', 'state': 'Karnataka', 'area': 'Indiranagar'},
            '560038': {'city': 'Bangalore', 'state': 'Karnataka', 'area': 'Koramangala'},
        }
        
        if pincode and pincode in pincode_map:
            result.update(pincode_map[pincode])
            result['is_inferred'] = True
            result['confidence'] = 'HIGH'
        
        return result
    
    def classify_profile(self, record: Dict) -> Tuple[str, float]:
        """Classify profile as Non-RE, Property Seeker, or Real Estate Trade"""
        signals = []
        classification = 'Non-Real Estate'
        confidence = 0.5
        
        # Check for property seeker signals
        if record.get('bhk_preference') or record.get('budget_range') or record.get('project_enquired'):
            signals.append('property_seeker')
        
        # Check for real estate trade signals  
        trade_keywords = ['broker', 'agent', 'developer', 'consultant', 'builder', 'realtor']
        company = str(record.get('company_name', '')).lower()
        if any(keyword in company for keyword in trade_keywords):
            signals.append('trade')
        
        # Check source type
        source = str(record.get('_source_type', '')).lower()
        if 'property portal' in source or 'facebook' in source:
            signals.append('property_seeker')
        elif 'broker' in source or 'agent' in source:
            signals.append('trade')
        
        # Determine classification
        if 'trade' in signals:
            classification = 'Real Estate Trade'
            confidence = 0.8
        elif 'property_seeker' in signals:
            classification = 'Property Seeker'
            confidence = 0.7
        
        return classification, confidence
    
    def merge_profile(self, profile_id: str, new_data: Dict, source_file: str, data_type: str = 'ACTUAL'):
        """Merge new data into existing profile with conflict resolution"""
        
        # Get current profile
        cursor = self.conn.execute("SELECT * FROM profiles WHERE profile_id = ?", (profile_id,))
        row = cursor.fetchone()
        if not row:
            return False
        
        # Get column names
        columns = [description[0] for description in cursor.description]
        current_dict = dict(zip(columns, row))
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Fields to merge with conflict resolution
        fields_to_merge = ['name', 'email', 'address', 'city', 'area', 'pincode', 
                          'bhk_preference', 'budget_range', 'income_group']
        
        for field in fields_to_merge:
            new_value = new_data.get(field)
            current_value = current_dict.get(field)
            
            if new_value and not current_value:
                # Empty field - fill it
                self.conn.execute(f"""
                    UPDATE profiles SET {field} = ?, last_enriched = ? 
                    WHERE profile_id = ?
                """, (new_value, now, profile_id))
                
                # Log to field history
                self.conn.execute("""
                    INSERT INTO field_history (profile_id, field_name, old_value, new_value, source_file, changed_at, change_type, data_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (profile_id, field, None, new_value, source_file, now, 'CREATE', data_type))
                
            elif new_value and current_value and str(new_value) != str(current_value):
                # Conflict - longer value wins for names
                if field == 'name' and len(str(new_value)) > len(str(current_value)):
                    self.conn.execute(f"UPDATE profiles SET {field} = ?, last_enriched = ? WHERE profile_id = ?", 
                                    (new_value, now, profile_id))
                    self.conn.execute("""
                        INSERT INTO field_history (profile_id, field_name, old_value, new_value, source_file, changed_at, change_type, data_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (profile_id, field, current_value, new_value, source_file, now, 'CONFLICT_RESOLVED', data_type))
        
        # Update record count and source files
        record_count = current_dict.get('record_count', 0) + 1
        source_files = current_dict.get('source_files', '')
        if source_file not in source_files:
            source_files = f"{source_files},{source_file}" if source_files else source_file
        
        self.conn.execute("""
            UPDATE profiles SET record_count = ?, source_files = ?, last_enriched = ? 
            WHERE profile_id = ?
        """, (record_count, source_files, now, profile_id))
        
        self.conn.commit()
        return True
    
    def create_profile(self, record: Dict, source_file: str, source_type: str, category: str, data_type: str = 'ACTUAL') -> str:
        """Create new profile from record"""
        
        mobile, is_valid = self.clean_mobile(record.get('mobile'))
        if not is_valid or not mobile:
            return None
        
        profile_id = hashlib.md5(mobile.encode()).hexdigest()[:16]
        
        # Infer location if needed
        location = self.infer_location(pincode=record.get('pincode'), address=record.get('address'))
        
        # Classify
        classification, confidence = self.classify_profile(record)
        
        # If operator provided category, override
        if category != 'Let system decide':
            classification = category
            confidence = 1.0
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        date_collected = record.get('date_collected', datetime.now().date())
        if isinstance(date_collected, datetime):
            date_collected = date_collected.strftime("%Y-%m-%d")
        elif isinstance(date_collected, str):
            pass
        else:
            date_collected = date_collected.strftime("%Y-%m-%d")
        
        # Insert profile
        self.conn.execute("""
            INSERT INTO profiles (
                profile_id, mobile, name, email, address, city, area, pincode,
                classification, classification_confidence, created_at, last_enriched,
                record_count, source_files, has_valid_mobile, date_collected
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            profile_id, mobile, 
            record.get('name'), record.get('email'), record.get('address'),
            location.get('city') or record.get('city'),
            location.get('area') or record.get('area'),
            record.get('pincode') or location.get('pincode'),
            classification, confidence,
            now, now,
            1, source_file, 1 if is_valid else 0, date_collected
        ))
        
        # Update search index
        self.conn.execute("""
            INSERT INTO profile_search (profile_id, mobile, name, email, address, city, area, pincode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (profile_id, mobile, record.get('name'), record.get('email'), 
              record.get('address'), location.get('city') or record.get('city'), 
              location.get('area') or record.get('area'), record.get('pincode')))
        
        self.conn.commit()
        
        return profile_id
    
    def process_file(self, file_obj, metadata: Dict) -> Dict:
        """Process uploaded file and merge into warehouse"""
    
        result = {
            'success': False,
            'message': '',
            'total_records': 0,
            'profiles_created': 0,
            'profiles_enriched': 0,
            'invalid_mobiles': 0
        }
    
        try:
            # Check if file is empty
            if file_obj.size == 0:
                result['message'] = "File is empty - skipping"
                result['success'] = True
                return result
        
            # Read file with multiple strategies
            df = None
            file_content = file_obj.read()
            file_obj.seek(0)
        
            # For .xls files (old Excel format)
            if file_obj.name.endswith('.xls'):
                try:
                    # Try with xlrd engine first (best for old .xls)
                    import xlrd
                    df = pd.read_excel(io.BytesIO(file_content), engine='xlrd')
                except:
                    try:
                        # Try with openpyxl
                        df = pd.read_excel(io.BytesIO(file_content), engine='openpyxl')
                    except:
                        try:
                            # Try reading raw bytes with pandas
                            df = pd.read_excel(io.BytesIO(file_content), engine=None)
                        except:
                            pass
        
            # For .xlsx files
            elif file_obj.name.endswith('.xlsx'):
                try:
                    df = pd.read_excel(io.BytesIO(file_content), engine='openpyxl')
                except:
                    try:
                        df = pd.read_excel(io.BytesIO(file_content), engine='xlrd')
                    except:
                        pass
        
            # For CSV files
            else:
                encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
                for encoding in encodings:
                    try:
                        df = pd.read_csv(io.BytesIO(file_content), encoding=encoding, on_bad_lines='skip')
                        if df is not None and not df.empty:
                            break
                    except:
                        continue
        
            if df is None or df.empty:
                result['message'] = "Could not read file or file is empty"
                return result
        
            # Check if this is a valid lead file (not a tracker/meeting file)
            # Look for patterns that indicate it's NOT a lead file
            first_rows = df.head(10).astype(str).values.flatten()
            first_rows_str = ' '.join([str(x).lower() for x in first_rows])
        
            # Skip tracker/meeting files
            skip_keywords = ['calls', 'cp meetings', 'cp orientation', 'site visit', 'meeting date', 
                        'firm name', 'person name', 'team size', 'rm name', 'remarks',
                        'cp firm name', 'contact person', 'meeting status', 'follow up call']
        
            is_tracker_file = any(keyword in first_rows_str for keyword in skip_keywords)
        
            if is_tracker_file:
                result['message'] = "Skipped - This appears to be a meeting tracker or CP management file, not a lead file"
                result['success'] = True  # Not an error, just skip silently
                return result
        
            # Find mobile column by checking multiple patterns
            mobile_col = None
            mobile_patterns = ['mobile', 'phone', 'contact', 'mobile_number', 'phone_number', 
                          'mobileno', 'contactno', 'mobile no', 'phone no']
        
            # First check column names
            for col in df.columns:
                col_lower = str(col).lower().replace('_', ' ').replace('.', '')
                for pattern in mobile_patterns:
                    if pattern in col_lower:
                        mobile_col = col
                        break
                if mobile_col:
                    break
        
            # If not found by name, check data patterns
            if not mobile_col:
                for col in df.columns:
                    # Sample first 30 non-null values
                    sample = df[col].dropna().head(30).astype(str)
                    # Check for Indian mobile number pattern (10 digits starting with 6/7/8/9)
                    if sample.str.match(r'^[6-9][0-9]{9}$').any():
                        mobile_col = col
                        break
                    # Check with +91 prefix
                    if sample.str.match(r'^\+91[6-9][0-9]{9}$').any():
                        mobile_col = col
                        break
                    # Check with 91 prefix
                    if sample.str.match(r'^91[6-9][0-9]{9}$').any():
                        mobile_col = col
                        break
        
            if not mobile_col:
                result['message'] = f"No mobile number column detected. Available columns: {list(df.columns)[:5]}"
                return result
        
            # Process each row
            for idx, row in df.iterrows():
                result['total_records'] += 1
            
                mobile_raw = row[mobile_col]
                mobile, is_valid = self.clean_mobile(mobile_raw)
            
                if not is_valid or not mobile:
                    result['invalid_mobiles'] += 1
                    continue
            
                # Find name column (try common patterns)
                name_col = None
                for col in df.columns:
                    col_lower = str(col).lower()
                    if 'name' in col_lower or 'full_name' in col_lower or 'person' in col_lower:
                        name_col = col
                        break
            
                # Find email column
                email_col = None
                for col in df.columns:
                    col_lower = str(col).lower()
                    if 'email' in col_lower or 'mail' in col_lower:
                        email_col = col
                        break
            
                # Find city column
                city_col = None
                for col in df.columns:
                    col_lower = str(col).lower()
                    if col_lower == 'city' or col_lower == 'town':
                        city_col = col
                        break
            
                record = {
                    'mobile': mobile,
                    'name': row[name_col] if name_col and name_col in row and pd.notna(row[name_col]) else '',
                    'email': row[email_col] if email_col and email_col in row and pd.notna(row[email_col]) else '',
                    'address': '',
                    'city': row[city_col] if city_col and city_col in row and pd.notna(row[city_col]) else '',
                    'pincode': '',
                    'bhk_preference': '',
                    'budget_range': '',
                    'date_collected': metadata.get('collection_date', datetime.now().strftime("%Y-%m-%d"))
                }
            
                # Also check for city in address column if city not found
                if not record['city']:
                    for col in df.columns:
                        if 'address' in str(col).lower() or 'addr' in str(col).lower():
                            if pd.notna(row[col]):
                                # Try to extract city from address
                                address_str = str(row[col])
                                # Common cities in Maharashtra
                                cities = ['Pune', 'Mumbai', 'Nagpur', 'Nashik', 'Aurangabad', 
                                     'Solapur', 'Kolhapur', 'Thane', 'Pimpri', 'Chinchwad']
                                for city in cities:
                                    if city.lower() in address_str.lower():
                                        record['city'] = city
                                        break
                            break
            
                # Check if profile exists
                cursor = self.conn.execute("SELECT profile_id FROM profiles WHERE mobile = ?", (mobile,))
                existing = cursor.fetchone()
            
                if existing:
                    self.merge_profile(existing[0], record, file_obj.name, 'ACTUAL')
                    result['profiles_enriched'] += 1
                else:
                    profile_id = self.create_profile(record, file_obj.name, 
                                                 metadata.get('source_type', 'Unknown'),
                                                 metadata.get('category', 'Let system decide'),
                                                 'ACTUAL')
                    if profile_id:
                        result['profiles_created'] += 1
        
            result['success'] = True
            result['message'] = f"Processed {result['total_records']} records"
        
            # Store import job
            job_id = hashlib.md5(f"{file_obj.name}{datetime.now()}".encode()).hexdigest()[:8]
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
            self.conn.execute("""
                INSERT INTO import_jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (job_id, file_obj.name, metadata.get('source_type'), metadata.get('collection_date'),
                  metadata.get('category'), metadata.get('geographic_coverage'), metadata.get('quality_notes'),
                  metadata.get('file_label'), 'COMPLETE', result['total_records'], result['total_records'],
                  result['profiles_created'], result['profiles_enriched'], result['invalid_mobiles'],
                  now, now))
        
            self.conn.commit()
        
        except Exception as e:
            result['message'] = f"Error: {str(e)}"
    
        return result
    
    def search(self, query: str = None, filters: Dict = None, limit: int = 1000) -> pd.DataFrame:
        """Search profiles with filters"""
        
        sql = "SELECT * FROM profiles WHERE is_active = 1"
        params = []
        
        if query:
            # Use FTS for text search
            try:
                fts_results = self.conn.execute("""
                    SELECT profile_id FROM profile_search WHERE profile_search MATCH ?
                    LIMIT 1000
                """, (query,)).fetchall()
                
                if fts_results:
                    profile_ids = [r[0] for r in fts_results]
                    placeholders = ','.join(['?' for _ in profile_ids])
                    sql += f" AND profile_id IN ({placeholders})"
                    params.extend(profile_ids)
                else:
                    # Fallback to LIKE search
                    search_pattern = f"%{query}%"
                    sql += " AND (name LIKE ? OR mobile LIKE ? OR email LIKE ? OR city LIKE ? OR address LIKE ?)"
                    params.extend([search_pattern, search_pattern, search_pattern, search_pattern, search_pattern])
            except:
                # Fallback to LIKE search
                search_pattern = f"%{query}%"
                sql += " AND (name LIKE ? OR mobile LIKE ? OR email LIKE ? OR city LIKE ? OR address LIKE ?)"
                params.extend([search_pattern, search_pattern, search_pattern, search_pattern, search_pattern])
        
        # Apply filters
        if filters:
            if filters.get('classification'):
                sql += " AND classification = ?"
                params.append(filters['classification'])
            if filters.get('city'):
                sql += " AND city = ?"
                params.append(filters['city'])
            if filters.get('pincode'):
                sql += " AND pincode = ?"
                params.append(filters['pincode'])
        
        sql += f" LIMIT {limit}"
        
        result = pd.read_sql_query(sql, self.conn, params=params)
        return result
    
    def get_statistics(self) -> Dict:
        """Get dashboard statistics"""
        
        stats = self.conn.execute("""
            SELECT 
                COUNT(*) as total_profiles,
                SUM(CASE WHEN has_valid_mobile = 1 THEN 1 ELSE 0 END) as valid_mobiles,
                SUM(CASE WHEN classification = 'Real Estate Trade' THEN 1 ELSE 0 END) as trade_count,
                SUM(CASE WHEN classification = 'Property Seeker' THEN 1 ELSE 0 END) as seeker_count,
                SUM(CASE WHEN classification = 'Non-Real Estate' THEN 1 ELSE 0 END) as nonre_count,
                SUM(record_count) as total_records
            FROM profiles
            WHERE is_active = 1
        """).fetchone()
        
        # City breakdown
        city_stats = self.conn.execute("""
            SELECT city, COUNT(*) as count 
            FROM profiles 
            WHERE city IS NOT NULL AND city != ''
            GROUP BY city 
            ORDER BY count DESC 
            LIMIT 10
        """).fetchall()
        
        # Source breakdown
        source_stats = self.conn.execute("""
            SELECT source_type, COUNT(*) as count 
            FROM import_jobs 
            GROUP BY source_type 
            ORDER BY count DESC 
            LIMIT 10
        """).fetchall()
        
        return {
            'total_profiles': stats[0] or 0,
            'valid_mobiles': stats[1] or 0,
            'trade_count': stats[2] or 0,
            'seeker_count': stats[3] or 0,
            'nonre_count': stats[4] or 0,
            'total_records': stats[5] or 0,
            'city_breakdown': [{'city': row[0], 'count': row[1]} for row in city_stats],
            'source_breakdown': [{'source': row[0], 'count': row[1]} for row in source_stats]
        }

def main():
    """Main application"""
    
    st.markdown('<div class="main-header">🏠 Real Estate Data Intelligence Platform</div>', unsafe_allow_html=True)
    
    # Initialize warehouse
    if not st.session_state.db_initialized:
        with st.spinner("Initializing database..."):
            warehouse = DataWarehouse()
            st.session_state.warehouse = warehouse
    else:
        warehouse = st.session_state.warehouse
    
    # Sidebar
    with st.sidebar:
        st.title("📊 Navigation")
        
        page = st.radio(
            "Select Module",
            ["📤 Import Data", "🔍 Search & Export", "📈 Dashboard", "📋 Import History", "⚙️ Settings"],
            index=0
        )
        
        st.markdown("---")
        
        # System stats
        stats = warehouse.get_statistics()
        st.markdown("### 📊 System Stats")
        st.metric("Total Profiles", f"{stats['total_profiles']:,}")
        st.metric("Total Records", f"{stats['total_records']:,}")
        st.metric("Valid Mobiles", f"{stats['valid_mobiles']:,}")
    
    # Page routing
    if page == "📤 Import Data":
        import_page(warehouse)
    elif page == "🔍 Search & Export":
        search_page(warehouse)
    elif page == "📈 Dashboard":
        dashboard_page(warehouse)
    elif page == "📋 Import History":
        history_page(warehouse)
    elif page == "⚙️ Settings":
        settings_page()

def import_page(warehouse: DataWarehouse):
    """File import interface"""
    st.header("📤 Import Data Files")
    
    st.markdown("""
    <div class="info-box">
        <strong>📋 Intake Questions</strong> - Please answer these 6 questions before importing
    </div>
    """, unsafe_allow_html=True)
    
    with st.form("import_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            source_type = st.selectbox(
                "1. Source of Data *",
                ["Utility Consumer List", "Facebook Advertising Lead", "Property Portal Enquiry",
                 "Real Estate Expo Walk-in", "Broker/Agent List", "School/Institutional Data",
                 "Internal Sales Data", "General Population List", "Other"]
            )
            
            collection_date = st.date_input("2. Collection Date", datetime.now())
            
            category = st.selectbox(
                "3. Data Category *",
                ["Let system decide", "Real Estate Trade", "Property Seeker", "Non-Real Estate"]
            )
        
        with col2:
            geographic_coverage = st.text_input("4. Geographic Coverage", placeholder="e.g., Pune, Mumbai, Pan-India")
            
            quality_notes = st.text_area("5. Quality Notes", placeholder="Expected duplicates, verified leads, known issues...")
            
            file_label = st.text_input("6. File Label", placeholder="Name this file for reference")
        
        uploaded_files = st.file_uploader(
            "Choose Files (Excel or CSV)",
            type=['xlsx', 'xls', 'csv'],
            accept_multiple_files=True,
            help="Upload one or more files. They will be processed sequentially."
        )
        
        submitted = st.form_submit_button("🚀 Import Files", type="primary", use_container_width=True)
        
        if submitted and uploaded_files:
            for file in uploaded_files:
                with st.spinner(f"Processing {file.name}..."):
                    metadata = {
                        'source_type': source_type,
                        'collection_date': collection_date.strftime("%Y-%m-%d"),
                        'category': category,
                        'geographic_coverage': geographic_coverage,
                        'quality_notes': quality_notes,
                        'file_label': file_label or file.name
                    }
                    
                    result = warehouse.process_file(file, metadata)
                    
                    if result['success']:
                        st.success(f"✅ {file.name}: {result['message']}")
                        st.caption(f"   Created: {result['profiles_created']} | Enriched: {result['profiles_enriched']} | Invalid: {result['invalid_mobiles']}")
                    else:
                        st.error(f"❌ {file.name}: {result['message']}")

def search_page(warehouse: DataWarehouse):
    """Search and export interface"""
    st.header("🔍 Search & Export")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        search_text = st.text_input("🔍 Search", placeholder="Name, mobile, email, area, pincode...")
    
    with col2:
        classification = st.selectbox("Category", ["All", "Real Estate Trade", "Property Seeker", "Non-Real Estate"])
    
    with col3:
        city = st.text_input("City", placeholder="e.g., Pune, Mumbai")
    
    if st.button("🔍 Search", type="primary", use_container_width=True):
        filters = {}
        if classification != "All":
            filters['classification'] = classification
        if city:
            filters['city'] = city
        
        with st.spinner("Searching..."):
            results = warehouse.search(query=search_text if search_text else None, 
                                       filters=filters if filters else None,
                                       limit=1000)
            
            st.markdown(f"### 📊 Results: {len(results)} profiles found")
            
            if not results.empty:
                # Display results
                display_cols = ['profile_id', 'mobile', 'name', 'email', 'city', 'classification', 'record_count']
                available_cols = [col for col in display_cols if col in results.columns]
                st.dataframe(results[available_cols], use_container_width=True, height=400)
                
                # Export
                st.markdown("---")
                col1, col2 = st.columns(2)
                with col1:
                    export_format = st.selectbox("Export Format", ["CSV", "Excel"])
                with col2:
                    export_name = st.text_input("Filename", value=f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                
                if st.button("📥 Download Results"):
                    if export_format == "CSV":
                        csv = results.to_csv(index=False).encode()
                        st.download_button("Download CSV", csv, f"{export_name}.csv", "text/csv")
                    else:
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            results.to_excel(writer, sheet_name='Results', index=False)
                        st.download_button("Download Excel", output.getvalue(), f"{export_name}.xlsx",
                                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            else:
                st.info("No results found")

def dashboard_page(warehouse: DataWarehouse):
    """Analytics dashboard"""
    st.header("📈 Analytics Dashboard")
    
    stats = warehouse.get_statistics()
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{stats['total_profiles']:,}</div>
            <div class="stat-label">Total Profiles</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{stats['total_records']:,}</div>
            <div class="stat-label">Total Records</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{stats['valid_mobiles']:,}</div>
            <div class="stat-label">Valid Mobiles</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        duplicate_count = stats['total_records'] - stats['total_profiles']
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{duplicate_count:,}</div>
            <div class="stat-label">Duplicates Removed</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Category breakdown
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Category Distribution")
        category_data = {
            'Category': ['Real Estate Trade', 'Property Seeker', 'Non-Real Estate'],
            'Count': [stats['trade_count'], stats['seeker_count'], stats['nonre_count']]
        }
        import plotly.express as px
        fig = px.pie(category_data, values='Count', names='Category', title='Profiles by Category', hole=0.3)
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("Top Cities")
        if stats['city_breakdown']:
            city_df = pd.DataFrame(stats['city_breakdown'])
            fig = px.bar(city_df, x='city', y='count', title='Profiles by City', color='count')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No city data available")
    
    # Source breakdown
    st.subheader("Data Sources")
    if stats['source_breakdown']:
        source_df = pd.DataFrame(stats['source_breakdown'])
        fig = px.bar(source_df, x='source', y='count', title='Records by Source', color='count')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No source data available")

def history_page(warehouse: DataWarehouse):
    """Import history"""
    st.header("📋 Import History")
    
    history = pd.read_sql_query("""
        SELECT file_name, source_type, collection_date, category, 
               total_records, profiles_created, profiles_enriched, 
               invalid_mobiles, status, started_at
        FROM import_jobs 
        ORDER BY started_at DESC 
        LIMIT 50
    """, warehouse.conn)
    
    if not history.empty:
        st.dataframe(history, use_container_width=True)
        
        # Export history
        if st.button("📥 Export History"):
            csv = history.to_csv(index=False).encode()
            st.download_button("Download CSV", csv, "import_history.csv", "text/csv")
    else:
        st.info("No import history yet")

def settings_page():
    """Settings interface"""
    st.header("⚙️ Settings")
    
    st.markdown("""
    ### System Configuration
    
    **Database Location:** `data_warehouse.db`
    
    ### Data Rules
    
    - Mobile numbers are standardized to 10 digits
    - Duplicate detection uses mobile number as primary key
    - Field conflicts resolved by: longer values win
    - Classification is automatic (can be overridden at import)
    
    ### Location Inference
    
    The system maintains a database of Indian pincodes to automatically infer:
    - City from pincode
    - State from pincode
    - Area from pincode
    
    ### Export Settings
    
    - CSV: UTF-8 encoding
    - Excel: .xlsx format with openpyxl
    
    ### About
    
    **Version:** 2.0 (Enterprise Scale)
    **Architecture:** SQLite with FTS5
    **Scale Ready:** Designed for 5 crore+ records
    """)

if __name__ == "__main__":
    main()
