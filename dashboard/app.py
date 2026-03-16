"""
Post-Harvest Knowledge Scraper Dashboard
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional

st.set_page_config(
    page_title="Post-Harvest Scraper Dashboard",
    page_icon="🌾",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Data helpers (lazy connection – gracefully handles DB being offline)
# ---------------------------------------------------------------------------

@st.cache_resource(ttl=60)
def _get_db():
    try:
        from src.storage.postgres import PostgresClient
        return PostgresClient()
    except Exception:
        return None


@st.cache_resource(ttl=60)
def _get_vector_db():
    try:
        from src.storage.vector_db import VectorDBClient
        return VectorDBClient()
    except Exception:
        return None


@st.cache_resource(ttl=60)
def _get_llm():
    try:
        from src.llm.client import LLMClient
        return LLMClient()
    except Exception:
        return None


@st.cache_resource(ttl=3600)
def _get_translator():
    try:
        from src.config.settings import settings
        if not settings.translation_enabled:
            return None
        from src.translation import TranslationClient
        return TranslationClient()
    except Exception:
        return None


def _get_stats() -> Dict:
    db = _get_db()
    if db is None:
        return {"total_documents": 0, "processed_documents": 0, "processing_rate": 0}
    try:
        return db.get_crawl_stats()
    except Exception:
        return {"total_documents": 0, "processed_documents": 0, "processing_rate": 0}


def _get_recent_documents(site_name: Optional[str] = None, limit: int = 50) -> List:
    db = _get_db()
    if db is None:
        return []
    try:
        return db.get_documents(site_name=site_name, limit=limit)
    except Exception:
        return []


def _check_connections() -> Dict[str, bool]:
    results = {}

    # PostgreSQL
    try:
        from src.storage.postgres import PostgresClient
        db = PostgresClient()
        db.get_crawl_stats()
        results["PostgreSQL"] = True
    except Exception:
        results["PostgreSQL"] = False

    # MinIO
    try:
        from src.storage.minio_client import MinIOClient
        m = MinIOClient()
        m.list_objects()
        results["MinIO"] = True
    except Exception:
        results["MinIO"] = False

    # Qdrant
    try:
        from src.storage.vector_db import VectorDBClient
        v = VectorDBClient()
        results["Qdrant"] = v.check_connection()
    except Exception:
        results["Qdrant"] = False

    # LLM
    try:
        from src.llm.client import LLMClient
        llm = LLMClient()
        results["LLM Service"] = llm.check_connection()
    except Exception:
        results["LLM Service"] = False

    # Prefect
    try:
        import httpx
        from src.config.settings import settings
        r = httpx.get(settings.prefect_api_url + "/health", timeout=5)
        results["Prefect"] = r.status_code == 200
    except Exception:
        results["Prefect"] = False

    return results


def _semantic_search(query: str, top_k: int = 10) -> List[Dict]:
    try:
        from src.llm.embeddings import EmbeddingClient
        from src.storage.vector_db import VectorDBClient

        embedder = EmbeddingClient()
        query_vec = embedder.embed(query)

        vector_db = VectorDBClient()
        return vector_db.search(query_vec, top_k=top_k)
    except Exception as e:
        st.error(f"Search failed: {e}")
        return []


def _answer_question(
    question: str, top_k: int, score_threshold: float
) -> tuple[str | None, list, str | None]:
    """Retrieve relevant chunks and synthesise a grounded answer.

    Returns (answer, results, detected_lang).
    detected_lang is None when the question is English or translation is disabled.
    """
    from src.config.settings import settings
    from src.translation import TranslationError

    detected_lang: str | None = None
    english_question = question

    translator = _get_translator() if settings.translation_enabled else None

    # --- Translation: query → English ---
    if translator is not None:
        detected_lang = translator.detect_language(question)
        if detected_lang is not None:
            try:
                english_question = translator.translate_to_english(question, detected_lang)
            except TranslationError as exc:
                st.warning(f"Could not translate your question — searching in original language. ({exc})")
                detected_lang = None

    results = _semantic_search(english_question, top_k)
    results = [r for r in results if r.get("score", 0) >= score_threshold]
    if not results:
        return None, [], None

    chunk_payloads = [r["payload"] for r in results]
    llm = _get_llm()
    if llm is None:
        return None, results, None

    answer = llm.answer_question(english_question, chunk_payloads)

    # --- Translation: answer → local language ---
    if detected_lang is not None and translator is not None:
        try:
            answer = translator.translate_from_english(answer, detected_lang)
        except TranslationError:
            answer = answer + "\n\n*(Could not translate answer — showing in English)*"

    return answer, results, detected_lang


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🌾 Post-Harvest Scraper")
    st.write("AI-powered knowledge base builder")

    st.divider()

    st.subheader("Quick Actions")
    if st.button("▶️ Run Full Crawl", use_container_width=True):
        try:
            from prefect.deployments import run_deployment
            run_deployment("post_harvest_scraper/daily-scraper-production")
            st.success("Full crawl triggered!")
        except Exception as e:
            st.error(f"Could not trigger flow: {e}")

    if st.button("🔄 Incremental Update", use_container_width=True):
        try:
            from prefect.deployments import run_deployment
            run_deployment("incremental_update/incremental-update-production")
            st.success("Incremental update triggered!")
        except Exception as e:
            st.error(f"Could not trigger flow: {e}")

    st.divider()

    st.subheader("Filters")
    selected_sites = st.multiselect(
        "Sites:",
        ["naro", "agriculture", "extension", "ubos"],
        default=["naro", "agriculture", "extension", "ubos"],
    )

# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------

st.title("📊 Post-Harvest Knowledge Scraper")
st.caption("Real-time monitoring and management dashboard")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["📊 Overview", "📄 Documents", "🔍 Search", "🤖 Knowledge Base Q&A", "⚙️ Configuration"]
)

# ---------------------------------------------------------------------------
# Tab 1: Overview
# ---------------------------------------------------------------------------

with tab1:
    st.subheader("System Overview")

    stats = _get_stats()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Documents", stats.get("total_documents", 0))
    with col2:
        st.metric("Processed", stats.get("processed_documents", 0))
    with col3:
        rate = stats.get("processing_rate", 0)
        st.metric("Processing Rate", f"{rate:.0%}")
    with col4:
        # Vector index size
        try:
            vdb = _get_vector_db()
            info = vdb.get_collection_info() if vdb else {}
            st.metric("Vectors Indexed", info.get("vectors_count", 0))
        except Exception:
            st.metric("Vectors Indexed", "N/A")

    st.divider()

    # Recent crawl activity (last 30 days – approximate from DB)
    st.subheader("Crawl Activity")
    docs = _get_recent_documents(limit=200)
    if docs:
        dates = [
            d.discovered_at.date() if d.discovered_at else datetime.utcnow().date()
            for d in docs
        ]
        date_counts = pd.Series(dates).value_counts().sort_index()
        chart_df = pd.DataFrame({
            "date": date_counts.index,
            "documents": date_counts.values,
        }).set_index("date")
        st.line_chart(chart_df)
    else:
        st.info("No crawl data yet. Run a crawl to see activity here.")


# ---------------------------------------------------------------------------
# Tab 2: Documents
# ---------------------------------------------------------------------------

with tab2:
    st.subheader("Documents")

    col1, col2, col3 = st.columns(3)
    with col1:
        site_filter = st.selectbox(
            "Site", ["All"] + ["naro", "agriculture", "extension", "ubos"]
        )
    with col2:
        status_filter = st.selectbox(
            "Status", ["All", "discovered", "queued", "processing", "processed", "failed", "skipped"]
        )
    with col3:
        sort_by = st.selectbox("Sort by", ["Discovered (newest)", "Relevance"])

    site_arg = None if site_filter == "All" else site_filter
    docs = _get_recent_documents(site_name=site_arg, limit=100)

    if not docs:
        st.info("No documents found. Run a crawl to populate the database.")
    else:
        rows = []
        for doc in docs:
            meta = doc.extra_metadata or {}
            llm_cls = meta.get("llm_classification", {})
            rows.append({
                "Title": doc.title or "Untitled",
                "Site": doc.site_name,
                "Type": doc.document_type or "unknown",
                "Status": doc.status.value if doc.status else "unknown",
                "Relevance": llm_cls.get("relevance_score", "-"),
                "Discovered": (
                    doc.discovered_at.strftime("%Y-%m-%d %H:%M")
                    if doc.discovered_at
                    else "N/A"
                ),
                "URL": doc.url,
            })

        df = pd.DataFrame(rows)
        if sort_by == "Relevance":
            df = df.sort_values("Relevance", ascending=False)

        st.dataframe(df, use_container_width=True)
        st.caption(f"Showing {len(df)} documents")


# ---------------------------------------------------------------------------
# Tab 3: Semantic Search
# ---------------------------------------------------------------------------

with tab3:
    st.subheader("🔍 Search Knowledge Base")

    query = st.text_input(
        "Search for post-harvest information:",
        placeholder="e.g. maize storage best practices",
    )
    top_k = st.slider("Results", min_value=3, max_value=20, value=10)

    if query:
        with st.spinner("Searching…"):
            from src.config.settings import settings
            search_query = query
            search_lang: str | None = None
            if settings.translation_enabled:
                from src.translation import TranslationError
                translator = _get_translator()
                if translator is not None:
                    search_lang = translator.detect_language(query)
                    if search_lang is not None:
                        try:
                            search_query = translator.translate_to_english(query, search_lang)
                        except TranslationError:
                            search_lang = None
            results = _semantic_search(search_query, top_k=top_k)
        if search_lang is not None:
            from src.translation import SUPPORTED_LANGUAGES
            lang_name = SUPPORTED_LANGUAGES.get(search_lang, search_lang)
            st.caption(f"Searching in English (translated from {lang_name})")

        if results:
            st.write(f"Found **{len(results)}** relevant chunks")
            for res in results:
                payload = res.get("payload", {})
                score = res.get("score", 0)
                with st.expander(
                    f"[{score:.3f}] {payload.get('source_url', 'Unknown source')}"
                ):
                    st.write(payload.get("text", ""))
                    col1, col2 = st.columns(2)
                    with col1:
                        st.caption(f"Topics: {', '.join(payload.get('topics', []) or ['-'])}")
                        st.caption(f"Crops: {', '.join(payload.get('crops', []) or ['-'])}")
                    with col2:
                        st.caption(f"Type: {payload.get('document_type', 'N/A')}")
                        st.caption(
                            f"Relevance: {payload.get('relevance_score', 'N/A')}"
                        )
        else:
            st.info(
                "No results found. Make sure documents have been processed and "
                "embedded before searching."
            )


# ---------------------------------------------------------------------------
# Tab 4: Knowledge Base Q&A
# ---------------------------------------------------------------------------

with tab4:
    st.subheader("🤖 Knowledge Base Q&A")
    st.caption("Ask a question — the AI will search the knowledge base and synthesise a grounded answer.")

    question = st.text_area(
        "Ask a question about post-harvest practices:",
        placeholder="e.g. What are best practices for maize storage after harvest?",
        height=100,
    )

    with st.expander("Search Filters"):
        qa_top_k = st.slider(
            "Top-K chunks to retrieve",
            min_value=3,
            max_value=15,
            value=8,
            help="Number of document chunks passed to the LLM",
        )
        qa_threshold = st.slider(
            "Minimum similarity score",
            min_value=0.0,
            max_value=0.9,
            value=0.4,
            step=0.05,
            help="Chunks below this score are excluded",
        )

    ask_clicked = st.button("Ask the Knowledge Base", type="primary")

    if ask_clicked and question.strip():
        with st.spinner("Searching knowledge base and generating answer…"):
            answer, results, detected_lang = _answer_question(question.strip(), qa_top_k, qa_threshold)

        if answer is None and not results:
            st.warning(
                "No relevant chunks found above the similarity threshold. "
                "Try lowering the minimum similarity score or rephrasing your question."
            )
        elif answer is None:
            st.error("LLM service is unavailable. Check your configuration in the ⚙️ tab.")
        else:
            st.divider()
            if detected_lang is not None:
                from src.translation import SUPPORTED_LANGUAGES
                lang_name = SUPPORTED_LANGUAGES.get(detected_lang, detected_lang)
                st.caption(f"Detected: {lang_name} — answering in {lang_name}")
            st.markdown("**Answer:**")
            st.info(answer)

            st.divider()
            st.markdown(f"**Sources** ({len(results)} chunks retrieved):")

            for i, res in enumerate(results, 1):
                payload = res.get("payload", {})
                score = res.get("score", 0)
                url = payload.get("source_url", "Unknown source")
                topics = ", ".join(payload.get("topics", []) or ["-"])
                crops = ", ".join(payload.get("crops", []) or ["-"])
                label = f"[{i}] {url}"
                with st.expander(label):
                    st.progress(float(score), text=f"Similarity: {score:.3f}")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.caption(f"Topics: {topics}")
                        st.caption(f"Crops: {crops}")
                    with col2:
                        st.caption(f"Type: {payload.get('document_type', 'N/A')}")
                        st.caption(f"Relevance score: {payload.get('relevance_score', 'N/A')}")
                    st.markdown(f"[Open source]({url})")
                    st.write(payload.get("text", ""))
    elif ask_clicked:
        st.warning("Please enter a question before clicking Ask.")


# ---------------------------------------------------------------------------
# Tab 5: Configuration
# ---------------------------------------------------------------------------

with tab5:
    st.subheader("⚙️ System Configuration")

    col1, col2 = st.columns(2)

    with col1:
        st.write("**LLM Settings**")
        llm_provider = st.selectbox("Provider", ["openai", "ollama"])
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
            "Relevance Threshold", 0.0, 10.0, 6.0, 0.5,
            help="Only process documents above this score",
        )

    st.divider()
    if st.button("💾 Save Configuration", type="primary"):
        st.info(
            "Runtime configuration changes via the dashboard are not yet persisted. "
            "Update your .env file and restart the services to apply changes."
        )

    st.divider()

    # System status
    st.subheader("System Status")

    if st.button("🔄 Check Connections"):
        with st.spinner("Checking…"):
            status = _check_connections()

        status_rows = [
            {
                "Component": name,
                "Status": "🟢 Connected" if ok else "🔴 Not Connected",
            }
            for name, ok in status.items()
        ]
        st.dataframe(pd.DataFrame(status_rows), use_container_width=True)
    else:
        st.caption("Click 'Check Connections' to test service connectivity.")

# Footer
st.divider()
st.caption(
    "Built by [Fourlanes](https://fourlanes.tech) | Post-Harvest Knowledge Scraper v0.2.0"
)
