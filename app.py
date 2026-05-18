import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import hashlib
import re
import json
from datetime import datetime, timedelta
from pathlib import Path
import io
import base64
from typing import Dict, List, Any, Optional, Tuple
import warnings
from collections import defaultdict
import anthropic
import openpyxl
import xlrd
from io import BytesIO
import chardet
warnings.filterwarnings('ignore')

# Page configuration
st.set_page_config(
    page_title="AI-Powered Real Estate Data Warehouse",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .stat-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .stat-number {
        font-size: 2rem;
        font-weight: bold;
    }
    .stat-label {
        font-size: 0.9rem;
        opacity: 0.9;
    }
    .ai-badge {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        color: white;
        font-size: 0.8rem;
        display: inline-block;
        margin-left: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'data_warehouse' not in st.session_state:
    st.session_state.data_warehouse = pd.DataFrame()
if 'file_metadata' not in st.session_state:
    st.session_state.file_metadata = []
if 'query_history' not in st.session_state:
    st.session_state.query_history = []
if 'column_mappings' not in st.session_state:
    st.session_state.column_mappings = {}
if 'claude_client' not in st.session_state:
    st.session_state.claude_client = None
if 'processing_queue' not in st.session_state:
    st.session_state.processing_queue = []
if 'failed_files' not in st.session_state:
    st.session_state.failed_files = []

class AIDataProcessor:
    """AI-powered data processing with Claude API"""
    
    def __init__(self, api_key: str = None):
        self.client = None
        if api_key:
            try:
                self.client = anthropic.Anthropic(api_key=api_key)
            except Exception as e:
                pass
    
    def safe_convert_to_string(self, value: Any) -> str:
        """Safely convert any value to string without lower() errors"""
        if pd.isna(value) or value is None:
            return ""
        try:
            # Handle integers, floats, and other types
            if isinstance(value, (int, float)):
                return str(int(value)) if value == int(value) else str(value)
            return str(value).strip()
        except:
            return ""
    
    def detect_columns_with_ai(self, df: pd.DataFrame, file_name: str, target_columns: List[str]) -> Dict[str, str]:
        """Use Claude AI to intelligently detect column mappings"""
        if not self.client:
            return self.fallback_column_detection(df, target_columns)
        
        try:
            # Prepare sample data safely
            sample_data = []
            for _, row in df.head(5).iterrows():
                row_dict = {}
                for col in df.columns:
                    value = row[col]
                    if pd.isna(value):
                        row_dict[col] = None
                    elif isinstance(value, (int, float)):
                        row_dict[col] = str(int(value)) if value == int(value) else str(value)
                    else:
                        row_dict[col] = str(value)[:100]  # Limit string length
                sample_data.append(row_dict)
            
            columns_info = {col: str(df[col].dtype) for col in df.columns}
            
            # Create prompt for Claude
            prompt = f"""You are an AI assistant helping to map columns in a real estate data file.

File Name: {file_name}

Available columns in the file:
{json.dumps(columns_info, indent=2)}

Sample data (first 3 rows):
{json.dumps(sample_data[:3], indent=2, default=str)}

Target columns to map:
{json.dumps(target_columns, indent=2)}

Please analyze the column names and sample data to determine which existing columns correspond to each target column.
Return a JSON object mapping target columns to actual column names in the file.
If a target column cannot be mapped, map it to null.

Important rules:
1. For 'contact' column: Look for columns containing phone numbers (10-12 digits), or named: mobile, phone, contact, cell, telephone
2. For 'name' column: Look for columns with names, full names, customer names
3. For 'email' column: Look for columns with @ symbol or named email, e-mail
4. For 'address' column: Look for address, location, area columns
5. For 'city' column: Look for city, town, district columns
6. For 'source' column: Look for source, lead source columns
7. For 'category' column: Look for category, type, classification columns

Return ONLY the JSON mapping, no other text."""

            # Call Claude API
            message = self.client.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=1000,
                temperature=0,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Parse AI response
            response_text = message.content[0].text
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                mapping = json.loads(json_match.group())
                return mapping
            else:
                return self.fallback_column_detection(df, target_columns)
                
        except Exception as e:
            return self.fallback_column_detection(df, target_columns)
    
    def fallback_column_detection(self, df: pd.DataFrame, target_columns: List[str]) -> Dict[str, str]:
        """Fallback column detection using rules"""
        mapping = {}
        column_lower = {col: col.lower() for col in df.columns}
        
        # Comprehensive mapping rules
        mapping_rules = {
            'contact': ['contact', 'mobile', 'phone', 'cell', 'mob', 'telephone', 'whatsapp', 'ph', 'phone number', 'contact number', 'mobile number'],
            'name': ['name', 'full name', 'customer name', 'client name', 'party name', 'buyer name', 'seller name', 'lead name', 'campaign_name'],
            'email': ['email', 'e-mail', 'mail', 'email id', 'email address', 'mail id'],
            'address': ['address', 'addr', 'location', 'locality', 'area', 'street', 'full address', 'property address'],
            'city': ['city', 'town', 'district', 'location city'],
            'state': ['state', 'province', 'region', 'state name'],
            'pincode': ['pincode', 'pin', 'zip', 'postal', 'zipcode', 'postal code', 'pin code'],
            'source': ['source', 'lead source', 'data source', 'origin'],
            'category': ['category', 'type', 'classification', 'segment']
        }
        
        for target in target_columns:
            if target in mapping_rules:
                for rule in mapping_rules[target]:
                    for col, col_lower in column_lower.items():
                        if rule in col_lower:
                            mapping[target] = col
                            break
                    if target in mapping:
                        break
            
            # If not found, try data pattern detection
            if target not in mapping and target == 'contact':
                for col in df.columns:
                    try:
                        # Check first 20 non-null values
                        sample = df[col].dropna().head(20).astype(str)
                        # Check for phone number pattern
                        if sample.str.match(r'^[0-9]{10}$').any() or sample.str.match(r'^[0-9]{12}$').any():
                            mapping[target] = col
                            break
                    except:
                        continue
            
            # If still not found, set to None
            if target not in mapping:
                mapping[target] = None
        
        return mapping
    
    def read_file_with_fallback(self, file_obj) -> Optional[pd.DataFrame]:
        """Intelligently read Excel/CSV files with multiple fallback strategies"""
        
        # For old .xls files
        if file_obj.name.endswith('.xls'):
            try:
                # Try with xlrd engine first
                df = pd.read_excel(file_obj, engine='xlrd')
                if not df.empty:
                    return df
            except:
                pass
            
            try:
                # Try reading with openpyxl
                file_obj.seek(0)
                df = pd.read_excel(file_obj, engine='openpyxl')
                if not df.empty:
                    return df
            except:
                pass
            
            try:
                # Try reading as CSV
                file_obj.seek(0)
                df = pd.read_csv(file_obj, encoding='utf-8', on_bad_lines='skip')
                if not df.empty:
                    return df
            except:
                pass
            
            try:
                # Try different encoding
                file_obj.seek(0)
                result = chardet.detect(file_obj.read(10000))
                encoding = result['encoding'] if result['encoding'] else 'latin1'
                file_obj.seek(0)
                df = pd.read_csv(file_obj, encoding=encoding, on_bad_lines='skip')
                if not df.empty:
                    return df
            except:
                pass
        
        # For .xlsx files
        elif file_obj.name.endswith('.xlsx'):
            try:
                df = pd.read_excel(file_obj, engine='openpyxl')
                if not df.empty:
                    return df
            except:
                pass
            
            try:
                file_obj.seek(0)
                df = pd.read_excel(file_obj, engine='xlrd')
                if not df.empty:
                    return df
            except:
                pass
        
        # For CSV files
        else:
            encodings = ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']
            for encoding in encodings:
                try:
                    file_obj.seek(0)
                    df = pd.read_csv(file_obj, encoding=encoding, on_bad_lines='skip')
                    if not df.empty:
                        return df
                except:
                    continue
        
        return None

class AIWarehouse:
    """AI-powered data warehouse"""
    
    def __init__(self):
        api_key = st.session_state.get('claude_api_key')
        self.ai_processor = AIDataProcessor(api_key)
        self.data = st.session_state.data_warehouse
        self.primary_key = 'contact'
    
    def clean_contact(self, contact: Any) -> str:
        """Clean contact number to standard 10-digit format"""
        # Convert to string safely
        if pd.isna(contact) or contact is None:
            return ""
        
        # Handle different types
        try:
            if isinstance(contact, (int, float)):
                contact_str = str(int(contact)) if contact == int(contact) else str(contact)
            else:
                contact_str = str(contact).strip()
        except:
            return ""
        
        # Extract digits only
        digits = re.sub(r'\D', '', contact_str)
        
        # Standardize to 10 digits
        if len(digits) == 10:
            return digits
        elif len(digits) == 11 and digits.startswith('0'):
            return digits[1:]
        elif len(digits) == 12 and digits.startswith('91'):
            return digits[2:]
        elif len(digits) == 13 and digits.startswith('091'):
            return digits[3:]
        elif len(digits) > 10:
            # Take last 10 digits
            return digits[-10:]
        else:
            return ""
    
    def process_file(self, file_obj, metadata: Dict) -> Tuple[bool, str, Dict]:
        """Process a single file with comprehensive error handling"""
        try:
            # First check if file is empty
            if file_obj.size == 0:
                return False, "File is empty", {}
            
            # Read file with fallback strategies
            df = self.ai_processor.read_file_with_fallback(file_obj)
            
            if df is None or df.empty:
                return False, "Could not read file or file is empty", {}
            
            # Clean column names (remove extra spaces)
            df.columns = df.columns.str.strip()
            
            # Target columns
            target_columns = ['contact', 'name', 'email', 'address', 'city', 'state', 'pincode', 'source', 'category']
            
            # Detect column mappings
            column_mapping = self.ai_processor.detect_columns_with_ai(df, file_obj.name, target_columns)
            
            # Store mapping
            st.session_state.column_mappings[file_obj.name] = column_mapping
            
            # Apply renaming
            rename_dict = {}
            for target, source in column_mapping.items():
                if source and source in df.columns and source not in rename_dict:
                    rename_dict[source] = target
            
            if rename_dict:
                df = df.rename(columns=rename_dict)
            
            # Ensure all target columns exist
            for col in target_columns:
                if col not in df.columns:
                    df[col] = ""
            
            # Clean contact numbers safely
            if 'contact' in df.columns:
                df['contact'] = df['contact'].apply(lambda x: self.clean_contact(x))
                df['contact_valid'] = df['contact'].apply(lambda x: len(x) == 10 if x else False)
                # Remove rows with invalid contacts
                df = df[df['contact'] != ""]
            
            if df.empty:
                return False, "No valid contact numbers found", {}
            
            # Add metadata
            df['_source_file'] = file_obj.name
            df['_upload_date'] = metadata.get('upload_date', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            df['_source_type'] = metadata.get('source_type', 'Unknown')
            df['_category'] = metadata.get('category', 'Uncategorized')
            
            # Remove duplicates within the same file
            df = df.drop_duplicates(subset=['contact'], keep='first')
            
            # Merge with existing warehouse
            if st.session_state.data_warehouse.empty:
                st.session_state.data_warehouse = df
            else:
                # Get existing contacts
                existing_contacts = set(st.session_state.data_warehouse['contact'].tolist())
                
                # Only add new records (not existing in warehouse)
                new_records = df[~df['contact'].isin(existing_contacts)]
                
                if not new_records.empty:
                    st.session_state.data_warehouse = pd.concat(
                        [st.session_state.data_warehouse, new_records], 
                        ignore_index=True
                    )
                
                records_added = len(new_records)
                records_skipped = len(df) - records_added
            }
            
            file_info = {
                'file_name': file_obj.name,
                'records_added': len(df) if st.session_state.data_warehouse.empty else records_added,
                'records_skipped': 0 if st.session_state.data_warehouse.empty else records_skipped,
                'column_mapping': column_mapping,
                'upload_date': metadata.get('upload_date', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                'source_type': metadata.get('source_type', 'Unknown'),
                'category': metadata.get('category', 'Uncategorized')
            }
            
            return True, f"Successfully added {file_info['records_added']} records", file_info
            
        except Exception as e:
            return False, f"Error: {str(e)}", {}
    
    def dynamic_query(self, conditions: Dict) -> pd.DataFrame:
        """Execute dynamic query"""
        if st.session_state.data_warehouse.empty:
            return pd.DataFrame()
        
        df = st.session_state.data_warehouse.copy()
        
        # Apply filters
        for field, value in conditions.items():
            if field == 'search_text' and value:
                search_mask = pd.Series([False] * len(df))
                text_cols = ['name', 'email', 'address', 'city', 'contact']
                for col in text_cols:
                    if col in df.columns:
                        try:
                            search_mask |= df[col].astype(str).str.lower().str.contains(value.lower(), na=False)
                        except:
                            continue
                df = df[search_mask]
            
            elif field in df.columns and value and value != 'All':
                try:
                    df = df[df[field] == value]
                except:
                    continue
            
            elif field == 'contact' and value:
                contact_clean = self.clean_contact(value)
                if contact_clean:
                    df = df[df['contact'] == contact_clean]
        
        # Remove internal columns for display
        display_cols = [col for col in df.columns if not col.startswith('_')]
        return df[display_cols] if display_cols else df
    
    def get_statistics(self) -> Dict:
        """Get statistics"""
        if st.session_state.data_warehouse.empty:
            return {}
        
        df = st.session_state.data_warehouse
        
        stats = {
            'total_records': len(df),
            'unique_contacts': df['contact'].nunique() if 'contact' in df.columns else 0,
            'total_files': len(st.session_state.file_metadata),
            'valid_contacts': df['contact_valid'].sum() if 'contact_valid' in df.columns else 0
        }
        
        if '_source_type' in df.columns:
            stats['source_distribution'] = df['_source_type'].value_counts().to_dict()
        
        if '_category' in df.columns:
            stats['category_distribution'] = df['_category'].value_counts().to_dict()
        
        if 'city' in df.columns:
            stats['city_distribution'] = df['city'].value_counts().head(10).to_dict()
        
        return stats

def main():
    """Main application"""
    
    st.markdown('<div class="main-header">🤖 AI-Powered Real Estate Data Warehouse</div>', unsafe_allow_html=True)
    
    # Initialize warehouse
    warehouse = AIWarehouse()
    
    # API Key configuration in sidebar
    with st.sidebar:
        st.title("⚙️ Configuration")
        
        api_key = st.text_input("Claude API Key (Optional)", type="password", 
                                help="Enter your Claude API key for enhanced AI column detection")
        
        if api_key:
            st.session_state.claude_api_key = api_key
            st.success("✅ AI Ready!")
        
        st.markdown("---")
        st.title("📊 Navigation")
        
        page = st.radio(
            "Select Module",
            ["📤 Upload Files", "🔍 Dynamic Query", "📈 Analytics Dashboard", 
             "📁 File Management", "🤖 Column Mappings", "ℹ️ System Info"],
            index=0
        )
        
        st.markdown("---")
        
        # System stats
        if not st.session_state.data_warehouse.empty:
            st.markdown("### 📊 System Stats")
            st.metric("Total Records", f"{len(st.session_state.data_warehouse):,}")
            st.metric("Files Uploaded", f"{len(st.session_state.file_metadata)}")
    
    # Page routing
    if page == "📤 Upload Files":
        upload_files_page(warehouse)
    elif page == "🔍 Dynamic Query":
        dynamic_query_page(warehouse)
    elif page == "📈 Analytics Dashboard":
        analytics_dashboard_page(warehouse)
    elif page == "📁 File Management":
        file_management_page(warehouse)
    elif page == "🤖 Column Mappings":
        mappings_page(warehouse)
    elif page == "ℹ️ System Info":
        system_info_page(warehouse)

def upload_files_page(warehouse: AIWarehouse):
    """Handle file uploads"""
    st.header("📤 Upload Files")
    
    st.info("""
    🤖 **Features:**
    - Automatically detects contact numbers, names, emails, addresses
    - Handles Excel (.xlsx, .xls) and CSV files
    - Uses contact number as unique identifier
    - Prevents duplicate records
    """)
    
    with st.form("upload_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            source_type = st.selectbox(
                "Default Source Type",
                ["General", "MSEB", "Facebook Leads", "Property Portal", 
                 "Agent List", "School Data", "Doctor List", "Police Records",
                 "Broker List", "Expo Visitors", "Sales Data", "Other"]
            )
        
        with col2:
            category = st.selectbox(
                "Default Category",
                ["Real Estate Trade", "Property Seeker", "Non-Real Estate", "General"]
            )
        
        uploaded_files = st.file_uploader(
            "Choose Files (Excel or CSV)",
            type=['xlsx', 'xls', 'csv'],
            accept_multiple_files=True,
            help="Upload multiple files. System will auto-detect columns and use contact numbers as unique keys."
        )
        
        submitted = st.form_submit_button("🚀 Process Files", type="primary", use_container_width=True)
        
        if submitted and uploaded_files:
            process_files(warehouse, uploaded_files, source_type, category)

def process_files(warehouse: AIWarehouse, files, source_type, category):
    """Process multiple files"""
    progress_bar = st.progress(0)
    status_text = st.empty()
    results_container = st.container()
    
    success_count = 0
    error_count = 0
    total_records = 0
    failed_files = []
    
    for idx, file in enumerate(files):
        status_text.text(f"Processing: {file.name}... ({idx+1}/{len(files)})")
        
        metadata = {
            'upload_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'source_type': source_type,
            'category': category
        }
        
        success, message, file_info = warehouse.process_file(file, metadata)
        
        if success:
            success_count += 1
            total_records += file_info.get('records_added', 0)
            with results_container:
                st.success(f"✅ {file.name}: {message}")
                
                # Show column mapping if available
                if 'column_mapping' in file_info and file_info['column_mapping']:
                    mapping_summary = {k: v for k, v in file_info['column_mapping'].items() if v}
                    if mapping_summary:
                        st.caption(f"📋 Mapped: {mapping_summary}")
            
            # Store metadata
            st.session_state.file_metadata.append(file_info)
        else:
            error_count += 1
            failed_files.append(file.name)
            with results_container:
                st.error(f"❌ {file.name}: {message}")
        
        progress_bar.progress((idx + 1) / len(files))
    
    status_text.text("✅ Processing Complete!")
    
    # Summary
    st.markdown("---")
    st.subheader("📊 Processing Summary")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Files Processed", f"{success_count}/{len(files)}")
    with col2:
        st.metric("Files Failed", f"{error_count}")
    with col3:
        st.metric("Total Records Added", f"{total_records:,}")
    with col4:
        st.metric("Primary Key", "Contact Number")
    
    if failed_files:
        st.warning(f"⚠️ Failed files: {', '.join(failed_files)}")
    
    if success_count > 0:
        st.balloons()
        st.info("💡 Go to 'Column Mappings' page to see how columns were detected")

def dynamic_query_page(warehouse: AIWarehouse):
    """Dynamic query interface"""
    st.header("🔍 Dynamic Query")
    
    if st.session_state.data_warehouse.empty:
        st.warning("No data available. Please upload files first.")
        return
    
    col1, col2 = st.columns(2)
    
    with col1:
        search_text = st.text_input("🔍 Search Any Field", placeholder="Name, email, city, address...")
    
    with col2:
        contact_search = st.text_input("📱 Specific Contact Number", placeholder="Enter 10-digit number")
    
    col3, col4 = st.columns(2)
    
    with col3:
        if '_source_type' in st.session_state.data_warehouse.columns:
            sources = ['All'] + sorted(st.session_state.data_warehouse['_source_type'].unique().tolist())
            source_filter = st.selectbox("Filter by Source", sources)
        else:
            source_filter = "All"
    
    with col4:
        if '_category' in st.session_state.data_warehouse.columns:
            categories = ['All'] + sorted(st.session_state.data_warehouse['_category'].unique().tolist())
            category_filter = st.selectbox("Filter by Category", categories)
        else:
            category_filter = "All"
    
    if st.button("🔍 Execute Query", type="primary", use_container_width=True):
        conditions = {}
        
        if search_text:
            conditions['search_text'] = search_text
        if contact_search:
            conditions['contact'] = contact_search
        if source_filter != "All":
            conditions['_source_type'] = source_filter
        if category_filter != "All":
            conditions['_category'] = category_filter
        
        with st.spinner("Searching..."):
            results_df = warehouse.dynamic_query(conditions)
            
            st.markdown(f"### 📊 Results: {len(results_df)} records found")
            
            if not results_df.empty:
                # Select columns to display
                display_cols = ['contact', 'name', 'email', 'city', '_source_type', '_category']
                available_cols = [col for col in display_cols if col in results_df.columns]
                
                st.dataframe(results_df[available_cols], use_container_width=True, height=400)
                
                # Export option
                st.markdown("---")
                if st.button("📥 Export Results to CSV"):
                    csv = results_df.to_csv(index=False).encode()
                    st.download_button(
                        "Download CSV",
                        csv,
                        f"query_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        "text/csv"
                    )
            else:
                st.info("No records found matching your criteria")

def analytics_dashboard_page(warehouse: AIWarehouse):
    """Analytics dashboard"""
    st.header("📈 Analytics Dashboard")
    
    if st.session_state.data_warehouse.empty:
        st.warning("No data available. Please upload files first.")
        return
    
    stats = warehouse.get_statistics()
    df = st.session_state.data_warehouse
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Records", f"{stats.get('total_records', 0):,}")
    with col2:
        st.metric("Unique Contacts", f"{stats.get('unique_contacts', 0):,}")
    with col3:
        st.metric("Valid Contacts", f"{stats.get('valid_contacts', 0):,}")
    with col4:
        st.metric("Files Uploaded", f"{stats.get('total_files', 0)}")
    
    st.markdown("---")
    
    # Visualizations
    tab1, tab2, tab3 = st.tabs(["📊 Source Distribution", "🏷️ Category Distribution", "📍 Top Cities"])
    
    with tab1:
        if 'source_distribution' in stats and stats['source_distribution']:
            source_df = pd.DataFrame(list(stats['source_distribution'].items()), 
                                    columns=['Source', 'Count'])
            fig = px.pie(source_df, values='Count', names='Source', title='Records by Source', hole=0.3)
            fig.update_layout(height=500)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No source distribution data available")
    
    with tab2:
        if 'category_distribution' in stats and stats['category_distribution']:
            cat_df = pd.DataFrame(list(stats['category_distribution'].items()),
                                 columns=['Category', 'Count'])
            fig = px.bar(cat_df, x='Category', y='Count', title='Records by Category', 
                        color='Count', color_continuous_scale='Viridis')
            fig.update_layout(height=500)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No category distribution data available")
    
    with tab3:
        if 'city' in df.columns:
            city_counts = df['city'].value_counts().head(15)
            if not city_counts.empty:
                fig = px.bar(x=city_counts.values, y=city_counts.index, orientation='h',
                            title='Top 15 Cities', labels={'x': 'Count', 'y': 'City'},
                            color=city_counts.values, color_continuous_scale='Plasma')
                fig.update_layout(height=500)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No city data available")
        else:
            st.info("City column not found in data")

def mappings_page(warehouse: AIWarehouse):
    """Show column mappings"""
    st.header("🤖 Column Mappings")
    
    if not st.session_state.column_mappings:
        st.info("No files processed yet. Upload files to see column mappings.")
        return
    
    st.subheader("How Columns Were Mapped")
    
    for file_name, mapping in st.session_state.column_mappings.items():
        with st.expander(f"📄 {file_name}"):
            # Show mapping in a nice format
            mapping_df = pd.DataFrame([
                {"Target Column": k, "Source Column": v if v else "Not found"}
                for k, v in mapping.items()
            ])
            st.dataframe(mapping_df, use_container_width=True)

def file_management_page(warehouse: AIWarehouse):
    """File management"""
    st.header("📁 File Management")
    
    if st.session_state.data_warehouse.empty:
        st.info("No data to manage")
        return
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🗑️ Clear All Data", type="secondary", use_container_width=True):
            st.session_state.data_warehouse = pd.DataFrame()
            st.session_state.file_metadata = []
            st.session_state.column_mappings = {}
            st.success("All data cleared!")
            st.rerun()
    
    with col2:
        if st.button("📥 Export All Data", type="primary", use_container_width=True):
            export_df = st.session_state.data_warehouse.copy()
            # Remove internal columns
            export_df = export_df[[col for col in export_df.columns if not col.startswith('_')]]
            csv = export_df.to_csv(index=False).encode()
            st.download_button(
                "Download CSV",
                csv,
                f"full_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                "text/csv"
            )
    
    # Show file list
    if st.session_state.file_metadata:
        st.markdown("---")
        st.subheader("Uploaded Files History")
        files_df = pd.DataFrame(st.session_state.file_metadata)
        st.dataframe(files_df, use_container_width=True)

def system_info_page(warehouse: AIWarehouse):
    """System information"""
    st.header("ℹ️ System Information")
    
    st.markdown("""
    ### 🤖 AI-Powered Real Estate Data Warehouse
    
    **Version:** 2.0
    
    **Features:**
    - **Smart Column Detection**: Automatically identifies contact numbers, names, emails, and addresses
    - **Multi-Format Support**: Handles Excel (.xlsx, .xls) and CSV files
    - **Deduplication**: Uses contact numbers as unique identifiers
    - **Dynamic Querying**: Search across all data with multiple filters
    - **Analytics Dashboard**: Visual insights into your data
    
    ### How It Works
    
    1. **Upload Files**: Upload Excel or CSV files with any column structure
    2. **Auto-Detection**: System identifies contact numbers, names, emails, etc.
    3. **Deduplication**: Records are merged using contact numbers as keys
    4. **Query & Export**: Search, filter, and export consolidated data
    
    ### File Format Support
    
    - **Excel**: .xlsx (openpyxl), .xls (xlrd)
    - **CSV**: UTF-8, Latin-1, ISO-8859-1 encodings
    
    ### Data Privacy
    
    - All processing happens in memory
    - No data is stored permanently
    - API keys are not saved
    """)

if __name__ == "__main__":
    main()
