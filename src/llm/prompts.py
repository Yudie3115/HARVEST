"""
Prompt templates for LLM operations
"""
from src.config.site_configs import DOCUMENT_TYPES, TARGET_CROPS, TOPICS


# ---------------------------------------------------------------------------
# URL classification
# ---------------------------------------------------------------------------

URL_CLASSIFICATION_SYSTEM = (
    "You are a content classifier for an agricultural knowledge base focused "
    "on pre-harvest and post-harvest crop practices in Uganda."
)

URL_CLASSIFICATION_TEMPLATE = """Analyze these URLs and determine their relevance to pre-harvest topics (seed and varieties, planting, crop management, drought and water stress, field pests and diseases, harvest timing and methods) and post-harvest topics (storage, drying, pest management, contamination, quality control, handling, and marketing).

URLs:
{url_list}

For each URL return a JSON object with these fields (be concise):
- url: The original URL
- relevance_score: 0-10 (10 = highly relevant)
- topics: list from {topics}
- document_type: one value from {document_types}
- priority: high/medium/low

Relevant indicators: seed, variety, planting, agronomy, crop management, drought, water stress, field pests, crop diseases, harvesting, post-harvest, storage, drying, pest, loss, handling, preservation, quality, contamination, aflatoxin, PDF/DOC files, research publications, extension guides.

Return as JSON with a single "urls" key containing the array."""


def build_url_classification_prompt(urls: list[str]) -> str:
    url_list = "\n".join(f"{i}. {url}" for i, url in enumerate(urls, 1))
    return URL_CLASSIFICATION_TEMPLATE.format(
        url_list=url_list,
        topics=TOPICS,
        document_types=DOCUMENT_TYPES,
    )


# ---------------------------------------------------------------------------
# Content classification
# ---------------------------------------------------------------------------

CONTENT_CLASSIFICATION_SYSTEM = (
    "You are an agricultural content analyzer specializing in pre-harvest and "
    "post-harvest crop practices."
)

CONTENT_CLASSIFICATION_TEMPLATE = """Analyze this agricultural document excerpt and extract structured metadata for a crop knowledge base covering pre-harvest and post-harvest practices.

Source URL: {url}

Document excerpt:
{content}

Extract the following information:

1. primary_topics: Main topics from this list - {topics}
2. crops_mentioned: Specific crops mentioned from this list - {crops}
3. regions: Geographic areas mentioned (Ugandan districts or regions)
4. document_type: Category from {document_types}
5. target_audience: Who should read this (farmers, extension_workers, researchers, traders, policymakers)
6. language: Primary language (English, Luganda, Swahili, etc.)
7. relevance_score: Rate 0-10 for relevance to pre-harvest and post-harvest crop practices
8. summary: Concise 2-3 sentence summary of the main content
9. key_practices: List of specific best practices or recommendations mentioned
10. actionable: Boolean - does this contain practical, actionable advice?
11. has_data: Boolean - does this contain statistics, measurements, or quantitative data?
12. technical_level: Simple/Intermediate/Advanced - complexity level

Scoring guide:
- 9-10: Highly relevant - dedicated pre-harvest or post-harvest crop guidance, research, or policy
- 7-8: Very relevant - contains substantial pre-harvest or post-harvest crop information
- 5-6: Moderately relevant - mentions pre-harvest or post-harvest topics
- 3-4: Tangentially relevant - agricultural content but not about growing, harvesting, or handling crops (e.g. livestock, general policy)
- 0-2: Not relevant - unrelated to agriculture

Return as a single JSON object with all fields."""


def build_content_classification_prompt(content: str, url: str = "") -> str:
    return CONTENT_CLASSIFICATION_TEMPLATE.format(
        url=url,
        content=content,
        topics=TOPICS,
        document_types=DOCUMENT_TYPES,
        crops=TARGET_CROPS,
    )


# ---------------------------------------------------------------------------
# Information extraction
# ---------------------------------------------------------------------------

INFORMATION_EXTRACTION_SYSTEM = (
    "You are an expert at extracting information from agricultural documents."
)

INFORMATION_EXTRACTION_TEMPLATE = """From this agricultural document, answer the following question or extract the requested information.

Question: {query}

Document excerpt:
{text}

Provide a concise, factual answer based only on the information in the document.
If the answer is not found in the document, respond with "Information not found in document."
"""


def build_information_extraction_prompt(text: str, query: str) -> str:
    return INFORMATION_EXTRACTION_TEMPLATE.format(text=text, query=query)


# ---------------------------------------------------------------------------
# Summarisation
# ---------------------------------------------------------------------------

SUMMARISATION_SYSTEM = "You are an expert at summarizing agricultural content."

SUMMARISATION_TEMPLATE = """Provide a concise {max_length}-character summary of this agricultural text, focusing on key pre-harvest and post-harvest practices and recommendations:

{text}

Summary:"""


def build_summarisation_prompt(text: str, max_length: int = 200) -> str:
    return SUMMARISATION_TEMPLATE.format(text=text[:2000], max_length=max_length)


# ---------------------------------------------------------------------------
# RAG Q&A
# ---------------------------------------------------------------------------

QA_SYSTEM_PROMPT = """You are an agricultural knowledge assistant specialising in pre-harvest and post-harvest crop practices in Uganda and East Africa. Answer questions using only the provided document excerpts. Always cite your sources by referring to the source number (e.g. [1], [2]). If the excerpts do not contain enough information to answer the question, say so clearly — do not fabricate information."""

QA_ANSWER_TEMPLATE = """Use the following document excerpts to answer the question. Each excerpt is preceded by its source number.

{context}

Question: {question}

Provide a clear, structured answer. Cite source numbers inline (e.g. [1]). If the answer spans multiple sources, cite each one where it is relevant."""


_CHUNK_MAX_CHARS = 300


def build_qa_prompt(question: str, chunks: list) -> str:
    """
    Build a RAG prompt from a question and retrieved chunks.

    chunks: list of dicts with keys 'text', 'source_url', 'score'
    Numbers sources [1], [2], ... for citation.
    """
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        text = chunk["text"]
        if len(text) > _CHUNK_MAX_CHARS:
            text = text[:_CHUNK_MAX_CHARS] + "…"
        context_parts.append(
            f"[{i}] Source: {chunk.get('source_url', 'Unknown')}\n{text}"
        )
    context = "\n\n---\n\n".join(context_parts)
    return QA_ANSWER_TEMPLATE.format(context=context, question=question)
