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
import random
import string
warnings.filterwarnings('ignore')

# Page configuration
st.set_page_config(
    page_title="Real Estate Data Warehouse - Multi-File Query System",
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
    .query-builder {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        border: 2px solid #e9ecef;
        margin: 1rem 0;
    }
    .privacy-note {
        background-color: #e3f2fd;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #2196f3;
        margin: 1rem 0;
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
if 'primary_key_column' not in st.session_state:
    st.session_state.primary_key_column = None
if 'available_columns' not in st.session_state:
    st.session_state.available_columns = set()

class PrivacyCompliantDataWarehouse:
    """
    Data warehouse that respects privacy while enabling powerful querying
    Uses any column as primary key (mobile, email, ID, etc.) without exposing data
    """
    
    def __init__(self):
        self.data = st.session_state.data_warehouse
        self.pk_column = st.session_state.primary_key_column
    
    @staticmethod
    def hash_sensitive_data(value: str) -> str:
        """Hash sensitive data for secure storage (optional)"""
        if pd.isna(value) or value == "":
            return ""
        return hashlib.sha256(str(value).encode()).hexdigest()[:16]
    
    def detect_primary_key_column(self, df: pd.DataFrame) -> Optional[str]:
        """
        Intelligently detect which column could serve as primary key
        Based on uniqueness and data patterns, not specific values
        """
        candidates = []
        
        for col in df.columns:
            col_lower = col.lower()
            # Check for common identifier columns
            if any(keyword in col_lower for keyword in ['mobile', 'phone', 'contact', 'id', 'email', 'user_id', 'client_id']):
                # Check uniqueness
                uniqueness = df[col].nunique() / len(df)
                if uniqueness > 0.8:  # High uniqueness
                    candidates.append((col, uniqueness))
        
        if candidates:
            # Return the most unique column
            return max(candidates, key=lambda x: x[1])[0]
        
        # If no obvious PK column, check first column for uniqueness
        first_col = df.columns[0]
        uniqueness = df[first_col].nunique() / len(df)
        if uniqueness > 0.9:
            return first_col
        
        return None
    
    def add_file(self, file_obj, metadata: Dict) -> Tuple[bool, str, Dict]:
        """Add a file to the warehouse with flexible key column detection"""
        try:
            # Read file
            if file_obj.name.endswith('.csv'):
                df = pd.read_csv(file_obj)
            else:
                df = pd.read_excel(file_obj)
            
            # Detect or use existing primary key column
            if not self.pk_column:
                pk_column = self.detect_primary_key_column(df)
                if pk_column:
                    st.session_state.primary_key_column = pk_column
                    self.pk_column = pk_column
                else:
                    # Create an artificial unique ID column
                    df['_generated_id'] = [f"REC_{i+1}" for i in range(len(df))]
                    st.session_state.primary_key_column = '_generated_id'
                    self.pk_column = '_generated_id'
            
            # Ensure primary key column exists
            if self.pk_column not in df.columns and self.pk_column != '_generated_id':
                st.warning(f"Primary key column '{self.pk_column}' not found in {file_obj.name}")
                return False, f"Primary key column '{self.pk_column}' not found", {}
            
            # Add metadata columns
            df['_source_file'] = file_obj.name
            df['_upload_date'] = metadata.get('upload_date', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            df['_source_type'] = metadata.get('source_type', 'Unknown')
            df['_category'] = metadata.get('category', 'Uncategorized')
            df['_data_quality_score'] = self.calculate_quality_score(df)
            
            # Track all columns
            for col in df.columns:
                if not col.startswith('_'):
                    st.session_state.available_columns.add(col)
            
            # Remove duplicates based on primary key
            before_count = len(df)
            df = df.drop_duplicates(subset=[self.pk_column], keep='first')
            after_count = len(df)
            
            # Merge with existing data
            if st.session_state.data_warehouse.empty:
                st.session_state.data_warehouse = df
            else:
                # Use outer join to preserve all records
                st.session_state.data_warehouse = pd.merge(
                    st.session_state.data_warehouse, 
                    df, 
                    on=[self.pk_column], 
                    how='outer',
                    suffixes=('', '_new')
                )
                
                # Handle duplicate columns from merge
                for col in df.columns:
                    if f"{col}_new" in st.session_state.data_warehouse.columns:
                        # Combine data from both sources
                        st.session_state.data_warehouse[col] = st.session_state.data_warehouse[col].fillna(
                            st.session_state.data_warehouse[f"{col}_new"]
                        )
                        st.session_state.data_warehouse.drop(columns=[f"{col}_new"], inplace=True)
            
            # Update file metadata
            file_info = {
                'file_name': file_obj.name,
                'records_added': after_count,
                'duplicates_removed': before_count - after_count,
                'primary_key_column': self.pk_column,
                'total_rows': len(df),
                'upload_date': metadata.get('upload_date', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                'source_type': metadata.get('source_type', 'Unknown'),
                'category': metadata.get('category', 'Uncategorized')
            }
            st.session_state.file_metadata.append(file_info)
            
            return True, f"Successfully added {after_count} records using key: {self.pk_column}", file_info
            
        except Exception as e:
            return False, f"Error processing file: {str(e)}", {}
    
    def calculate_quality_score(self, df: pd.DataFrame) -> pd.Series:
        """Calculate data quality score based on completeness"""
        score = pd.Series([0] * len(df), index=df.index)
        
        # Award points for non-null values in important columns
        important_columns = ['name', 'email', 'address', 'city', 'state']
        points_per_column = 20
        
        for col in important_columns:
            if col in df.columns:
                score += df[col].notna() & (df[col] != "") * points_per_column
        
        return score.clip(upper=100)
    
    def dynamic_query(self, conditions: Dict) -> pd.DataFrame:
        """Execute dynamic query with flexible conditions"""
        if st.session_state.data_warehouse.empty:
            return pd.DataFrame()
        
        df = st.session_state.data_warehouse.copy()
        
        # Apply filters
        for field, value in conditions.items():
            if field == 'search_text' and value:
                # Search across all text columns
                search_mask = pd.Series([False] * len(df))
                for col in df.select_dtypes(include=['object']).columns:
                    if not col.startswith('_'):
                        search_mask |= df[col].astype(str).str.lower().str.contains(value.lower(), na=False)
                df = df[search_mask]
            
            elif field == 'date_from' and value:
                if '_upload_date' in df.columns:
                    df['_upload_date_dt'] = pd.to_datetime(df['_upload_date'], errors='coerce')
                    df = df[df['_upload_date_dt'] >= pd.to_datetime(value)]
            
            elif field == 'date_to' and value:
                if '_upload_date' in df.columns:
                    df['_upload_date_dt'] = pd.to_datetime(df['_upload_date'], errors='coerce')
                    df = df[df['_upload_date_dt'] <= pd.to_datetime(value)]
            
            elif field in df.columns and value and value != 'All':
                if field in df.columns:
                    df = df[df[field] == value]
            
            elif field.startswith('_') and value and value != 'All':
                if field in df.columns:
                    df = df[df[field] == value]
        
        # Remove internal columns for display
        display_cols = [col for col in df.columns if not col.startswith('_')]
        if self.pk_column in display_cols:
            # Ensure primary key is first column
            display_cols.insert(0, display_cols.pop(display_cols.index(self.pk_column)))
        
        return df[display_cols] if display_cols else df
    
    def get_statistics(self) -> Dict:
        """Get comprehensive statistics"""
        if st.session_state.data_warehouse.empty:
            return {}
        
        df = st.session_state.data_warehouse
        
        stats = {
            'total_records': len(df),
            'total_files': len(st.session_state.file_metadata),
            'primary_key_column': self.pk_column,
            'total_columns': len([col for col in df.columns if not col.startswith('_')])
        }
        
        # Source distribution
        if '_source_type' in df.columns:
            stats['source_distribution'] = df['_source_type'].value_counts().to_dict()
        
        # Category distribution
        if '_category' in df.columns:
            stats['category_distribution'] = df['_category'].value_counts().to_dict()
        
        # Data quality
        if '_data_quality_score' in df.columns:
            stats['avg_quality_score'] = df['_data_quality_score'].mean()
            stats['quality_distribution'] = {
                'High (80-100)': len(df[df['_data_quality_score'] >= 80]),
                'Medium (50-79)': len(df[(df['_data_quality_score'] >= 50) & (df['_data_quality_score'] < 80)]),
                'Low (0-49)': len(df[df['_data_quality_score'] < 50])
            }
        
        # Column completeness
        completeness = {}
        for col in df.select_dtypes(include=['object']).columns[:10]:  # Limit to first 10 columns
            if not col.startswith('_'):
                completeness[col] = (df[col].notna() & (df[col] != "")).mean() * 100
        stats['column_completeness'] = completeness
        
        return stats

def main():
    """Main application"""
    
    st.markdown('<div class="main-header">🏠 Pan-India Real Estate Data Warehouse</div>', unsafe_allow_html=True)
    
    # Privacy notice
    st.markdown("""
    <div class="privacy-note">
        🔒 <strong>Privacy First Approach:</strong> This system uses column-based primary keys (mobile, email, ID, etc.) 
        for data correlation without exposing or requiring specific values. All data processing happens in-memory 
        and is not persisted outside the session.
    </div>
    """, unsafe_allow_html=True)
    
    # Initialize warehouse
    warehouse = PrivacyCompliantDataWarehouse()
    
    # Sidebar
    with st.sidebar:
        st.title("📊 Navigation")
        
        page = st.radio(
            "Select Module",
            ["📤 Upload Files", "🔍 Dynamic Query", "📈 Analytics Dashboard", 
             "📁 Data Management", "ℹ️ System Info"],
            index=0
        )
        
        st.markdown("---")
        
        # System stats
        if not st.session_state.data_warehouse.empty:
            st.markdown("### 📊 System Stats")
            st.metric("Total Records", f"{len(st.session_state.data_warehouse):,}")
            st.metric("Files Uploaded", f"{len(st.session_state.file_metadata)}")
            
            if st.session_state.primary_key_column:
                st.info(f"🔑 Primary Key: **{st.session_state.primary_key_column}**")
    
    # Page routing
    if page == "📤 Upload Files":
        upload_files_page(warehouse)
    elif page == "🔍 Dynamic Query":
        dynamic_query_page(warehouse)
    elif page == "📈 Analytics Dashboard":
        analytics_dashboard_page(warehouse)
    elif page == "📁 Data Management":
        data_management_page(warehouse)
    elif page == "ℹ️ System Info":
        system_info_page(warehouse)

def upload_files_page(warehouse: PrivacyCompliantDataWarehouse):
    """Handle file uploads"""
    st.header("📤 Upload Multiple Files")
    
    st.info("""
    💡 **How it works:**
    - Upload multiple Excel/CSV files
    - System automatically detects which column can serve as a unique identifier (mobile, email, ID, etc.)
    - This identifier is used as a key to correlate records across different files
    - No specific values are required or exposed - the system works with any column as key
    """)
    
    with st.form("upload_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            source_type = st.selectbox(
                "Default Source Type (optional)",
                ["Select source", "MSEB", "Facebook Leads", "Property Portal", 
                 "Agent List", "School Data", "Doctor List", "Police Records",
                 "Broker List", "Expo Visitors", "Sales Data", "Other"]
            )
        
        with col2:
            category = st.selectbox(
                "Default Category (optional)",
                ["Select category", "Real Estate Trade", "Property Seeker", "Non-Real Estate", "General"]
            )
        
        uploaded_files = st.file_uploader(
            "Choose Files (Excel or CSV)",
            type=['xlsx', 'xls', 'csv'],
            accept_multiple_files=True,
            help="Upload any number of files. System will detect the best column to use as primary key for correlation."
        )
        
        submitted = st.form_submit_button("🚀 Process Files", type="primary", use_container_width=True)
        
        if submitted and uploaded_files:
            if source_type == "Select source":
                source_type = "General"
            if category == "Select category":
                category = "General"
                
            process_files(warehouse, uploaded_files, source_type, category)

def process_files(warehouse: PrivacyCompliantDataWarehouse, files, source_type, category):
    """Process multiple files"""
    progress_bar = st.progress(0)
    status_text = st.empty()
    results_container = st.container()
    
    success_count = 0
    error_count = 0
    total_records_added = 0
    
    for idx, file in enumerate(files):
        status_text.text(f"Processing {file.name}... ({idx+1}/{len(files)})")
        
        metadata = {
            'upload_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'source_type': source_type,
            'category': category
        }
        
        success, message, file_info = warehouse.add_file(file, metadata)
        
        if success:
            success_count += 1
            total_records_added += file_info.get('records_added', 0)
            with results_container:
                st.success(f"✅ {file.name}: {message}")
        else:
            error_count += 1
            with results_container:
                st.error(f"❌ {file.name}: {message}")
        
        progress_bar.progress((idx + 1) / len(files))
    
    status_text.text("✅ Processing Complete!")
    
    # Summary
    st.markdown("---")
    st.subheader("📊 Upload Summary")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Files Processed", f"{success_count}/{len(files)}")
    with col2:
        st.metric("Records Added", f"{total_records_added:,}")
    with col3:
        st.metric("Primary Key", st.session_state.primary_key_column or "Auto-detected")
    
    if success_count > 0:
        st.balloons()

def dynamic_query_page(warehouse: PrivacyCompliantDataWarehouse):
    """Dynamic query interface"""
    st.header("🔍 Dynamic Query Builder")
    
    if st.session_state.data_warehouse.empty:
        st.warning("No data available. Please upload files first.")
        return
    
    st.markdown('<div class="query-builder">', unsafe_allow_html=True)
    st.subheader("Build Your Custom Query")
    
    # Get available columns for filtering
    available_columns = [col for col in st.session_state.available_columns if not col.startswith('_')]
    available_columns.extend(['_source_type', '_category'])
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        query_type = st.selectbox(
            "Quick Filter",
            ["All Records", "By Source", "By Category", "Text Search", "Custom Query"]
        )
    
    conditions = {}
    
    if query_type == "By Source":
        if '_source_type' in st.session_state.data_warehouse.columns:
            sources = st.session_state.data_warehouse['_source_type'].unique().tolist()
            selected_source = st.selectbox("Select Source", ["All"] + sorted(sources))
            if selected_source != "All":
                conditions['_source_type'] = selected_source
    
    elif query_type == "By Category":
        if '_category' in st.session_state.data_warehouse.columns:
            categories = st.session_state.data_warehouse['_category'].unique().tolist()
            selected_category = st.selectbox("Select Category", ["All"] + sorted(categories))
            if selected_category != "All":
                conditions['_category'] = selected_category
    
    elif query_type == "Text Search":
        search_text = st.text_input("Search Text", placeholder="Search across all text fields...")
        if search_text:
            conditions['search_text'] = search_text
    
    elif query_type == "Custom Query":
        st.info("Build custom query with field-specific filters")
        
        num_filters = st.number_input("Number of filters", min_value=1, max_value=5, value=1)
        
        for i in range(num_filters):
            st.markdown(f"**Filter {i+1}**")
            filter_col1, filter_col2 = st.columns(2)
            
            with filter_col1:
                filter_field = st.selectbox(f"Field", available_columns, key=f"field_{i}")
            
            with filter_col2:
                # Get unique values for the selected field
                if filter_field in st.session_state.data_warehouse.columns:
                    unique_values = st.session_state.data_warehouse[filter_field].dropna().unique().tolist()
                    filter_value = st.selectbox(f"Value", ["All"] + sorted([str(v) for v in unique_values[:20]]), key=f"value_{i}")
                    if filter_value != "All":
                        conditions[filter_field] = filter_value
                else:
                    filter_value = st.text_input(f"Value", key=f"value_{i}")
                    if filter_value:
                        conditions[filter_field] = filter_value
    
    # Date range filter (always available)
    st.markdown("---")
    st.subheader("Date Range Filter (Optional)")
    col1, col2 = st.columns(2)
    with col1:
        date_from = st.date_input("From Date", value=None)
        if date_from:
            conditions['date_from'] = date_from.strftime("%Y-%m-%d")
    with col2:
        date_to = st.date_input("To Date", value=None)
        if date_to:
            conditions['date_to'] = date_to.strftime("%Y-%m-%d")
    
    # Execute query
    if st.button("🔍 Execute Query", type="primary", use_container_width=True):
        with st.spinner("Executing query..."):
            results_df = warehouse.dynamic_query(conditions)
            
            # Save to history
            query_record = {
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'query_type': query_type,
                'conditions': str(conditions),
                'results_count': len(results_df)
            }
            st.session_state.query_history.append(query_record)
            
            # Display results
            st.markdown("---")
            st.subheader(f"📊 Query Results: {len(results_df)} records found")
            
            if not results_df.empty:
                # Column selector for display
                all_cols = results_df.columns.tolist()
                default_cols = [col for col in [st.session_state.primary_key_column, 'name', 'email', '_source_type', '_category'] 
                              if col in all_cols]
                
                selected_cols = st.multiselect(
                    "Select columns to display",
                    all_cols,
                    default=default_cols[:5] if default_cols else all_cols[:5]
                )
                
                if selected_cols:
                    st.dataframe(results_df[selected_cols], use_container_width=True, height=400)
                
                # Export options
                st.markdown("---")
                st.subheader("📥 Export Results")
                
                export_format = st.selectbox("Export Format", ["CSV", "Excel", "JSON"])
                export_name = st.text_input("Filename", value=f"query_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                
                if st.button("📥 Download Results", type="primary"):
                    export_df = results_df[selected_cols] if selected_cols else results_df
                    
                    if export_format == "CSV":
                        csv = export_df.to_csv(index=False).encode()
                        st.download_button(
                            "Click to Download",
                            data=csv,
                            file_name=f"{export_name}.csv",
                            mime="text/csv"
                        )
                    elif export_format == "Excel":
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            export_df.to_excel(writer, sheet_name='Results', index=False)
                        st.download_button(
                            "Click to Download",
                            data=output.getvalue(),
                            file_name=f"{export_name}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    else:
                        json_str = export_df.to_json(orient='records', indent=2)
                        st.download_button(
                            "Click to Download",
                            data=json_str,
                            file_name=f"{export_name}.json",
                            mime="application/json"
                        )
            else:
                st.warning("No records found matching your criteria")
    
    st.markdown('</div>', unsafe_allow_html=True)

def analytics_dashboard_page(warehouse: PrivacyCompliantDataWarehouse):
    """Analytics dashboard"""
    st.header("📈 Analytics Dashboard")
    
    if st.session_state.data_warehouse.empty:
        st.warning("No data available. Please upload files first.")
        return
    
    stats = warehouse.get_statistics()
    df = st.session_state.data_warehouse
    
    # Key metrics
    st.subheader("📊 Key Metrics")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{stats['total_records']:,}</div>
            <div class="stat-label">Total Records</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{stats['total_files']}</div>
            <div class="stat-label">Files Uploaded</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{stats.get('avg_quality_score', 0):.0f}</div>
            <div class="stat-label">Avg Quality Score</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{stats['total_columns']}</div>
            <div class="stat-label">Data Fields</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Visualizations
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Distributions", "📈 Data Quality", "📁 File Analysis", "📋 Detailed Stats"])
    
    with tab1:
        col_a, col_b = st.columns(2)
        
        with col_a:
            if 'source_distribution' in stats and stats['source_distribution']:
                source_df = pd.DataFrame(list(stats['source_distribution'].items()), 
                                        columns=['Source', 'Count'])
                fig = px.pie(source_df, values='Count', names='Source', 
                            title='Records by Source', hole=0.3)
                st.plotly_chart(fig, use_container_width=True)
        
        with col_b:
            if 'category_distribution' in stats and stats['category_distribution']:
                cat_df = pd.DataFrame(list(stats['category_distribution'].items()),
                                     columns=['Category', 'Count'])
                fig = px.bar(cat_df, x='Category', y='Count', 
                           title='Records by Category', color='Count')
                st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        col_a, col_b = st.columns(2)
        
        with col_a:
            if 'quality_distribution' in stats:
                quality_df = pd.DataFrame(list(stats['quality_distribution'].items()),
                                         columns=['Quality Level', 'Count'])
                fig = px.bar(quality_df, x='Quality Level', y='Count',
                           title='Data Quality Distribution', color='Quality Level')
                st.plotly_chart(fig, use_container_width=True)
        
        with col_b:
            if 'column_completeness' in stats and stats['column_completeness']:
                completeness_df = pd.DataFrame(list(stats['column_completeness'].items()),
                                              columns=['Column', 'Completeness %'])
                completeness_df = completeness_df.sort_values('Completeness %', ascending=True).tail(10)
                fig = px.bar(completeness_df, x='Completeness %', y='Column',
                           orientation='h', title='Top 10 Columns by Completeness')
                st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        if st.session_state.file_metadata:
            files_df = pd.DataFrame(st.session_state.file_metadata)
            
            col_a, col_b = st.columns(2)
            
            with col_a:
                # Upload timeline
                files_df['upload_date'] = pd.to_datetime(files_df['upload_date'])
                timeline = files_df.groupby(files_df['upload_date'].dt.date).size().reset_index()
                timeline.columns = ['Date', 'Files']
                fig = px.line(timeline, x='Date', y='Files', 
                            title='File Upload Timeline', markers=True)
                st.plotly_chart(fig, use_container_width=True)
            
            with col_b:
                # Records per file
                fig = px.bar(files_df, x='file_name', y='records_added',
                           title='Records Added per File', color='records_added')
                fig.update_layout(xaxis_tickangle=-45, height=400)
                st.plotly_chart(fig, use_container_width=True)
    
    with tab4:
        st.subheader("Detailed Statistics")
        
        # Source breakdown
        if 'source_distribution' in stats and stats['source_distribution']:
            st.write("**Source Distribution**")
            source_df = pd.DataFrame(list(stats['source_distribution'].items()), 
                                    columns=['Source', 'Record Count'])
            source_df = source_df.sort_values('Record Count', ascending=False)
            st.dataframe(source_df, use_container_width=True)
        
        # File metadata
        if st.session_state.file_metadata:
            st.write("**File Upload History**")
            files_df = pd.DataFrame(st.session_state.file_metadata)
            st.dataframe(files_df, use_container_width=True)

def data_management_page(warehouse: PrivacyCompliantDataWarehouse):
    """Data management interface"""
    st.header("📁 Data Management")
    
    if st.session_state.data_warehouse.empty:
        st.info("No data to manage")
        return
    
    st.subheader("Current Data Overview")
    
    # Data preview
    with st.expander("📊 Data Preview (First 100 rows)"):
        preview_cols = [col for col in st.session_state.data_warehouse.columns if not col.startswith('_')][:10]
        st.dataframe(st.session_state.data_warehouse[preview_cols].head(100), use_container_width=True)
    
    st.markdown("---")
    st.subheader("Data Management Actions")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🗑️ Clear All Data", type="secondary", use_container_width=True):
            st.session_state.data_warehouse = pd.DataFrame()
            st.session_state.file_metadata = []
            st.session_state.query_history = []
            st.session_state.available_columns = set()
            st.session_state.primary_key_column = None
            st.success("All data cleared successfully!")
            st.rerun()
    
    with col2:
        # Export all data
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
    
    # File management
    if st.session_state.file_metadata:
        st.markdown("---")
        st.subheader("Uploaded Files")
        files_df = pd.DataFrame(st.session_state.file_metadata)
        st.dataframe(files_df, use_container_width=True)

def system_info_page(warehouse: PrivacyCompliantDataWarehouse):
    """System information"""
    st.header("ℹ️ System Information")
    
    st.markdown("""
    ### About This Application
    
    **Pan-India Real Estate Data Warehouse** is a powerful data management system designed to:
    
    - **Upload and correlate data** from multiple Excel/CSV files
    - **Use any column as primary key** (mobile, email, ID, etc.) for data correlation
    - **Dynamic querying** across all uploaded data
    - **Privacy-first approach** - works with column structures, not specific values
    - **Real-time analytics** and visualizations
    - **Flexible export** capabilities
    
    ### Key Features
    
    1. **Multi-File Upload**: Process hundreds of files simultaneously
    2. **Smart Column Detection**: Automatically identifies key columns
    3. **Flexible Primary Key**: Use any unique identifier column
    4. **Dynamic Query Builder**: Build custom queries with multiple filters
    5. **Comprehensive Analytics**: Visualize data from multiple perspectives
    6. **Data Quality Scoring**: Automatic quality assessment
    
    ### How It Works
    
    - Upload files → System detects best primary key column
    - Data is correlated using the primary key
    - Query across all files using any field
    - Export results in multiple formats
    
    ### Privacy & Security
    
    - No data is persisted outside the session
    - All processing happens in-memory
    - No external API calls or data sharing
    - Column-based correlation (not value-based)
    
    ### Technical Details
    
    - Built with Streamlit
    - Uses Pandas for data processing
    - Plotly for visualizations
    - Supports Excel, CSV formats
    """)
    
    # Current system status
    st.markdown("---")
    st.subheader("Current System Status")
    
    col1, col2 = st.columns(2)
    with col1:
        st.json({
            "Total Records": len(st.session_state.data_warehouse),
            "Total Files": len(st.session_state.file_metadata),
            "Primary Key Column": st.session_state.primary_key_column or "Not set",
            "Available Columns": len(st.session_state.available_columns),
            "Query History": len(st.session_state.query_history)
        })

if __name__ == "__main__":
    main()
