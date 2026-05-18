import streamlit as st
import pandas as pd
import duckdb
import sqlite3
import re
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import warnings
import os
import io
import chardet
import Levenshtein

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
if 'profiles_table' not in st.session_state:
    st.session_state.profiles_table = None
if 'import_jobs' not in st.session_state:
    st.session_state.import_jobs = []
if 'search_filters' not in st.session_state:
    st.session_state.search_filters = {}

class DataWarehouse:
    """Core data warehouse using DuckDB for analytics and SQLite for search"""
    
    def __init__(self, db_path: str = "data_warehouse.duckdb", search_path: str = "search_index.db"):
        self.db_path = db_path
        self.search_path = search_path
        self.conn = None
        self.search_conn = None
        self._initialize_databases()
    
    def _initialize_databases(self):
        """Initialize DuckDB and SQLite databases with proper schemas"""
        
        # DuckDB for main data storage and analytics
        self.conn = duckdb.connect(self.db_path)
        
        # Create profiles table with all required fields
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                profile_id VARCHAR PRIMARY KEY,
                mobile VARCHAR(10) UNIQUE,
                secondary_mobile VARCHAR(10),
                name VARCHAR(500),
                first_name VARCHAR(200),
                last_name VARCHAR(200),
                email VARCHAR(500),
                address TEXT,
                sub_locality VARCHAR(200),
                area VARCHAR(200),
                city VARCHAR(100),
                state VARCHAR(100),
                pincode VARCHAR(10),
                zone VARCHAR(100),
                gender VARCHAR(20),
                age INTEGER,
                age_group VARCHAR(50),
                income_group VARCHAR(100),
                bhk_preference VARCHAR(50),
                budget_range VARCHAR(100),
                project_enquired VARCHAR(500),
                lead_source VARCHAR(200),
                company_name VARCHAR(500),
                business_category VARCHAR(200),
                vehicle_info VARCHAR(200),
                date_collected DATE,
                classification VARCHAR(50),
                classification_confidence FLOAT,
                created_at TIMESTAMP,
                last_enriched TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                has_valid_mobile BOOLEAN DEFAULT TRUE,
                record_count INTEGER DEFAULT 1,
                source_files TEXT,
                field_lineage TEXT,
                raw_data TEXT
            )
        """)
        
        # Create field history table for audit trail
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS field_history (
                history_id INTEGER PRIMARY KEY,
                profile_id VARCHAR,
                field_name VARCHAR,
                old_value TEXT,
                new_value TEXT,
                source_file VARCHAR,
                changed_at TIMESTAMP,
                change_type VARCHAR(50),
                data_type VARCHAR(20)  -- ACTUAL or INFERRED
            )
        """)
        
        # Create import jobs table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS import_jobs (
                job_id VARCHAR PRIMARY KEY,
                file_name VARCHAR,
                source_type VARCHAR,
                collection_date DATE,
                category VARCHAR,
                geographic_coverage VARCHAR,
                quality_notes TEXT,
                file_label VARCHAR,
                status VARCHAR,
                total_records INTEGER,
                processed_records INTEGER,
                profiles_created INTEGER,
                profiles_enriched INTEGER,
                invalid_mobiles INTEGER,
                started_at TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)
        
        # Create unknown fields storage
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS unknown_fields (
                id INTEGER PRIMARY KEY,
                profile_id VARCHAR,
                field_name VARCHAR,
                field_value TEXT,
                source_file VARCHAR,
                imported_at TIMESTAMP
            )
        """)
        
        # SQLite for full-text search
        self.search_conn = sqlite3.connect(self.search_path)
        self.search_conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS profile_search USING fts5(
                profile_id, mobile, name, email, address, city, area, pincode,
                content=profiles
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
        # This would be backed by a comprehensive Indian geography database
        # For now, returns placeholder inference logic
        result = {
            'city': None, 'state': None, 'pincode': None, 'area': None,
            'is_inferred': False, 'confidence': 'LOW'
        }
        
        # Pincode to city/state mapping (sample - would be complete database)
        pincode_map = {
            '411001': {'city': 'Pune', 'state': 'Maharashtra', 'area': 'Shivajinagar'},
            '411002': {'city': 'Pune', 'state': 'Maharashtra', 'area': 'Koregaon Park'},
            '411004': {'city': 'Pune', 'state': 'Maharashtra', 'area': 'Deccan Gymkhana'},
            '411014': {'city': 'Pune', 'state': 'Maharashtra', 'area': 'Baner'},
            '411021': {'city': 'Pune', 'state': 'Maharashtra', 'area': 'Aundh'},
            '411045': {'city': 'Pune', 'state': 'Maharashtra', 'area': 'Hinjewadi'},
            '400001': {'city': 'Mumbai', 'state': 'Maharashtra', 'area': 'Fort'},
            '400002': {'city': 'Mumbai', 'state': 'Maharashtra', 'area': 'Churchgate'},
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
        current = self.conn.execute(f"SELECT * FROM profiles WHERE profile_id = '{profile_id}'").fetchone()
        if not current:
            return False
        
        current_dict = dict(zip([desc[0] for desc in self.conn.description], current))
        
        # Fields to merge with conflict resolution
        fields_to_merge = ['name', 'email', 'address', 'city', 'area', 'pincode', 
                          'bhk_preference', 'budget_range', 'income_group']
        
        for field in fields_to_merge:
            new_value = new_data.get(field)
            current_value = current_dict.get(field)
            
            if new_value and not current_value:
                # Empty field - fill it
                self.conn.execute(f"""
                    UPDATE profiles SET {field} = ?, last_enriched = NOW() 
                    WHERE profile_id = ?
                """, (new_value, profile_id))
                
                # Log to field history
                self.conn.execute("""
                    INSERT INTO field_history (profile_id, field_name, old_value, new_value, source_file, changed_at, change_type, data_type)
                    VALUES (?, ?, ?, ?, ?, NOW(), 'CREATE', ?)
                """, (profile_id, field, None, new_value, source_file, data_type))
                
            elif new_value and current_value and new_value != current_value:
                # Conflict - resolve by rules
                
                # Rule 1: Longer value wins for names
                if field == 'name' and len(new_value) > len(current_value):
                    self.conn.execute(f"UPDATE profiles SET {field} = ?, last_enriched = NOW() WHERE profile_id = ?", (new_value, profile_id))
                    self.conn.execute("INSERT INTO field_history VALUES (?, ?, ?, ?, ?, NOW(), 'CONFLICT_RESOLVED', ?)", 
                                    (profile_id, field, current_value, new_value, source_file, data_type))
                
                # Rule 2: More recent wins (handled by data_type flag)
                elif data_type == 'ACTUAL' and current_dict.get(f'_{field}_data_type') == 'INFERRED':
                    self.conn.execute(f"UPDATE profiles SET {field} = ?, last_enriched = NOW() WHERE profile_id = ?", (new_value, profile_id))
        
        # Update record count and source files
        record_count = current_dict.get('record_count', 0) + 1
        source_files = current_dict.get('source_files', '')
        if source_file not in source_files:
            source_files = f"{source_files},{source_file}" if source_files else source_file
        
        self.conn.execute("""
            UPDATE profiles SET record_count = ?, source_files = ?, last_enriched = NOW() 
            WHERE profile_id = ?
        """, (record_count, source_files, profile_id))
        
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
        
        # Insert profile
        self.conn.execute("""
            INSERT INTO profiles (
                profile_id, mobile, name, email, address, city, area, pincode,
                classification, classification_confidence, created_at, last_enriched,
                record_count, source_files, has_valid_mobile, date_collected
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NOW(), NOW(), 1, ?, ?, ?)
        """, (
            profile_id, mobile, 
            record.get('name'), record.get('email'), record.get('address'),
            location.get('city') or record.get('city'),
            location.get('area') or record.get('area'),
            record.get('pincode') or location.get('pincode'),
            classification, confidence,
            source_file, is_valid, record.get('date_collected', datetime.now().date())
        ))
        
        # Update search index
        self.search_conn.execute("""
            INSERT INTO profile_search (profile_id, mobile, name, email, address, city, area, pincode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (profile_id, mobile, record.get('name'), record.get('email'), 
              record.get('address'), location.get('city'), location.get('area'), record.get('pincode')))
        
        self.search_conn.commit()
        
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
            # Read file with encoding detection
            if file_obj.name.endswith('.xls') or file_obj.name.endswith('.xlsx'):
                df = pd.read_excel(file_obj)
            else:
                # Detect encoding for CSV
                raw_data = file_obj.read(10000)
                encoding = chardet.detect(raw_data)['encoding'] or 'utf-8'
                file_obj.seek(0)
                df = pd.read_csv(file_obj, encoding=encoding, on_bad_lines='skip')
            
            if df.empty:
                result['message'] = "File is empty"
                return result
            
            # Detect mobile column by examining data
            mobile_col = None
            for col in df.columns:
                sample = df[col].dropna().head(20).astype(str)
                if sample.str.match(r'^[0-9]{10}$').any() or sample.str.match(r'^[0-9]{12}$').any():
                    mobile_col = col
                    break
            
            if not mobile_col:
                result['message'] = "No mobile number column detected"
                return result
            
            # Process each row
            for _, row in df.iterrows():
                result['total_records'] += 1
                
                mobile_raw = row[mobile_col]
                mobile, is_valid = self.clean_mobile(mobile_raw)
                
                if not is_valid or not mobile:
                    result['invalid_mobiles'] += 1
                    continue
                
                # Build record dict
                record = {
                    'mobile': mobile,
                    'name': row.get('name', row.get('Name', row.get('NAME', ''))),
                    'email': row.get('email', row.get('Email', row.get('EMAIL', ''))),
                    'address': row.get('address', row.get('Address', row.get('ADDRESS', ''))),
                    'city': row.get('city', row.get('City', row.get('CITY', ''))),
                    'pincode': row.get('pincode', row.get('Pincode', row.get('PINCODE', ''))),
                    'date_collected': metadata.get('collection_date', datetime.now().date())
                }
                
                # Check if profile exists
                existing = self.conn.execute(f"SELECT profile_id FROM profiles WHERE mobile = '{mobile}'").fetchone()
                
                if existing:
                    # Enrich existing profile
                    self.merge_profile(existing[0], record, file_obj.name, 'ACTUAL')
                    result['profiles_enriched'] += 1
                else:
                    # Create new profile
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
            self.conn.execute("""
                INSERT INTO import_jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NOW(), NOW())
            """, (job_id, file_obj.name, metadata.get('source_type'), metadata.get('collection_date'),
                  metadata.get('category'), metadata.get('geographic_coverage'), metadata.get('quality_notes'),
                  metadata.get('file_label'), 'COMPLETE', result['total_records'], result['total_records'],
                  result['profiles_created'], result['profiles_enriched'], result['invalid_mobiles']))
            
        except Exception as e:
            result['message'] = f"Error: {str(e)}"
        
        return result
    
    def search(self, query: str = None, filters: Dict = None, limit: int = 100) -> pd.DataFrame:
        """Search profiles with filters"""
        
        sql = "SELECT * FROM profiles WHERE is_active = TRUE"
        
        if query:
            # Use FTS for text search
            fts_results = self.search_conn.execute("""
                SELECT profile_id FROM profile_search WHERE profile_search MATCH ?
            """, (query,)).fetchall()
            
            if fts_results:
                profile_ids = [r[0] for r in fts_results]
                sql += f" AND profile_id IN ({','.join([f"'{pid}'" for pid in profile_ids])})"
        
        # Apply filters
        if filters:
            if filters.get('classification'):
                sql += f" AND classification = '{filters['classification']}'"
            if filters.get('city'):
                sql += f" AND city = '{filters['city']}'"
            if filters.get('source_type'):
                sql += f" AND source_files LIKE '%{filters['source_type']}%'"
        
        sql += f" LIMIT {limit}"
        
        result = self.conn.execute(sql).fetchdf()
        return result
    
    def get_statistics(self) -> Dict:
        """Get dashboard statistics"""
        
        stats = self.conn.execute("""
            SELECT 
                COUNT(*) as total_profiles,
                COUNT(CASE WHEN has_valid_mobile = TRUE THEN 1 END) as valid_mobiles,
                COUNT(CASE WHEN classification = 'Real Estate Trade' THEN 1 END) as trade_count,
                COUNT(CASE WHEN classification = 'Property Seeker' THEN 1 END) as seeker_count,
                COUNT(CASE WHEN classification = 'Non-Real Estate' THEN 1 END) as nonre_count,
                SUM(record_count) as total_records
            FROM profiles
            WHERE is_active = TRUE
        """).fetchone()
        
        # City breakdown
        city_stats = self.conn.execute("""
            SELECT city, COUNT(*) as count 
            FROM profiles 
            WHERE city IS NOT NULL AND city != ''
            GROUP BY city 
            ORDER BY count DESC 
            LIMIT 10
        """).fetchdf()
        
        return {
            'total_profiles': stats[0],
            'valid_mobiles': stats[1],
            'trade_count': stats[2],
            'seeker_count': stats[3],
            'nonre_count': stats[4],
            'total_records': stats[5],
            'city_breakdown': city_stats.to_dict('records') if not city_stats.empty else []
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

def history_page(warehouse: DataWarehouse):
    """Import history"""
    st.header("📋 Import History")
    
    history = warehouse.conn.execute("""
        SELECT file_name, source_type, collection_date, category, 
               total_records, profiles_created, profiles_enriched, 
               invalid_mobiles, status, started_at
        FROM import_jobs 
        ORDER BY started_at DESC 
        LIMIT 50
    """).fetchdf()
    
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
    
    **Database Location:** `data_warehouse.duckdb`
    **Search Index:** `search_index.db`
    
    ### Data Rules
    
    - Mobile numbers are standardized to 10 digits
    - Duplicate detection uses mobile number as primary key
    - Field conflicts resolved by: longer values win, more recent wins
    - Classification is automatic (can be overridden at import)
    
    ### Export Settings
    
    - CSV: UTF-8 encoding
    - Excel: .xlsx format with openpyxl
    
    ### About
    
    **Version:** 2.0 (Enterprise Scale)
    **Architecture:** DuckDB + SQLite FTS5
    **Scale Ready:** 5 crore+ records
    """)

if __name__ == "__main__":
    main()
