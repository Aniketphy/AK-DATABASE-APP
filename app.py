import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
import json
from pathlib import Path
import hashlib

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

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1E3A8A;
        text-align: center;
        padding: 1rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .stat-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 1rem;
        color: white;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .stat-number {
        font-size: 2.5rem;
        font-weight: bold;
    }
    .stat-label {
        font-size: 0.9rem;
        opacity: 0.9;
        margin-top: 0.5rem;
    }
    .info-box {
        background-color: #F3F4F6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1E3A8A;
        margin: 1rem 0;
    }
    .success-badge {
        background-color: #10B981;
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        display: inline-block;
    }
    .warning-badge {
        background-color: #F59E0B;
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        display: inline-block;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'initialized' not in st.session_state:
    st.session_state.initialized = True
    st.session_state.supabase = SupabaseClient()
    st.session_state.ingestion = DataIngestion()
    st.session_state.dedup = Deduplication(st.session_state.supabase)
    st.session_state.claude = ClaudeAPI()
    st.session_state.upload_history = []
    st.session_state.current_filters = {}

# Title
st.markdown('<div class="main-header">🏠 Pan-India Real Estate Data Warehouse</div>', unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.image("https://img.icons8.com/color/96/real-estate.png", width=80)
    st.title("Navigation")
    
    page = st.radio(
        "Select Page",
        ["📊 Dashboard", "📤 Upload Data", "🔍 Search & Export", "📈 Analytics", "⚙️ Settings"],
        format_func=lambda x: x.split(" ")[1] if " " in x else x
    )
    
    st.markdown("---")
    
    # System status
    st.markdown("### System Status")
    try:
        if st.session_state.supabase.client:
            st.markdown("✅ Database: Connected")
            # Test query
            test = st.session_state.supabase.client.table("real_estate_records").select("count", count="exact").limit(1).execute()
            st.markdown("✅ API: Active")
        else:
            st.markdown("❌ Database: Disconnected")
    except:
        st.markdown("❌ Database: Error")
    
    st.markdown(f"📁 Uploads Ready: {len(st.session_state.upload_history)} files")
    
    # Claude API status
    if st.session_state.claude.client:
        st.markdown("🤖 Claude AI: Ready")
    else:
        st.markdown("⚠️ Claude AI: Not configured")
    
    st.markdown("---")
    st.markdown("### Quick Tips")
    st.info("💡 Upload Excel files with any column structure\n\n🔍 Search by name, mobile, or location\n\n📊 Export filtered data to CSV/Excel")

# Main content
if page == "📊 Dashboard":
    st.header("Dashboard Overview")
    
    # Get stats
    try:
        stats = st.session_state.supabase.get_dashboard_stats()
        
        # Top metrics row
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-number">{stats.get('total_records', 0):,}</div>
                <div class="stat-label">Total Records</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            unique_records = stats.get('unique_records', 0)
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-number">{unique_records:,}</div>
                <div class="stat-label">Unique Records</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            duplicates = stats.get('total_records', 0) - unique_records
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-number">{duplicates:,}</div>
                <div class="stat-label">Duplicates Flagged</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            categories = stats.get('categories', {})
            trade_count = categories.get('Real Estate Trade', 0)
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-number">{trade_count:,}</div>
                <div class="stat-label">Trade Professionals</div>
            </div>
            """, unsafe_allow_html=True)
        
        # Category breakdown chart
        st.subheader("Data Category Distribution")
        if categories:
            col1, col2 = st.columns([2, 1])
            with col1:
                fig = px.pie(
                    values=list(categories.values()),
                    names=list(categories.keys()),
                    title="Records by Category",
                    color_discrete_sequence=px.colors.qualitative.Set3
                )
                fig.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.markdown('<div class="info-box">', unsafe_allow_html=True)
                st.markdown("### Category Insights")
                st.markdown(f"""
                - **🏢 Real Estate Trade**: {categories.get('Real Estate Trade', 0):,} records
                  *Brokers, agents, developers*
                
                - **🔍 Property Seeker**: {categories.get('Property Seeker', 0):,} records
                  *Active buyers/renters*
                
                - **📄 Non-Real Estate**: {categories.get('Non-Real Estate', 0):,} records
                  *General population data*
                """)
                st.markdown('</div>', unsafe_allow_html=True)
        
        # Geographic distribution
        st.subheader("Geographic Coverage")
        
        # Get city distribution (simplified - you can enhance this with actual query)
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### Top Cities")
            # This would come from actual database query
            cities_data = {
                "Mumbai": 150000,
                "Pune": 125000,
                "Bangalore": 100000,
                "Delhi": 90000,
                "Hyderabad": 75000
            }
            fig = px.bar(
                x=list(cities_data.keys()),
                y=list(cities_data.values()),
                title="Records by City",
                labels={'x': 'City', 'y': 'Number of Records'}
            )
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.markdown("#### Source Distribution")
            sources_data = {
                "MSEB": 200000,
                "Facebook Leads": 150000,
                "Property Portals": 100000,
                "Agent Lists": 75000,
                "Other": 50000
            }
            fig = px.pie(
                values=list(sources_data.values()),
                names=list(sources_data.keys()),
                title="Records by Source"
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Recent activity
        st.subheader("Recent Upload Activity")
        recent_files = st.session_state.upload_history[-5:] if st.session_state.upload_history else []
        if recent_files:
            for file_info in reversed(recent_files):
                st.markdown(f"""
                <div class="info-box">
                    <strong>📄 {file_info.get('file_name', 'Unknown')}</strong><br>
                    Source: {file_info.get('source', 'N/A')} | 
                    Records: {file_info.get('records', 0):,} | 
                    Date: {file_info.get('date', 'N/A')}
                    <span class="success-badge">Processed</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No files uploaded yet. Go to Upload Data to get started.")
            
    except Exception as e:
        st.error(f"Error loading dashboard: {str(e)}")
        st.info("Make sure your Supabase database is set up correctly with the real_estate_records table.")

elif page == "📤 Upload Data":
    st.header("Upload New Data File")
    
    with st.form("intake_form"):
        st.subheader("File Information (The 6 Intake Questions)")
        
        col1, col2 = st.columns(2)
        
        with col1:
            source = st.selectbox(
                "1. Source of Data *",
                ["MSEB", "Facebook leads", "Property portal", "Agent list", 
                 "School", "Doctor", "Police", "Broker list", "Expo visitors", "Sales data", "Other"],
                help="Where did this data come from?"
            )
            
            date_sourced = st.date_input(
                "2. Date Sourced",
                datetime.now(),
                help="When was this data collected?"
            )
            
            category = st.radio(
                "3. Data Category",
                ["Let system decide (recommended)", "Real Estate Trade", "Property Seeker", "Non-Real Estate"],
                help="Choose category or let AI decide"
            )
        
        with col2:
            geography = st.text_input(
                "4. Geographic Coverage",
                placeholder="e.g., Baner, Kharadi, All Pune, Pan-India",
                help="Which areas does this data cover?"
            )
            
            quality_notes = st.multiselect(
                "5. Data Quality Notes",
                ["Expected duplicates", "Verified leads only", "Historical data", 
                 "Missing addresses", "Blacklisted numbers", "Fresh data", "Outdated"],
                help="Select any known quality issues"
            )
            
            file_name = st.text_input(
                "6. File Name/Description",
                placeholder="Custom name for reference",
                help="Give this file a descriptive name"
            )
        
        uploaded_file = st.file_uploader(
            "Upload Excel File",
            type=['xlsx', 'xls', 'csv'],
            help="Supports .xlsx, .xls, and .csv files"
        )
        
        use_ai = st.checkbox(
            "Use Claude AI for enhanced classification",
            value=True,
            help="AI helps with ambiguous records and location extraction"
        )
        
        submitted = st.form_submit_button("🚀 Process File", type="primary", use_container_width=True)
        
        if submitted and uploaded_file:
            with st.spinner("Processing file..."):
                # Save uploaded file temporarily
                temp_path = Path(f"temp/{uploaded_file.name}")
                temp_path.parent.mkdir(exist_ok=True)
                temp_path.write_bytes(uploaded_file.getvalue())
                
                # Prepare intake data
                intake_data = {
                    "source": source,
                    "date_sourced": date_sourced,
                    "category": category if category != "Let system decide (recommended)" else None,
                    "geography": geography,
                    "quality_notes": ", ".join(quality_notes),
                    "file_name": file_name or uploaded_file.name,
                    "use_ai": use_ai
                }
                
                # Process the file
                records, stats = st.session_state.ingestion.process_file(str(temp_path), intake_data)
                
                if stats["success"]:
                    # Check for duplicates
                    records = st.session_state.dedup.find_duplicates(records)
                    
                    # Insert into database
                    result = st.session_state.supabase.insert_records(records)
                    
                    if result["success"]:
                        st.success(f"✅ Successfully processed {stats['processed']:,} records!")
                        
                        # Add to history
                        st.session_state.upload_history.append({
                            "file_name": file_name or uploaded_file.name,
                            "source": source,
                            "records": stats["processed"],
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                        })
                        
                        # Show preview
                        st.subheader("Preview of Processed Data")
                        preview_df = pd.DataFrame(records[:10])
                        preview_cols = ["name", "mobile", "city", "category", "source_type"]
                        available_cols = [col for col in preview_cols if col in preview_df.columns]
                        st.dataframe(preview_df[available_cols], use_container_width=True)
                        
                        # Statistics
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Total Records", f"{stats['processed']:,}")
                        with col2:
                            duplicates_found = sum(1 for r in records if r.get("is_duplicate"))
                            st.metric("Duplicates Found", f"{duplicates_found:,}")
                        with col3:
                            unique_cities = len(set(r.get("city") for r in records if r.get("city")))
                            st.metric("Unique Cities", unique_cities)
                    else:
                        st.error(f"Database error: {result.get('error', 'Unknown error')}")
                else:
                    st.error(f"Processing error: {stats.get('error', 'Unknown error')}")
                
                # Cleanup
                temp_path.unlink()
        
        elif submitted and not uploaded_file:
            st.warning("Please select a file to upload")

elif page == "🔍 Search & Export":
    st.header("Search and Export Data")
    
    # Search filters
    st.subheader("Search Filters")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        search_query = st.text_input("🔍 Search", placeholder="Name, mobile, email, address, pincode...")
    
    with col2:
        category_filter = st.selectbox(
            "Category",
            ["All", "Real Estate Trade", "Property Seeker", "Non-Real Estate"]
        )
    
    with col3:
        city_filter = st.text_input("City", placeholder="e.g., Mumbai, Pune, Delhi")
    
    col4, col5, col6 = st.columns(3)
    
    with col4:
        source_filter = st.selectbox(
            "Source Type",
            ["All", "MSEB", "Facebook leads", "Property portal", "Agent list", "School", "Doctor", "Police"]
        )
    
    with col5:
        date_from = st.date_input("Date From", datetime.now() - timedelta(days=30))
    
    with col6:
        date_to = st.date_input("Date To", datetime.now())
    
    # Advanced filters expander
    with st.expander("Advanced Filters"):
        col1, col2 = st.columns(2)
        with col1:
            gender_filter = st.selectbox("Gender", ["All", "Male", "Female"])
            age_filter = st.selectbox("Age Group", ["All", "Under 18", "18-29", "30-44", "45-59", "60+"])
        with col2:
            zone_filter = st.text_input("Zone/Area", placeholder="e.g., Baner, Kharadi")
            has_mobile = st.checkbox("Has Mobile Number Only", value=False)
    
    search_clicked = st.button("🔍 Search", type="primary", use_container_width=True)
    
    if search_clicked:
        with st.spinner("Searching..."):
            # Build filters
            filters = {}
            if category_filter != "All":
                filters["category"] = category_filter
            if city_filter:
                filters["city"] = city_filter
            if source_filter != "All":
                filters["source_type"] = source_filter
            if gender_filter != "All":
                filters["gender"] = gender_filter
            if age_filter != "All":
                filters["age_group"] = age_filter
            
            # Search
            results = st.session_state.supabase.search_records(search_query, filters, limit=1000)
            
            if results:
                st.success(f"Found {len(results)} records")
                
                # Display results
                df_results = pd.DataFrame(results)
                
                # Select columns to display
                display_cols = ["name", "mobile", "email", "city", "category", "source_type", "date_added"]
                available_cols = [col for col in display_cols if col in df_results.columns]
                
                st.dataframe(
                    df_results[available_cols],
                    use_container_width=True,
                    height=400
                )
                
                # Export options
                st.subheader("Export Data")
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button("📊 Export to Excel", use_container_width=True):
                        excel_file = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                        df_results.to_excel(excel_file, index=False)
                        with open(excel_file, "rb") as f:
                            st.download_button(
                                "Download Excel",
                                f,
                                file_name=excel_file,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                
                with col2:
                    if st.button("📄 Export to CSV", use_container_width=True):
                        csv_file = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                        csv_data = df_results.to_csv(index=False)
                        st.download_button(
                            "Download CSV",
                            csv_data,
                            file_name=csv_file,
                            mime="text/csv"
                        )
            else:
                st.info("No records found matching your search criteria")

elif page == "📈 Analytics":
    st.header("Advanced Analytics")
    
    tab1, tab2, tab3 = st.tabs(["Geographic Analysis", "Source Performance", "Trend Analysis"])
    
    with tab1:
        st.subheader("Geographic Distribution")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # City-wise distribution
            st.markdown("#### Top Cities by Records")
            # This would come from actual query
            city_data = {
                "Mumbai": 250000,
                "Pune": 200000,
                "Bangalore": 180000,
                "Delhi": 150000,
                "Hyderabad": 120000,
                "Chennai": 100000,
                "Kolkata": 80000,
                "Ahmedabad": 70000
            }
            fig = px.bar(
                x=list(city_data.keys()),
                y=list(city_data.values()),
                title="Records per City",
                color=list(city_data.values()),
                color_continuous_scale="Viridis"
            )
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.markdown("#### Regional Breakdown")
            region_data = {
                "West": 450000,
                "South": 400000,
                "North": 350000,
                "East": 150000,
                "Central": 100000
            }
            fig = px.pie(
                values=list(region_data.values()),
                names=list(region_data.keys()),
                title="Records by Region"
            )
            st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        st.subheader("Source Type Performance")
        
        # Source performance metrics
        source_data = {
            "MSEB": {"records": 500000, "unique": 450000, "quality": 0.95},
            "Facebook Leads": {"records": 300000, "unique": 280000, "quality": 0.93},
            "Property Portals": {"records": 250000, "unique": 240000, "quality": 0.96},
            "Agent Lists": {"records": 150000, "unique": 140000, "quality": 0.94},
            "Expo Visitors": {"records": 50000, "unique": 48000, "quality": 0.97}
        }
        
        df_sources = pd.DataFrame(source_data).T
        df_sources.columns = ["Total Records", "Unique Records", "Quality Score"]
        
        st.dataframe(df_sources, use_container_width=True)
        
        # Source contribution chart
        fig = px.bar(
            df_sources,
            x=df_sources.index,
            y="Total Records",
            title="Records by Source Type",
            color="Quality Score",
            color_continuous_scale="RdYlGn"
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        st.subheader("Data Growth Trends")
        
        # Simulated growth data (replace with actual time-series data)
        dates = pd.date_range(start='2024-01-01', end='2024-12-31', freq='ME')
        growth_data = {
            "Date": dates,
            "Records Added": [50000, 75000, 100000, 125000, 150000, 175000, 
                            200000, 225000, 250000, 275000, 300000, 350000]
        }
        
        df_growth = pd.DataFrame(growth_data)
        
        fig = px.line(
            df_growth,
            x="Date",
            y="Records Added",
            title="Monthly Data Addition Trend",
            markers=True
        )
        fig.update_layout(
            xaxis_title="Month",
            yaxis_title="Records Added",
            hovermode='x unified'
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Cumulative growth
        df_growth["Cumulative Total"] = df_growth["Records Added"].cumsum()
        
        fig2 = px.area(
            df_growth,
            x="Date",
            y="Cumulative Total",
            title="Cumulative Data Growth",
            fill='tozeroy'
        )
        fig2.update_layout(
            xaxis_title="Month",
            yaxis_title="Total Records in Database"
        )
        st.plotly_chart(fig2, use_container_width=True)

elif page == "⚙️ Settings":
    st.header("Settings")
    
    tab1, tab2, tab3 = st.tabs(["Database", "AI Settings", "System"])
    
    with tab1:
        st.subheader("Database Configuration")
        
        # Database connection test
        if st.button("Test Database Connection"):
            try:
                test = st.session_state.supabase.client.table("real_estate_records").select("count", count="exact").limit(1).execute()
                st.success("✅ Database connection successful!")
            except Exception as e:
                st.error(f"❌ Database connection failed: {str(e)}")
        
        st.markdown("#### Database Statistics")
        stats = st.session_state.supabase.get_dashboard_stats()
        st.json(stats)
        
        st.warning("⚠️ Dangerous Actions")
        if st.button("🗑️ Clear All Data (Requires Confirmation)", type="secondary"):
            st.error("This action cannot be undone. Type 'CONFIRM' to proceed.")
            confirm = st.text_input("Type CONFIRM to delete all data")
            if confirm == "CONFIRM":
                # Add delete logic here
                st.error("Data deletion not implemented for safety")
    
    with tab2:
        st.subheader("Claude AI Configuration")
        
        if st.session_state.claude.client:
            st.success("✅ Claude AI is configured and ready")
            
            # Test AI
            test_text = st.text_area("Test AI Classification", value="John Doe, looking for 2BHK in Baner, budget 80L")
            if st.button("Test Classification"):
                result = st.session_state.claude.classify_with_ai(test_text)
                st.json(result)
        else:
            st.error("❌ Claude API key not configured")
            st.info("Add CLAUDE_API_KEY to your .env file to enable AI features")
        
        st.markdown("#### AI Features")
        st.checkbox("Enable automatic AI classification", value=True)
        st.checkbox("Use AI for location extraction", value=True)
        st.slider("AI Confidence Threshold", 0.0, 1.0, 0.7, 0.1)
    
    with tab3:
        st.subheader("System Settings")
        
        st.markdown("#### File Processing")
        max_file_size = st.number_input("Maximum file size (MB)", min_value=10, max_value=1000, value=500)
        st.selectbox("Default file encoding", ["utf-8", "latin1", "cp1252"])
        
        st.markdown("#### Export Settings")
        st.number_input("Maximum export rows", min_value=1000, max_value=1000000, value=100000)
        
        st.markdown("#### Cache Settings")
        st.slider("Cache duration (seconds)", 0, 3600, 300)
        
        if st.button("Clear Cache"):
            st.cache_data.clear()
            st.success("Cache cleared!")

# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #666;'>"
    "🏠 Real Estate Data Warehouse v1.0 | Powered by Streamlit, Supabase & Claude AI"
    "</div>",
    unsafe_allow_html=True
)
