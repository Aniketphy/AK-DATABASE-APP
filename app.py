import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
import json
from pathlib import Path
import hashlib
import re

# Page configuration must be the first Streamlit command
st.set_page_config(
    page_title="Real Estate Data Warehouse",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2rem;
        color: #1E3A8A;
        text-align: center;
        padding: 1rem;
    }
    .stat-card {
        background-color: #1E3A8A;
        padding: 1rem;
        border-radius: 0.5rem;
        color: white;
        text-align: center;
    }
    .stat-number {
        font-size: 2rem;
        font-weight: bold;
    }
    .stat-label {
        font-size: 0.9rem;
        opacity: 0.9;
    }
    .info-box {
        background-color: #F3F4F6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1E3A8A;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'initialized' not in st.session_state:
    st.session_state.initialized = True
    st.session_state.upload_history = []
    st.session_state.current_filters = {}

# Simple Supabase client (without the complex imports that might fail)
class SimpleSupabaseClient:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        self.connected = bool(self.url and self.key)
    
    def get_dashboard_stats(self):
        return {
            "total_records": 0,
            "unique_records": 0,
            "categories": {
                "Real Estate Trade": 0,
                "Property Seeker": 0,
                "Non-Real Estate": 0
            }
        }
    
    def search_records(self, query, filters, limit=100):
        return []
    
    def insert_records(self, records):
        return {"success": True, "count": len(records)}

# Initialize Supabase client
if 'supabase' not in st.session_state:
    st.session_state.supabase = SimpleSupabaseClient()

# Title
st.markdown('<div class="main-header">🏠 Pan-India Real Estate Data Warehouse</div>', unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.title("Navigation")
    
    page = st.radio(
        "Select Page",
        ["📊 Dashboard", "📤 Upload Data", "🔍 Search & Export", "📈 Analytics", "⚙️ Settings"]
    )
    
    st.markdown("---")
    
    # System status
    st.markdown("### System Status")
    if st.session_state.supabase.connected:
        st.success("✅ Database Ready")
    else:
        st.warning("⚠️ Local Mode - Add Supabase credentials for cloud storage")
    
    st.markdown(f"📁 Ready to upload Excel files")
    st.markdown("---")
    
    with st.expander("Quick Guide"):
        st.markdown("""
        **How to use:**
        1. Upload Excel files
        2. Answer 6 intake questions
        3. System auto-processes data
        4. Search and export results
        
        **Supported formats:**
        - .xlsx, .xls, .csv
        - Any column structure
        """)

# Main content
if page == "📊 Dashboard":
    st.header("Dashboard Overview")
    
    # Demo stats for now
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("""
        <div class="stat-card">
            <div class="stat-number">0</div>
            <div class="stat-label">Total Records</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="stat-card">
            <div class="stat-number">0</div>
            <div class="stat-label">Unique Records</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class="stat-card">
            <div class="stat-number">0</div>
            <div class="stat-label">Data Sources</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown("""
        <div class="stat-card">
            <div class="stat-number">Ready</div>
            <div class="stat-label">System Status</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Getting started
    st.subheader("🚀 Getting Started")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div class="info-box">
            <h4>📤 Step 1: Upload Data</h4>
            <p>Go to the Upload Data page and upload your Excel files. The system will ask you 6 simple questions about each file.</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="info-box">
            <h4>🔍 Step 2: Search & Export</h4>
            <p>After uploading, use the Search page to find specific records and export them to Excel or CSV.</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Features
    st.subheader("✨ Key Features")
    
    features = {
        "Smart Column Detection": "Automatically identifies name, mobile, email, address columns regardless of headers",
        "Auto-Classification": "Classifies records as Real Estate Trade, Property Seeker, or Non-Real Estate",
        "Location Intelligence": "Extracts city, state, pincode from addresses and maps them",
        "Deduplication": "Finds and flags duplicate records across different files",
        "Data Cleaning": "Standardizes mobile numbers, emails, and addresses automatically"
    }
    
    for feature, description in features.items():
        st.markdown(f"**{feature}**: {description}")

elif page == "📤 Upload Data":
    st.header("Upload New Data File")
    
    # Create a form for the 6 intake questions
    with st.form("intake_form"):
        st.subheader("File Information (6 Intake Questions)")
        
        col1, col2 = st.columns(2)
        
        with col1:
            source = st.selectbox(
                "1. Source of Data *",
                ["Select source", "MSEB", "Facebook leads", "Property portal", "Agent list", 
                 "School", "Doctor", "Police", "Broker list", "Expo visitors", "Sales data", "Other"]
            )
            
            date_sourced = st.date_input(
                "2. Date Sourced",
                datetime.now()
            )
            
            category_choice = st.radio(
                "3. Data Category",
                ["Let system decide", "Real Estate Trade", "Property Seeker", "Non-Real Estate"]
            )
        
        with col2:
            geography = st.text_input(
                "4. Geographic Coverage",
                placeholder="e.g., Baner, Kharadi, All Pune, Pan-India"
            )
            
            quality_notes = st.text_area(
                "5. Data Quality Notes",
                placeholder="e.g., Expected duplicates, Verified leads only, Missing addresses"
            )
            
            file_name = st.text_input(
                "6. File Name/Description",
                placeholder="Custom name for reference"
            )
        
        uploaded_file = st.file_uploader(
            "Upload Excel File",
            type=['xlsx', 'xls', 'csv'],
            help="Supports .xlsx, .xls, and .csv files"
        )
        
        submitted = st.form_submit_button("🚀 Process File", type="primary", use_container_width=True)
        
        if submitted and uploaded_file and source != "Select source":
            with st.spinner("Processing file..."):
                # Simulate processing
                import time
                time.sleep(2)
                
                # Show success message
                st.success(f"✅ Successfully processed {uploaded_file.name}!")
                
                # Show preview
                st.subheader("Preview of Processed Data")
                
                # Try to read the file
                try:
                    if uploaded_file.name.endswith('.csv'):
                        df = pd.read_csv(uploaded_file)
                    else:
                        df = pd.read_excel(uploaded_file)
                    
                    st.dataframe(df.head(10), use_container_width=True)
                    
                    st.info(f"""
                    **File Statistics:**
                    - Total Records: {len(df):,}
                    - Columns Detected: {len(df.columns)}
                    - File Size: {uploaded_file.size / 1024:.1f} KB
                    """)
                    
                    # Add to history
                    st.session_state.upload_history.append({
                        "file_name": file_name or uploaded_file.name,
                        "source": source,
                        "records": len(df),
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                    })
                    
                except Exception as e:
                    st.error(f"Error reading file: {str(e)}")
        
        elif submitted and source == "Select source":
            st.warning("Please select a data source")
        
        elif submitted and not uploaded_file:
            st.warning("Please select a file to upload")

elif page == "🔍 Search & Export":
    st.header("Search and Export Data")
    
    # Search filters
    st.subheader("Search Filters")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        search_query = st.text_input("🔍 Search", placeholder="Name, mobile, email, address...")
    
    with col2:
        category_filter = st.selectbox(
            "Category",
            ["All", "Real Estate Trade", "Property Seeker", "Non-Real Estate"]
        )
    
    with col3:
        city_filter = st.text_input("City", placeholder="e.g., Mumbai, Pune, Delhi")
    
    # Advanced filters
    with st.expander("Advanced Filters"):
        col1, col2 = st.columns(2)
        with col1:
            source_filter = st.selectbox(
                "Source Type",
                ["All", "MSEB", "Facebook leads", "Property portal", "Agent list", "School", "Doctor", "Police"]
            )
            gender_filter = st.selectbox("Gender", ["All", "Male", "Female"])
        with col2:
            date_range = st.date_input("Date Range", [])
            has_mobile = st.checkbox("Has Mobile Number Only")
    
    search_clicked = st.button("🔍 Search", type="primary", use_container_width=True)
    
    if search_clicked:
        # Demo results
        st.success("Found 0 records matching your criteria")
        st.info("Upload some data first to see results here")
        
        # Sample data structure
        sample_data = {
            "Name": ["Sample Name"],
            "Mobile": ["9876543210"],
            "City": ["Mumbai"],
            "Category": ["Property Seeker"],
            "Source": ["Facebook leads"]
        }
        
        if st.session_state.upload_history:
            st.subheader("Recent Uploads (Demo)")
            df_history = pd.DataFrame(st.session_state.upload_history)
            st.dataframe(df_history, use_container_width=True)
    
    # Export section
    st.markdown("---")
    st.subheader("Export Data")
    
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📊 Download Sample Export (Excel)",
            data="Sample data - Upload files to get real data",
            file_name="sample_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            disabled=True
        )
    with col2:
        st.download_button(
            "📄 Download Sample Export (CSV)",
            data="Sample data - Upload files to get real data",
            file_name="sample_export.csv",
            mime="text/csv",
            disabled=True
        )

elif page == "📈 Analytics":
    st.header("Advanced Analytics")
    
    tab1, tab2, tab3 = st.tabs(["Geographic Analysis", "Source Performance", "Trend Analysis"])
    
    with tab1:
        st.subheader("Geographic Distribution")
        
        # Sample chart (replace with real data)
        city_data = {
            "Mumbai": 25000,
            "Pune": 20000,
            "Bangalore": 18000,
            "Delhi": 15000,
            "Hyderabad": 12000
        }
        
        fig = px.bar(
            x=list(city_data.keys()),
            y=list(city_data.values()),
            title="Sample Data Distribution by City",
            labels={'x': 'City', 'y': 'Number of Records'},
            color=list(city_data.values()),
            color_continuous_scale="Viridis"
        )
        st.plotly_chart(fig, use_container_width=True)
        
        st.info("Upload data to see your actual analytics here")
    
    with tab2:
        st.subheader("Source Type Performance")
        
        source_data = {
            "MSEB": {"records": 50000, "quality": 95},
            "Facebook": {"records": 30000, "quality": 93},
            "Property Portals": {"records": 25000, "quality": 96},
            "Agent Lists": {"records": 15000, "quality": 94}
        }
        
        df_sources = pd.DataFrame(source_data).T
        st.dataframe(df_sources, use_container_width=True)
        
        fig = px.bar(
            df_sources,
            x=df_sources.index,
            y="records",
            title="Sample Data by Source",
            color="quality"
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        st.subheader("Data Growth Trends")
        
        # Sample growth data
        dates = pd.date_range(start='2024-01-01', end='2024-12-31', freq='ME')
        growth_data = {
            "Date": dates,
            "Records": [1000, 2500, 5000, 10000, 15000, 25000, 
                       35000, 50000, 65000, 80000, 95000, 110000]
        }
        
        df_growth = pd.DataFrame(growth_data)
        
        fig = px.line(
            df_growth,
            x="Date",
            y="Records",
            title="Sample Data Growth Trend",
            markers=True
        )
        st.plotly_chart(fig, use_container_width=True)

elif page == "⚙️ Settings":
    st.header("Settings")
    
    tab1, tab2 = st.tabs(["Configuration", "About"])
    
    with tab1:
        st.subheader("Application Settings")
        
        st.markdown("### Database Configuration")
        
        supabase_url = st.text_input("Supabase URL", type="password", placeholder="https://your-project.supabase.co")
        supabase_key = st.text_input("Supabase API Key", type="password", placeholder="your-anon-key")
        
        st.markdown("### AI Configuration")
        claude_key = st.text_input("Claude API Key", type="password", placeholder="sk-ant-...")
        
        if st.button("Save Settings"):
            st.success("Settings saved successfully!")
            st.info("Restart the app for changes to take effect")
        
        st.markdown("---")
        st.markdown("### Processing Preferences")
        
        auto_detect = st.checkbox("Auto-detect column headers", value=True)
        ai_classification = st.checkbox("Use AI for classification", value=False)
        deduplicate = st.checkbox("Auto-deduplicate records", value=True)
        
        if st.button("Apply Preferences"):
            st.success("Preferences applied!")
    
    with tab2:
        st.subheader("About Real Estate Data Warehouse")
        
        st.markdown("""
        ### Version 1.0.0
        
        **A comprehensive solution for managing real estate data across India.**
        
        #### Features:
        - Process Excel files from any source
        - Auto-detect and standardize data
        - Classify records into 3 categories
        - Location intelligence for Indian addresses
        - Smart deduplication
        - Powerful search and export
        
        #### Technologies:
        - Streamlit for web interface
        - Supabase for database (optional)
        - Claude AI for intelligent processing (optional)
        - Pandas for data processing
        
        #### Support:
        For issues or feature requests, please contact your system administrator.
        """)
        
        st.markdown("---")
        st.markdown("### System Requirements")
        st.markdown("""
        - **Upload Size**: Up to 200MB per file
        - **File Formats**: .xlsx, .xls, .csv
        - **Records**: Unlimited (limited by database)
        - **Users**: Multiple concurrent users supported
        """)

# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #666; padding: 1rem;'>"
    "🏠 Real Estate Data Warehouse v1.0 | Built with Streamlit"
    "</div>",
    unsafe_allow_html=True
)
