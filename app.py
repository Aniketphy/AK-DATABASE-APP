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

class AIDataProcessor:
    """AI-powered data processing with Claude API"""
    
    def __init__(self, api_key: str = None):
        self.client = None
        if api_key:
            try:
                self.client = anthropic.Anthropic(api_key=api_key)
                st.success("🤖 AI Assistant Ready!")
            except Exception as e:
                st.warning(f"AI setup: {str(e)}")
    
    def detect_columns_with_ai(self, df: pd.DataFrame, file_name: str, target_columns: List[str]) -> Dict[str, str]:
        """Use Claude AI to intelligently detect column mappings"""
        if not self.client:
            return self.fallback_column_detection(df, target_columns)
        
        try:
            # Prepare sample data for AI
            sample_data = df.head(10).to_dict('records')
            columns_info = {col: str(df[col].dtype) for col in df.columns}
            
            # Create prompt for Claude
            prompt = f"""You are an AI assistant helping to map columns in a real estate data file.

File Name: {file_name}

Available columns in the file:
{json.dumps(columns_info, indent=2)}

Sample data (first 5 rows):
{json.dumps(sample_data[:5], indent=2, default=str)}

Target columns to map:
{json.dumps(target_columns, indent=2)}

Please analyze the column names and sample data to determine which existing columns correspond to each target column.
Return a JSON object mapping target columns to actual column names in the file.
If a target column cannot be mapped, map it to null.
Consider:
1. Column name similarity (case-insensitive, partial matches)
2. Data patterns (phone numbers, emails, names, etc.)
3. Common variations (mobile/phone/contact, name/full_name, etc.)
4. Data types and formats

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
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                mapping = json.loads(json_match.group())
                return mapping
            else:
                return self.fallback_column_detection(df, target_columns)
                
        except Exception as e:
            st.warning(f"AI detection failed: {str(e)}. Using fallback method.")
            return self.fallback_column_detection(df, target_columns)
    
    def fallback_column_detection(self, df: pd.DataFrame, target_columns: List[str]) -> Dict[str, str]:
        """Fallback column detection using rules"""
        mapping = {}
        column_lower = {col: col.lower() for col in df.columns}
        
        # Comprehensive mapping rules
        mapping_rules = {
            'contact': ['contact', 'mobile', 'phone', 'cell', 'mob', 'telephone', 'whatsapp', 'ph', 'phone number', 'contact number'],
            'name': ['name', 'full name', 'customer name', 'client name', 'party name', 'buyer name', 'seller name', 'lead name'],
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
                    sample = df[col].head(20).astype(str)
                    # Check for phone number pattern
                    if sample.str.match(r'^[0-9]{10}$').any() or sample.str.match(r'^[0-9]{12}$').any():
                        mapping[target] = col
                        break
            
            # If still not found, set to null
            if target not in mapping:
                mapping[target] = None
        
        return mapping
    
    def fix_excel_engine(self, file_obj) -> pd.DataFrame:
        """Intelligently read Excel files with correct engine"""
        try:
            # Try reading with default engine
            if file_obj.name.endswith('.xls'):
                # For older .xls files
                df = pd.read_excel(file_obj, engine='xlrd')
            else:
                # For .xlsx files
                df = pd.read_excel(file_obj, engine='openpyxl')
            return df
        except Exception as e:
            try:
                # Try alternative engine
                if file_obj.name.endswith('.xls'):
                    df = pd.read_excel(file_obj, engine='openpyxl')
                else:
                    df = pd.read_excel(file_obj, engine='xlrd')
                return df
            except:
                # If both fail, try reading with raw data
                file_obj.seek(0)
                df = pd.read_excel(file_obj, engine=None)
                return df

class AIWarehouse:
    """AI-powered data warehouse"""
    
    def __init__(self):
        self.ai_processor = AIDataProcessor(st.session_state.get('claude_api_key'))
        self.data = st.session_state.data_warehouse
        self.primary_key = 'contact'  # Standardized primary key
    
    def process_file_with_ai(self, file_obj, metadata: Dict) -> Tuple[bool, str, Dict]:
        """Process file with AI-powered column detection"""
        try:
            # First, fix Excel engine issues
            if file_obj.name.endswith(('.xls', '.xlsx')):
                df = self.ai_processor.fix_excel_engine(file_obj)
            else:
                df = pd.read_csv(file_obj)
            
            if df.empty:
                return False, "File is empty", {}
            
            # Target columns we want to map
            target_columns = ['contact', 'name', 'email', 'address', 'city', 'state', 'pincode', 'source', 'category']
            
            # Use AI to detect column mappings
            column_mapping = self.ai_processor.detect_columns_with_ai(df, file_obj.name, target_columns)
            
            # Store mapping for this file
            st.session_state.column_mappings[file_obj.name] = column_mapping
            
            # Rename columns based on mapping
            rename_dict = {v: k for k, v in column_mapping.items() if v is not None and v in df.columns}
            if rename_dict:
                df = df.rename(columns=rename_dict)
            
            # Ensure all target columns exist
            for col in target_columns:
                if col not in df.columns:
                    df[col] = ""
            
            # Clean contact numbers (standardize to 10 digits)
            if 'contact' in df.columns:
                df['contact'] = df['contact'].astype(str).apply(self.clean_contact)
                df['contact_valid'] = df['contact'].str.match(r'^[0-9]{10}$')
            
            # Add metadata
            df['_source_file'] = file_obj.name
            df['_upload_date'] = metadata.get('upload_date', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            df['_source_type'] = metadata.get('source_type', 'Unknown')
            df['_category'] = metadata.get('category', 'Uncategorized')
            
            # Remove duplicates based on contact
            before_count = len(df)
            df = df.drop_duplicates(subset=['contact'], keep='first')
            after_count = len(df)
            
            # Merge with existing data
            if st.session_state.data_warehouse.empty:
                st.session_state.data_warehouse = df
            else:
                # Use contact as key for merging
                st.session_state.data_warehouse = pd.merge(
                    st.session_state.data_warehouse,
                    df,
                    on=['contact'],
                    how='outer',
                    suffixes=('', '_new')
                )
                
                # Merge additional fields
                for col in ['name', 'email', 'address', 'city', 'state', 'pincode']:
                    if f"{col}_new" in st.session_state.data_warehouse.columns:
                        st.session_state.data_warehouse[col] = st.session_state.data_warehouse[col].fillna(
                            st.session_state.data_warehouse[f"{col}_new"]
                        )
                        st.session_state.data_warehouse.drop(columns=[f"{col}_new"], inplace=True)
            
            file_info = {
                'file_name': file_obj.name,
                'records_added': after_count,
                'duplicates_removed': before_count - after_count,
                'column_mapping': column_mapping,
                'upload_date': metadata.get('upload_date', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                'source_type': metadata.get('source_type', 'Unknown'),
                'category': metadata.get('category', 'Uncategorized')
            }
            
            return True, f"Successfully added {after_count} records", file_info
            
        except Exception as e:
            return False, f"Error: {str(e)}", {}
    
    def clean_contact(self, contact: str) -> str:
        """Clean contact number to standard 10-digit format"""
        if pd.isna(contact) or contact == "":
            return ""
        
        # Extract digits only
        digits = re.sub(r'\D', '', str(contact))
        
        # Standardize to 10 digits
        if len(digits) == 10:
            return digits
        elif len(digits) == 11 and digits.startswith('0'):
            return digits[1:]
        elif len(digits) == 12 and digits.startswith('91'):
            return digits[2:]
        elif len(digits) == 13 and digits.startswith('091'):
            return digits[3:]
        else:
            return ""
    
    def dynamic_query(self, conditions: Dict) -> pd.DataFrame:
        """Execute dynamic query"""
        if st.session_state.data_warehouse.empty:
            return pd.DataFrame()
        
        df = st.session_state.data_warehouse.copy()
        
        # Apply filters
        for field, value in conditions.items():
            if field == 'search_text' and value:
                # Search across text fields
                search_mask = pd.Series([False] * len(df))
                text_cols = ['name', 'email', 'address', 'city', 'contact']
                for col in text_cols:
                    if col in df.columns:
                        search_mask |= df[col].astype(str).str.lower().str.contains(value.lower(), na=False)
                df = df[search_mask]
            
            elif field in df.columns and value and value != 'All':
                df = df[df[field] == value]
            
            elif field == 'contact' and value:
                contact_clean = self.clean_contact(value)
                if contact_clean:
                    df = df[df['contact'] == contact_clean]
        
        # Remove internal columns
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
        
        # Source distribution
        if '_source_type' in df.columns:
            stats['source_distribution'] = df['_source_type'].value_counts().to_dict()
        
        # Category distribution
        if '_category' in df.columns:
            stats['category_distribution'] = df['_category'].value_counts().to_dict()
        
        return stats

def main():
    """Main application"""
    
    st.markdown('<div class="main-header">🤖 AI-Powered Real Estate Data Warehouse</div>', unsafe_allow_html=True)
    
    # Initialize warehouse
    warehouse = AIWarehouse()
    
    # API Key configuration in sidebar
    with st.sidebar:
        st.title("⚙️ Configuration")
        
        # Claude API Key input
        api_key = st.text_input("Claude API Key", type="password", 
                                help="Enter your Claude API key for AI-powered column detection")
        
        if api_key:
            st.session_state.claude_api_key = api_key
            if not st.session_state.get('claude_client'):
                st.session_state.claude_client = anthropic.Anthropic(api_key=api_key)
                st.success("✅ AI Assistant Configured!")
        
        st.markdown("---")
        st.title("📊 Navigation")
        
        page = st.radio(
            "Select Module",
            ["📤 Upload Files", "🔍 Dynamic Query", "📈 Analytics Dashboard", 
             "📁 File Management", "🤖 AI Column Mapping", "ℹ️ System Info"],
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
    elif page == "🤖 AI Column Mapping":
        ai_mapping_page(warehouse)
    elif page == "ℹ️ System Info":
        system_info_page(warehouse)

def upload_files_page(warehouse: AIWarehouse):
    """Handle file uploads with AI processing"""
    st.header("📤 Upload Files with AI Processing")
    
    st.info("""
    🤖 **AI-Powered Processing:**
    - Automatically detects column mappings using Claude AI
    - Handles various Excel formats (.xls, .xlsx, .csv)
    - Standardizes contact numbers to 10 digits
    - Uses contact number as primary key for deduplication
    """)
    
    with st.form("upload_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            source_type = st.selectbox(
                "Source Type",
                ["General", "MSEB", "Facebook Leads", "Property Portal", 
                 "Agent List", "School Data", "Doctor List", "Police Records",
                 "Broker List", "Expo Visitors", "Sales Data", "Other"]
            )
        
        with col2:
            category = st.selectbox(
                "Category",
                ["Real Estate Trade", "Property Seeker", "Non-Real Estate", "General"]
            )
        
        uploaded_files = st.file_uploader(
            "Choose Files (Excel or CSV)",
            type=['xlsx', 'xls', 'csv'],
            accept_multiple_files=True,
            help="Upload any number of files. AI will automatically detect column structures."
        )
        
        submitted = st.form_submit_button("🚀 Process with AI", type="primary", use_container_width=True)
        
        if submitted and uploaded_files:
            process_files_with_ai(warehouse, uploaded_files, source_type, category)

def process_files_with_ai(warehouse: AIWarehouse, files, source_type, category):
    """Process files using AI"""
    progress_bar = st.progress(0)
    status_text = st.empty()
    results_container = st.container()
    
    success_count = 0
    error_count = 0
    total_records = 0
    
    for idx, file in enumerate(files):
        status_text.text(f"🤖 AI Processing: {file.name}... ({idx+1}/{len(files)})")
        
        metadata = {
            'upload_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'source_type': source_type,
            'category': category
        }
        
        success, message, file_info = warehouse.process_file_with_ai(file, metadata)
        
        if success:
            success_count += 1
            total_records += file_info.get('records_added', 0)
            with results_container:
                st.success(f"✅ {file.name}: {message}")
                if 'column_mapping' in file_info:
                    st.caption(f"📋 AI Mapping: {file_info['column_mapping']}")
        else:
            error_count += 1
            with results_container:
                st.error(f"❌ {file.name}: {message}")
        
        progress_bar.progress((idx + 1) / len(files))
    
    status_text.text("✅ AI Processing Complete!")
    
    # Summary
    st.markdown("---")
    st.subheader("📊 Processing Summary")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Files Processed", f"{success_count}/{len(files)}")
    with col2:
        st.metric("Total Records Added", f"{total_records:,}")
    with col3:
        st.metric("Primary Key", "Contact Number")
    
    if success_count > 0:
        st.balloons()
        st.info("💡 Tip: Check the 'AI Column Mapping' page to see how AI mapped columns for each file")

def dynamic_query_page(warehouse: AIWarehouse):
    """Dynamic query interface"""
    st.header("🔍 Dynamic Query Builder")
    
    if st.session_state.data_warehouse.empty:
        st.warning("No data available. Please upload files first.")
        return
    
    st.markdown("### Query Your Data Warehouse")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        search_text = st.text_input("🔍 Search Any Field", placeholder="Name, email, address...")
    
    with col2:
        if '_source_type' in st.session_state.data_warehouse.columns:
            sources = ['All'] + sorted(st.session_state.data_warehouse['_source_type'].unique().tolist())
            source_filter = st.selectbox("Filter by Source", sources)
        else:
            source_filter = "All"
    
    with col3:
        if '_category' in st.session_state.data_warehouse.columns:
            categories = ['All'] + sorted(st.session_state.data_warehouse['_category'].unique().tolist())
            category_filter = st.selectbox("Filter by Category", categories)
        else:
            category_filter = "All"
    
    # Specific contact search
    st.markdown("---")
    contact_search = st.text_input("📱 Search Specific Contact Number", placeholder="Enter 10-digit contact number")
    
    # Execute query
    if st.button("🔍 Execute Query", type="primary", use_container_width=True):
        conditions = {}
        
        if search_text:
            conditions['search_text'] = search_text
        if source_filter != "All":
            conditions['_source_type'] = source_filter
        if category_filter != "All":
            conditions['_category'] = category_filter
        if contact_search:
            conditions['contact'] = contact_search
        
        with st.spinner("Searching..."):
            results_df = warehouse.dynamic_query(conditions)
            
            st.markdown(f"### 📊 Results: {len(results_df)} records found")
            
            if not results_df.empty:
                # Display results
                display_cols = ['contact', 'name', 'email', 'city', '_source_type', '_category']
                available_cols = [col for col in display_cols if col in results_df.columns]
                
                st.dataframe(results_df[available_cols], use_container_width=True, height=400)
                
                # Export
                st.markdown("---")
                col1, col2 = st.columns(2)
                with col1:
                    export_format = st.selectbox("Export Format", ["CSV", "Excel"])
                with col2:
                    export_name = st.text_input("Filename", value=f"query_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                
                if st.button("📥 Download Results"):
                    if export_format == "CSV":
                        csv = results_df.to_csv(index=False).encode()
                        st.download_button("Download CSV", csv, f"{export_name}.csv", "text/csv")
                    else:
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            results_df.to_excel(writer, sheet_name='Results', index=False)
                        st.download_button("Download Excel", output.getvalue(), f"{export_name}.xlsx", 
                                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
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
        st.metric("Total Records", f"{stats['total_records']:,}")
    with col2:
        st.metric("Unique Contacts", f"{stats['unique_contacts']:,}")
    with col3:
        st.metric("Valid Contacts", f"{stats['valid_contacts']:,}")
    with col4:
        st.metric("Files Uploaded", f"{stats['total_files']}")
    
    st.markdown("---")
    
    # Visualizations
    tab1, tab2 = st.tabs(["📊 Distributions", "📈 Data Overview"])
    
    with tab1:
        col_a, col_b = st.columns(2)
        
        with col_a:
            if 'source_distribution' in stats and stats['source_distribution']:
                source_df = pd.DataFrame(list(stats['source_distribution'].items()), 
                                        columns=['Source', 'Count'])
                fig = px.pie(source_df, values='Count', names='Source', title='Records by Source', hole=0.3)
                st.plotly_chart(fig, use_container_width=True)
        
        with col_b:
            if 'category_distribution' in stats and stats['category_distribution']:
                cat_df = pd.DataFrame(list(stats['category_distribution'].items()),
                                     columns=['Category', 'Count'])
                fig = px.bar(cat_df, x='Category', y='Count', title='Records by Category', color='Count')
                st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        # Top cities
        if 'city' in df.columns:
            city_counts = df['city'].value_counts().head(10)
            fig = px.bar(x=city_counts.values, y=city_counts.index, orientation='h',
                        title='Top 10 Cities', labels={'x': 'Count', 'y': 'City'})
            st.plotly_chart(fig, use_container_width=True)

def ai_mapping_page(warehouse: AIWarehouse):
    """Show AI column mappings"""
    st.header("🤖 AI Column Mapping History")
    
    if not st.session_state.column_mappings:
        st.info("No files processed yet. Upload files to see AI column mappings.")
        return
    
    st.subheader("How AI Mapped Your Files")
    
    for file_name, mapping in st.session_state.column_mappings.items():
        with st.expander(f"📄 {file_name}"):
            st.json(mapping)
            
            # Show AI explanation
            st.markdown("**🤖 AI Analysis:**")
            st.caption("AI automatically detected and mapped columns based on column names and data patterns")

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
            csv = export_df.to_csv(index=False).encode()
            st.download_button("Download CSV", csv, f"full_export_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")
    
    # Show file list
    if st.session_state.file_metadata:
        st.markdown("---")
        st.subheader("Uploaded Files")
        files_df = pd.DataFrame(st.session_state.file_metadata)
        st.dataframe(files_df, use_container_width=True)

def system_info_page(warehouse: AIWarehouse):
    """System information"""
    st.header("ℹ️ System Information")
    
    st.markdown("""
    ### 🤖 AI-Powered Real Estate Data Warehouse
    
    **Features:**
    - **AI Column Detection**: Uses Claude AI to automatically map columns from any file structure
    - **Smart Error Handling**: Automatically fixes Excel format issues and missing columns
    - **Contact Number Standardization**: Automatically standardizes contact numbers to 10 digits
    - **Intelligent Deduplication**: Uses contact numbers as primary key
    - **Dynamic Querying**: Search across all data with multiple filters
    
    ### How AI Helps
    
    1. **Column Mapping**: AI analyzes column names and sample data to identify contact numbers, names, emails, addresses, etc.
    2. **Format Detection**: Automatically handles different Excel formats (.xls, .xlsx)
    3. **Data Cleaning**: Standardizes phone numbers and handles missing values
    
    ### Supported File Formats
    - Excel (.xlsx, .xls) with automatic engine detection
    - CSV files
    
    ### Privacy Note
    - No data is stored permanently
    - AI processing uses only column structures, not actual data values
    - API keys are not stored
    """)

if __name__ == "__main__":
    main()
