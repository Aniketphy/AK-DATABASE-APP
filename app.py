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
import base64

# Optional imports with fallbacks
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    openai = None

try:
    import xlrd
    XLRD_AVAILABLE = True
except ImportError:
    XLRD_AVAILABLE = False

warnings.filterwarnings('ignore')

# Page configuration
st.set_page_config(
    page_title="AI-Powered Real Estate Data Intelligence Platform",
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
    .info-box {
        background-color: #f0fdf4;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #22c55e;
        margin: 1rem 0;
    }
    .warning-box {
        background-color: #fef3c7;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #f59e0b;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'db_initialized' not in st.session_state:
    st.session_state.db_initialized = False
if 'import_jobs' not in st.session_state:
    st.session_state.import_jobs = []
if 'openai_api_key' not in st.session_state:
    st.session_state.openai_api_key = None

class DataWarehouse:
    """Core data warehouse using SQLite for storage and search with AI parsing"""
    
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
            
            # Remove +91 prefix and other non-digits
            digits = ''.join(filter(str.isdigit, value_str))
            
            # Remove leading zero
            if digits.startswith('0'):
                digits = digits[1:]
            
            # Handle country codes
            if digits.startswith('91') and len(digits) == 12:
                digits = digits[2:]
            
            # Validate Indian mobile number (10 digits, starts with 6/7/8/9)
            if len(digits) == 10 and digits[0] in '6789':
                return digits, True
            else:
                return digits, False
                
        except Exception:
            return "", False
    
    def parse_complex_excel_with_ai(self, file_content: bytes, file_name: str) -> Optional[pd.DataFrame]:
        """Use OpenAI to parse complex Excel files with merged cells and multi-line headers"""
        
        if not OPENAI_AVAILABLE or not st.session_state.openai_api_key:
            return None
        
        try:
            client = openai.OpenAI(api_key=st.session_state.openai_api_key)
            
            # Try to extract sample content using xlrd
            sample_text = f"File: {file_name}\n\n"
            
            if XLRD_AVAILABLE:
                try:
                    workbook = xlrd.open_workbook(file_contents=file_content)
                    sheet = workbook.sheet_by_index(0)
                    
                    # Extract first 30 rows as text
                    for row_idx in range(min(30, sheet.nrows)):
                        row_values = []
                        for col_idx in range(min(15, sheet.ncols)):  # Limit to 15 columns for readability
                            cell = sheet.cell(row_idx, col_idx)
                            if cell.ctype == xlrd.XL_CELL_TEXT:
                                val = str(cell.value)[:50]
                                if val.strip():
                                    row_values.append(val)
                            elif cell.ctype == xlrd.XL_CELL_NUMBER:
                                val = str(int(cell.value)) if cell.value == int(cell.value) else str(cell.value)[:20]
                                if val.strip():
                                    row_values.append(val)
                        if row_values:
                            sample_text += f"Row {row_idx}: {' | '.join(row_values)}\n"
                except Exception as e:
                    sample_text += f"Could not extract sample: {str(e)}\n"
            else:
                sample_text += "xlrd not available for complex Excel parsing\n"
            
            # OpenAI prompt
            prompt = f"""You are helping parse a complex Excel/CSV file: {file_name}

Here are the first 30 rows of the file as text:

{sample_text}

Please analyze this file and:
1. Identify which row contains the column headers (look for: id, created_time, mobile_number, phone_number, full_name, name, email, city, address)
2. Identify which column contains mobile/phone numbers
3. Identify which column contains names
4. Identify which column contains email addresses
5. Identify which column contains city/location

Return a JSON object with:
- header_row_index: (row number, 0-based, or -1 if no clear header)
- mobile_column_name: (the exact column name or index)
- name_column_name: (the exact column name or index)
- email_column_name: (the exact column name or index)
- city_column_name: (the exact column name or index)
- data_start_row: (row where data actually starts)
- has_valid_data: (true/false)

Return ONLY valid JSON, no other text."""

            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                max_tokens=800,
                temperature=0,
                messages=[
                    {"role": "system", "content": "You are an Excel parsing assistant. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            result = json.loads(response.choices[0].message.content)
            
            if result.get('has_valid_data'):
                # Try to read with pandas using detected header row
                try:
                    if result.get('header_row_index', -1) >= 0:
                        df = pd.read_excel(io.BytesIO(file_content), 
                                          header=result['header_row_index'],
                                          engine='xlrd' if XLRD_AVAILABLE else 'openpyxl')
                        return df
                except:
                    pass
            
            return None
            
        except Exception as e:
            st.warning(f"OpenAI parsing failed: {str(e)}")
            return None
    
    def read_file_smart(self, file_obj) -> Optional[pd.DataFrame]:
        """Intelligently read Excel/CSV files with multiple fallback strategies"""
        
        file_content = file_obj.read()
        file_obj.seek(0)
        
        # For .xls files (old Excel format with complex formatting)
        if file_obj.name.endswith('.xls'):
            # Try AI-powered parsing first if OpenAI is available
            if OPENAI_AVAILABLE and st.session_state.openai_api_key:
                df = self.parse_complex_excel_with_ai(file_content, file_obj.name)
                if df is not None and not df.empty:
                    return df
            
            # Try xlrd engine
            if XLRD_AVAILABLE:
                try:
                    df = pd.read_excel(io.BytesIO(file_content), engine='xlrd')
                    if not df.empty and len(df.columns) > 1:
                        return df
                except:
                    pass
            
            # Try openpyxl
            try:
                df = pd.read_excel(io.BytesIO(file_content), engine='openpyxl')
                if not df.empty and len(df.columns) > 1:
                    return df
            except:
                pass
            
            # Try reading without engine specification
            try:
                df = pd.read_excel(io.BytesIO(file_content))
                if not df.empty and len(df.columns) > 1:
                    return df
            except:
                pass
        
        # For .xlsx files
        elif file_obj.name.endswith('.xlsx'):
            try:
                df = pd.read_excel(io.BytesIO(file_content), engine='openpyxl')
                if not df.empty:
                    return df
            except:
                try:
                    df = pd.read_excel(io.BytesIO(file_content), engine='xlrd')
                    if not df.empty:
                        return df
                except:
                    pass
        
        # For CSV files
        else:
            encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
            for encoding in encodings:
                try:
                    df = pd.read_csv(io.BytesIO(file_content), encoding=encoding, on_bad_lines='skip')
                    if not df.empty:
                        return df
                except:
                    continue
        
        return None
    
    def is_tracker_file(self, df: pd.DataFrame, file_name: str) -> bool:
        """Check if file is a tracker/meeting file (not lead data)"""
        
        first_rows = df.head(10).astype(str).values.flatten()
        first_rows_str = ' '.join([str(x).lower() for x in first_rows])
        
        # Keywords that indicate this is NOT a lead file
        skip_keywords = [
            'calls', 'cp meetings', 'cp orientation', 'site visit', 'meeting date',
            'firm name', 'person name', 'team size', 'rm name', 'remarks',
            'cp firm name', 'contact person', 'meeting status', 'follow up call',
            'calls', 'cp meetings', 'cp orientation', 'site visit'
        ]
        
        return any(keyword in first_rows_str for keyword in skip_keywords)
    
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
            
            # Smart file reading
            df = self.read_file_smart(file_obj)
            
            if df is None or df.empty:
                result['message'] = "Could not read file or file is empty"
                return result
            
            # Check if this is a tracker file (skip silently)
            if self.is_tracker_file(df, file_obj.name):
                result['message'] = "Skipped - Meeting tracker or CP management file"
                result['success'] = True
                return result
            
            # Clean column names
            df.columns = [str(col).strip().lower().replace(' ', '_').replace('\n', '') for col in df.columns]
            
            # Find mobile column
            mobile_col = None
            mobile_patterns = ['mobile', 'phone', 'contact', 'mobile_number', 'phone_number', 
                              'mobileno', 'contactno', 'mobile_no', 'phone_no', 'full_phone']
            
            for col in df.columns:
                for pattern in mobile_patterns:
                    if pattern in col:
                        mobile_col = col
                        break
                if mobile_col:
                    break
            
            # If not found by name, check data patterns
            if not mobile_col:
                for col in df.columns:
                    sample = df[col].dropna().head(30).astype(str)
                    if sample.str.match(r'^[6-9][0-9]{9}$').any():
                        mobile_col = col
                        break
                    if sample.str.match(r'^\+91[6-9][0-9]{9}$').any():
                        mobile_col = col
                        break
            
            if not mobile_col:
                result['message'] = f"No mobile number column detected. Columns found: {list(df.columns)[:5]}"
                return result
            
            # Find other columns
            name_col = None
            for col in df.columns:
                if 'name' in col or 'full_name' in col or 'person' in col:
                    name_col = col
                    break
            
            email_col = None
            for col in df.columns:
                if 'email' in col or 'mail' in col:
                    email_col = col
                    break
            
            city_col = None
            for col in df.columns:
                if col == 'city' or col == 'town' or col == 'location':
                    city_col = col
                    break
            
            # Process each row
            for idx, row in df.iterrows():
                result['total_records'] += 1
                
                mobile_raw = row[mobile_col]
                mobile, is_valid = self.clean_mobile(mobile_raw)
                
                if not is_valid or not mobile:
                    result['invalid_mobiles'] += 1
                    continue
                
                record = {
                    'mobile': mobile,
                    'name': row[name_col] if name_col and pd.notna(row.get(name_col)) else '',
                    'email': row[email_col] if email_col and pd.notna(row.get(email_col)) else '',
                    'address': '',
                    'city': row[city_col] if city_col and pd.notna(row.get(city_col)) else '',
                    'pincode': '',
                    'bhk_preference': '',
                    'budget_range': '',
                    'date_collected': metadata.get('collection_date', datetime.now().strftime("%Y-%m-%d"))
                }
                
                # Convert to string and clean
                for key in record:
                    if pd.isna(record[key]) or record[key] is None:
                        record[key] = ''
                    else:
                        record[key] = str(record[key]).strip()
                
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
    
    def merge_profile(self, profile_id: str, new_data: Dict, source_file: str, data_type: str = 'ACTUAL'):
        """Merge new data into existing profile"""
        
        cursor = self.conn.execute("SELECT * FROM profiles WHERE profile_id = ?", (profile_id,))
        row = cursor.fetchone()
        if not row:
            return False
        
        columns = [description[0] for description in cursor.description]
        current_dict = dict(zip(columns, row))
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        fields_to_merge = ['name', 'email', 'address', 'city', 'pincode']
        
        for field in fields_to_merge:
            new_value = new_data.get(field)
            current_value = current_dict.get(field)
            
            if new_value and not current_value:
                self.conn.execute(f"""
                    UPDATE profiles SET {field} = ?, last_enriched = ? 
                    WHERE profile_id = ?
                """, (new_value, now, profile_id))
                
                self.conn.execute("""
                    INSERT INTO field_history (profile_id, field_name, old_value, new_value, source_file, changed_at, change_type, data_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (profile_id, field, None, new_value, source_file, now, 'CREATE', data_type))
        
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
        
        mobile = record.get('mobile')
        if not mobile:
            return None
        
        profile_id = hashlib.md5(mobile.encode()).hexdigest()[:16]
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        date_collected = record.get('date_collected', datetime.now().strftime("%Y-%m-%d"))
        
        classification = 'Property Seeker' if category == 'Let system decide' else category
        
        self.conn.execute("""
            INSERT INTO profiles (
                profile_id, mobile, name, email, city, classification, 
                created_at, last_enriched, record_count, source_files, 
                has_valid_mobile, date_collected
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            profile_id, mobile, record.get('name'), record.get('email'), record.get('city'),
            classification, now, now, 1, source_file, 1, date_collected
        ))
        
        self.conn.execute("""
            INSERT INTO profile_search (profile_id, mobile, name, email, city)
            VALUES (?, ?, ?, ?, ?)
        """, (profile_id, mobile, record.get('name'), record.get('email'), record.get('city')))
        
        self.conn.commit()
        return profile_id
    
    def search(self, query: str = None, filters: Dict = None, limit: int = 1000) -> pd.DataFrame:
        """Search profiles with filters"""
        
        sql = "SELECT * FROM profiles WHERE is_active = 1"
        params = []
        
        if query:
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
                    search_pattern = f"%{query}%"
                    sql += " AND (name LIKE ? OR mobile LIKE ? OR email LIKE ? OR city LIKE ?)"
                    params.extend([search_pattern, search_pattern, search_pattern, search_pattern])
            except:
                search_pattern = f"%{query}%"
                sql += " AND (name LIKE ? OR mobile LIKE ? OR email LIKE ? OR city LIKE ?)"
                params.extend([search_pattern, search_pattern, search_pattern, search_pattern])
        
        if filters:
            if filters.get('classification'):
                sql += " AND classification = ?"
                params.append(filters['classification'])
            if filters.get('city'):
                sql += " AND city = ?"
                params.append(filters['city'])
        
        sql += f" LIMIT {limit}"
        
        return pd.read_sql_query(sql, self.conn, params=params)
    
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
        
        city_stats = self.conn.execute("""
            SELECT city, COUNT(*) as count 
            FROM profiles 
            WHERE city IS NOT NULL AND city != ''
            GROUP BY city 
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
            'city_breakdown': [{'city': row[0], 'count': row[1]} for row in city_stats]
        }

def main():
    """Main application"""
    
    st.markdown('<div class="main-header">🤖 AI-Powered Real Estate Data Intelligence Platform</div>', unsafe_allow_html=True)
    
    # Sidebar - Configuration
    with st.sidebar:
        st.title("⚙️ Configuration")
        
        # OpenAI API Key input
        api_key = st.text_input("OpenAI API Key (Optional)", type="password", 
                                help="Enter your OpenAI API key for AI-powered complex Excel parsing")
        
        if api_key:
            st.session_state.openai_api_key = api_key
            if OPENAI_AVAILABLE:
                st.success("✅ OpenAI API Key configured!")
            else:
                st.warning("⚠️ OpenAI package not installed. Run: pip install openai")
        
        st.markdown("---")
        st.title("📊 Navigation")
        
        page = st.radio(
            "Select Module",
            ["📤 Import Data", "🔍 Search & Export", "📈 Dashboard", "📋 Import History", "ℹ️ System Info"],
            index=0
        )
        
        st.markdown("---")
        
        # System status
        if OPENAI_AVAILABLE and st.session_state.openai_api_key:
            st.info("🤖 AI Mode: Enabled for complex Excel parsing")
        elif OPENAI_AVAILABLE:
            st.warning("🤖 AI Mode: Enter API key to enable")
        else:
            st.error("⚠️ OpenAI package not installed")
    
    # Initialize warehouse
    if not st.session_state.db_initialized:
        with st.spinner("Initializing database..."):
            warehouse = DataWarehouse()
            st.session_state.warehouse = warehouse
    else:
        warehouse = st.session_state.warehouse
    
    # Page routing
    if page == "📤 Import Data":
        import_page(warehouse)
    elif page == "🔍 Search & Export":
        search_page(warehouse)
    elif page == "📈 Dashboard":
        dashboard_page(warehouse)
    elif page == "📋 Import History":
        history_page(warehouse)
    elif page == "ℹ️ System Info":
        system_info_page(warehouse)

def import_page(warehouse: DataWarehouse):
    """File import interface"""
    st.header("📤 Import Data Files")
    
    if OPENAI_AVAILABLE and st.session_state.openai_api_key:
        st.markdown("""
        <div class="info-box">
            🤖 <strong>AI-Powered Parsing Enabled</strong> - Complex Excel files with merged cells 
            and multi-line headers will be automatically parsed using OpenAI.
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="warning-box">
            ⚠️ <strong>AI Parsing Not Available</strong> - Add OpenAI API key in sidebar for 
            better handling of complex Excel files.
        </div>
        """, unsafe_allow_html=True)
    
    with st.form("import_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            source_type = st.selectbox(
                "1. Source of Data *",
                ["Facebook Lead", "Property Portal", "Real Estate Expo", 
                 "Broker/Agent List", "Utility Consumer List", "School/Institutional Data",
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
            help="Upload multiple files. AI will help parse complex Excel files automatically."
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
                        if result['profiles_created'] > 0 or result['profiles_enriched'] > 0:
                            st.caption(f"   Created: {result['profiles_created']} | Enriched: {result['profiles_enriched']} | Invalid: {result['invalid_mobiles']}")
                    else:
                        st.error(f"❌ {file.name}: {result['message']}")

def search_page(warehouse: DataWarehouse):
    """Search and export interface"""
    st.header("🔍 Search & Export")
    
    col1, col2 = st.columns(2)
    
    with col1:
        search_text = st.text_input("🔍 Search", placeholder="Name, mobile, email, city...")
    
    with col2:
        classification = st.selectbox("Category", ["All", "Real Estate Trade", "Property Seeker", "Non-Real Estate"])
    
    if st.button("🔍 Search", type="primary", use_container_width=True):
        filters = {}
        if classification != "All":
            filters['classification'] = classification
        
        with st.spinner("Searching..."):
            results = warehouse.search(query=search_text if search_text else None, 
                                       filters=filters if filters else None,
                                       limit=1000)
            
            st.markdown(f"### 📊 Results: {len(results)} profiles found")
            
            if not results.empty:
                display_cols = ['profile_id', 'mobile', 'name', 'email', 'city', 'classification', 'record_count']
                available_cols = [col for col in display_cols if col in results.columns]
                st.dataframe(results[available_cols], use_container_width=True, height=400)
                
                st.markdown("---")
                if st.button("📥 Export Results to CSV"):
                    csv = results.to_csv(index=False).encode()
                    st.download_button("Download CSV", csv, f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
            else:
                st.info("No results found")

def dashboard_page(warehouse: DataWarehouse):
    """Analytics dashboard"""
    st.header("📈 Analytics Dashboard")
    
    stats = warehouse.get_statistics()
    
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
        
        if st.button("📥 Export History"):
            csv = history.to_csv(index=False).encode()
            st.download_button("Download CSV", csv, "import_history.csv", "text/csv")
    else:
        st.info("No import history yet")

def system_info_page(warehouse: DataWarehouse):
    """System information"""
    st.header("ℹ️ System Information")
    
    st.markdown("""
    ### 🤖 AI-Powered Real Estate Data Intelligence Platform
    
    **Version:** 3.0
    
    **Features:**
    - **AI-Powered Excel Parsing**: Uses OpenAI to parse complex Excel files with merged cells
    - **Smart Mobile Detection**: Automatically identifies mobile number columns
    - **Multi-Format Support**: Handles .xlsx, .xls, and .csv files
    - **Deduplication**: Uses mobile numbers as unique identifiers
    - **Dynamic Search**: Search across all data with filters
    - **Analytics Dashboard**: Visual insights into your data
    
    ### AI Capabilities
    
    When OpenAI API key is provided:
    - Parses complex Excel files with merged cells
    - Detects header rows automatically
    - Identifies mobile, name, email, city columns
    - Handles multi-line headers and formatting
    
    ### Requirements
    
    - **Python Packages**: streamlit, pandas, openpyxl, xlrd, openai
    - **OpenAI API Key**: Optional but recommended for complex Excel files
    
    ### Data Privacy
    
    - All processing happens in memory
    - No data is stored permanently
    - API keys are not saved permanently
    - OpenAI only receives column structures, not full data
    """)

if __name__ == "__main__":
    main()
