import streamlit as st
import pandas as pd
from datetime import datetime
import os
from pathlib import Path
import asyncio

# Import utilities
from utils.supabase_client import SupabaseClient
from utils.data_ingestion import DataIngestion
from utils.deduplication import Deduplication
from utils.claude_api import ClaudeAPI

# Page configuration
st.set_page_config(
    page_title="Real Estate Data Warehouse",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'supabase' not in st.session_state:
    st.session_state.supabase = SupabaseClient()
if 'ingestion' not in st.session_state:
    st.session_state.ingestion = DataIngestion()
if 'dedup' not in st.session_state:
    st.session_state.dedup = Deduplication(st.session_state.supabase)
if 'claude' not in st.session_state:
    st.session_state.claude = ClaudeAPI()

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1E3A8A;
        text-align: center;
        padding: 1rem;
    }
    .stat-card {
        background-color: #F3F4F6;
        padding: 1rem;
        border-radius: 0.5rem;
        text-align: center;
    }
    .stat-number {
        font-size: 2rem;
        font-weight: bold;
        color: #1E3A8A;
    }
    .sidebar .sidebar-content {
        background-color: #F9FAFB;
    }
</style>
""", unsafe_allow_html=True)

# Title
st.markdown('<div class="main-header">🏠 Pan-India Real Estate Data Warehouse</div>', unsafe_allow_html=True)

# Sidebar for navigation
with st.sidebar:
    st.image("https://img.icons8.com/color/96/real-estate.png", width=80)
    st.title("Navigation")
    
    page = st.radio(
        "Go to",
        ["Dashboard", "Upload Data", "Search & Export", "Settings"]
    )
    
    st.markdown("---")
    st.markdown("### System Status")
    st.markdown("✅ Database Connected" if st.session_state.supabase.client else "❌ Database Disconnected")
    st.markdown(f"📁 Uploads Ready")

# Main content based on navigation
if page == "Dashboard":
    st.header("📊 Dashboard Overview")
    
    # Get stats
    stats = st.session_state.supabase.get_dashboard_stats()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown('<div class="stat-card">', unsafe_allow_html=True)
        st.markdown('<div class="stat-number">{:,}</div>'.format(stats.get("total_records", 0)), unsafe_allow_html=True)
        st.markdown("Total Records")
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        st.markdown('<div class="stat-card">', unsafe_allow_html=True)
        st.markdown('<div class="stat-number">{:,}</div>'.format(stats.get("unique_records", 0)), unsafe_allow_html=True)
        st.markdown("Unique Records")
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col3:
        st.markdown('<div class="stat-card">', unsafe_allow_html=True)
        st.markdown('<div class="stat-number">{:,}</div>'.format(
            stats.get("total_records", 0) - stats.get("unique_records", 0)
        ), unsafe_allow_html=True)
        st.markdown("Duplicates Flagged")
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col4:
        st.markdown('<div class="stat-card">', unsafe_allow_html=True)
        st.markdown('<div class="stat-number">{}</div>'.format(
            len(st.session_state.supabase.client.table("real_estate_records").select("source_type", count="exact", distinct=True).execute().data) if st.session_state.supabase.client else 0
        ), unsafe_allow_html=True)
        st.markdown("Data Sources")
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Category Breakdown
    st.subheader("📈 Data Category Breakdown")
    categories = stats.get("categories", {})
    if categories:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("🏢 Real Estate Trade", f"{categories.get('Real Estate Trade', 0):,}")
        with col2:
            st.metric("🔍 Property Seeker", f"{categories.get('Property Seeker', 0):,}")
        with col3:
            st.metric("📄 Non-Real Estate", f"{categories.get('Non-Real Estate', 0):,}")
    
    # Recent uploads
    st.subheader("📁 Recent Uploads")
    recent = st.session_state.supabase.search_records("", limit=10)
    if recent:
        df_recent = pd.DataFrame(recent)[["name", "mobile", "city", "category", "date_added"]]
        st.dataframe(df_recent, use_container_width=True)

elif page == "Upload Data":
    st.header("📤 Upload New Data File")
    
    # Intake Questions Form
    with st.form("intake_form"):
        st.subheader("File Information")
        
        col1, col2 = st.columns(2)
        with col1:
            source = st.selectbox(
                "1. Source of Data *",
                ["MSEB", "Facebook leads", "Property portal", "Agent list", 
                 "School", "Doctor", "Police", "Broker list", "Expo visitors", "Other"]
            )
            
            date_sourced = st.date_input("2. Date Sourced", datetime.now())
            
            category = st.selectbox(
                "3. Data Category",
                ["Let system decide", "Real Estate Trade", "Property Seeker", "Non-Real Estate"]
            )
        
        with col2:
            geography = st.text_input("4. Geographic Coverage", placeholder="e.g., Baner, Kharadi, All Pune")
            
            quality_notes = st.selectbox(
                "5. Data Quality Notes",
                ["None", "Expected duplicates", "Verified leads only", "Historical data", 
                 "Missing addresses", "Blacklisted numbers"]
            )
            
            file_name = st.text_input("6. File Name/Description", placeholder="Custom name for reference")
        
        uploaded_file = st.file_uploader("Upload Excel File", type=['xlsx', 'xls'])
        
        submitted = st.form_submit_button("Process File", type="primary")
        
        if
