"""
Post-Harvest Knowledge Scraper Dashboard
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(
    page_title="Post-Harvest Scraper Dashboard",
    page_icon="🌾",
    layout="wide"
)

# Sidebar
with st.sidebar:
    st.title("🌾 Post-Harvest Scraper")
    st.write("AI-powered knowledge base builder")
    
    st.divider()
    
    st.subheader("Quick Actions")
    if st.button("▶️ Run Full Crawl", use_container_width=True):
        st.info("Prefect flow integration coming soon...")
    
    if st.button("🔄 Incremental Update", use_container_width=True):
        st.info("Prefect flow integration coming soon...")
    
    st.divider()
    
    # Site filter
    st.subheader("Filters")
    selected_sites = st.multiselect(
        "Sites:",
        ["naro", "agriculture", "extension", "ubos"],
        default=["naro", "agriculture", "extension", "ubos"]
    )

# Main content
st.title("📊 Post-Harvest Knowledge Scraper")
st.caption("Real-time monitoring and management dashboard")

# Tabs
tab1, tab2, tab3 = st.tabs(["📊 Overview", "📄 Documents", "⚙️ Configuration"])

with tab1:
    st.subheader("System Overview")
    
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="Total Documents",
            value="0",
            delta="Waiting for data..."
        )
    
    with col2:
        st.metric(
            label="Processed Today",
            value="0",
            delta="0%"
        )
    
    with col3:
        st.metric(
            label="Avg Relevance",
            value="0.00",
            delta="N/A"
        )
    
    with col4:
        st.metric(
            label="Storage Used",
            value="0 GB",
            delta="N/A"
        )
    
    st.divider()
    
    # Status message
    st.info("""
    👋 **Welcome to the Post-Harvest Knowledge Scraper!**
    
    This dashboard will display:
    - Real-time crawl statistics
    - Document processing status
    - Search capabilities
    - System configuration
    
    **Next steps:**
    1. Run `scripts/init_db.py` to initialize the database
    2. Start a crawl using the Prefect flows
    3. Return here to monitor progress
    
    *Dashboard features are being implemented...*
    """)
    
    # Placeholder chart
    st.subheader("Crawl Activity")
    chart_data = pd.DataFrame({
        'date': pd.date_range(start='2024-01-01', periods=30, freq='D'),
        'discovered': [0] * 30,
        'processed': [0] * 30
    })
    st.line_chart(chart_data.set_index('date'))

with tab2:
    st.subheader("Documents")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        topic_filter = st.selectbox("Topic", ["All", "storage", "drying", "pest_management"])
    with col2:
        status_filter = st.selectbox("Status", ["All", "discovered", "processed", "failed"])
    with col3:
        sort_by = st.selectbox("Sort by", ["Relevance", "Date", "Site"])
    
    st.info("Document database integration pending. Run a crawl to see documents here.")
    
    # Placeholder table
    st.dataframe(
        pd.DataFrame({
            'Title': ['Document 1', 'Document 2'],
            'Site': ['naro', 'agriculture'],
            'Type': ['PDF', 'HTML'],
            'Relevance': [8.5, 7.2],
            'Status': ['discovered', 'discovered']
        }),
        use_container_width=True
    )

with tab3:
    st.subheader("⚙️ System Configuration")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**LLM Settings**")
        llm_provider = st.selectbox(
            "Provider",
            ["openai", "ollama"],
            help="LLM provider for content classification"
        )
        
        if llm_provider == "openai":
            model = st.selectbox("Model", ["gpt-4o-mini", "gpt-4o"])
            st.caption("💡 gpt-4o-mini recommended for cost/performance")
        else:
            model = st.selectbox("Model", ["llama3.1:8b", "llama3.1:70b"])
            st.caption("⚠️ Requires Ollama service running")
        
        temperature = st.slider("Temperature", 0.0, 1.0, 0.1, 0.1)
    
    with col2:
        st.write("**Crawl Settings**")
        max_depth = st.number_input("Max Depth", 1, 10, 4)
        rate_limit = st.number_input("Rate Limit (req/s)", 0.5, 10.0, 2.0, 0.5)
        relevance_threshold = st.slider(
            "Relevance Threshold",
            0.0, 10.0, 6.0, 0.5,
            help="Only process documents above this score"
        )
    
    st.divider()
    
    if st.button("💾 Save Configuration", type="primary"):
        st.success("Configuration saved! (Feature in development)")
    
    st.divider()
    
    # System status
    st.subheader("System Status")
    
    status_data = {
        "Component": ["PostgreSQL", "MinIO", "Qdrant", "LLM Service", "Prefect"],
        "Status": ["🔴 Not Connected", "🔴 Not Connected", "🔴 Not Connected", "🔴 Not Connected", "🔴 Not Connected"],
        "Last Check": ["N/A"] * 5
    }
    st.dataframe(pd.DataFrame(status_data), use_container_width=True)
    
    if st.button("🔄 Check Connections"):
        st.info("Connection check integration coming soon...")

# Footer
st.divider()
st.caption("Built by [Fourlanes](https://fourlanes.co) | Post-Harvest Knowledge Scraper v0.1.0")
