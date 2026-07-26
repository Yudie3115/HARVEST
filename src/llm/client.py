"""
Unified LLM client supporting OpenAI (primary) and Ollama (fallback)
"""
import json
from typing import Dict, Generator, List, Optional
from loguru import logger
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from src.config.settings import settings
from src.config.site_configs import POST_HARVEST_TOPICS, DOCUMENT_TYPES, TARGET_CROPS


class LLMContextTooLargeError(Exception):
    """Raised when the LLM rejects a request because the token count exceeds its limit."""


class LLMClient:
    """Unified client for OpenAI and Ollama LLM providers"""

    def __init__(
        self,
        provider: str = None,
        model: str = None,
        temperature: float = None,
    ):
        # Auto-detect provider based on API key availability
        if provider is None:
            provider = settings.llm_provider
            if provider == "openai" and not settings.openai_api_key:
                logger.warning("OpenAI API key not found, falling back to Ollama")
                provider = "ollama"
            elif provider == "groq" and not settings.groq_api_key:
                logger.warning("Groq API key not found, falling back to Ollama")
                provider = "ollama"

        self.provider = provider
        self.temperature = temperature

        if self.provider == "openai":
            from openai import OpenAI

            if not settings.openai_api_key:
                raise ValueError("OpenAI API key required but not found in settings")

            self.client = OpenAI(api_key=settings.openai_api_key)
            self.model = model or settings.openai_model
            self.temperature = temperature or settings.openai_temperature
            logger.info(f"Initialized OpenAI client with model {self.model}")

        elif self.provider == "groq":
            from openai import OpenAI

            if not settings.groq_api_key:
                raise ValueError("Groq API key required but not found in settings")
            self.client = OpenAI(
                api_key=settings.groq_api_key,
                base_url="https://api.groq.com/openai/v1",
            )
            self.model = model or settings.groq_model
            self.temperature = temperature or settings.groq_temperature
            logger.info(f"Initialized Groq client with model {self.model}")

        elif self.provider == "ollama":
            try:
                import ollama

                self.client = ollama.Client(host=settings.ollama_base_url)
                self.model = model or settings.ollama_model
                self.temperature = temperature or settings.ollama_temperature
                logger.info(
                    f"Initialized Ollama client: {settings.ollama_base_url} with model {self.model}"
                )
            except ImportError:
                raise ImportError(
                    "Ollama package not installed. Install with: poetry install --extras ollama"
                )
        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_not_exception_type(LLMContextTooLargeError),
    )
    def _generate(
        self,
        prompt: str,
        system_prompt: str = None,
        response_format: str = "json",
        temperature: float = None,
        max_tokens: int = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Generate response from LLM with retry logic"""
        try:
            if self.provider in ("openai", "groq"):
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                if history:
                    messages.extend(history)
                messages.append({"role": "user", "content": prompt})

                kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature or self.temperature,
                    "max_completion_tokens": max_tokens or settings.openai_max_tokens,
                }

                if response_format == "json":
                    kwargs["response_format"] = {"type": "json_object"}

                response = self.client.chat.completions.create(**kwargs)
                return response.choices[0].message.content

            else:  # ollama
                fmt = "json" if response_format == "json" else ""
                if history:
                    # ollama.generate() is single-turn; use chat() for multi-turn
                    messages = []
                    if system_prompt:
                        messages.append({"role": "system", "content": system_prompt})
                    messages.extend(history)
                    messages.append({"role": "user", "content": prompt})
                    response = self.client.chat(
                        model=self.model,
                        messages=messages,
                        format=fmt,
                        options={
                            "temperature": temperature or self.temperature,
                            "num_predict": max_tokens or settings.ollama_max_tokens,
                        },
                    )
                    return response.message.content
                else:
                    response = self.client.generate(
                        model=self.model,
                        prompt=prompt,
                        system=system_prompt or "",
                        format=fmt,
                        options={
                            "temperature": temperature or self.temperature,
                            "num_predict": max_tokens or settings.ollama_max_tokens,
                        },
                    )
                    return response.response

        except Exception as e:
            if self.provider in ("openai", "groq"):
                try:
                    from openai import APIStatusError

                    if isinstance(e, APIStatusError) and e.status_code == 413:
                        raise LLMContextTooLargeError(str(e)) from e
                except ImportError:
                    pass
            elif self.provider == "ollama":
                try:
                    import ollama as _ollama

                    if isinstance(e, _ollama.ResponseError) and (
                        "context" in str(e).lower() or "too long" in str(e).lower()
                    ):
                        raise LLMContextTooLargeError(str(e)) from e
                except ImportError:
                    pass
            logger.error(f"LLM generation error ({self.provider}): {e}")
            raise

    def classify_urls(self, urls: List[str]) -> List[Dict]:
        """
        Classify a batch of URLs for relevance to post-harvest topics

        Args:
            urls: List of URLs to classify

        Returns:
            List of classification results
        """
        # Process in batches of 20 to keep responses well within token limits
        BATCH_SIZE = 20
        all_results = []

        for i in range(0, len(urls), BATCH_SIZE):
            batch = urls[i : i + BATCH_SIZE]

            system_prompt = "You are a content classifier for an agricultural knowledge base focused on post-harvest practices in Uganda."

            prompt = f"""Analyze these URLs and determine their relevance to post-harvest topics such as storage, drying, pest management, contamination, quality control, handling, and marketing.

URLs:
{chr(10).join(f"{idx}. {url}" for idx, url in enumerate(batch, 1))}

For each URL return a JSON object with these fields (be concise):
- url: The original URL
- relevance_score: 0-10 (10 = highly relevant)
- topics: list from {POST_HARVEST_TOPICS}
- document_type: one value from {DOCUMENT_TYPES}
- priority: high/medium/low

Relevant indicators: post-harvest, storage, drying, pest, loss, handling, preservation, quality, contamination, aflatoxin, PDF/DOC files, research publications, extension guides.

Return as JSON with a single "urls" key containing the array.
"""

            try:
                response = self._generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    response_format="json",
                    temperature=0.1,
                )
                batch_results = json.loads(response)

                # Ensure it's a list
                if isinstance(batch_results, dict) and "urls" in batch_results:
                    batch_results = batch_results["urls"]
                elif not isinstance(batch_results, list):
                    batch_results = [batch_results]

                all_results.extend(batch_results)

                logger.debug(f"Classified batch of {len(batch)} URLs using {self.provider}")

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response: {e}")
                # Return default classifications
                all_results.extend(
                    [
                        {
                            "url": url,
                            "relevance_score": 5.0,
                            "topics": [],
                            "document_type": "unknown",
                            "priority": "medium",
                            "reason": "Classification failed",
                        }
                        for url in batch
                    ]
                )
            except Exception as e:
                logger.error(f"URL classification error: {e}")
                all_results.extend(
                    [
                        {
                            "url": url,
                            "relevance_score": 5.0,
                            "topics": [],
                            "document_type": "unknown",
                            "priority": "medium",
                            "reason": f"Error: {str(e)}",
                        }
                        for url in batch
                    ]
                )

        return all_results

    def classify_content(self, content: str, url: str = "", max_length: int = 4000) -> Dict:
        """
        Classify document content and extract metadata

        Args:
            content: Document text content
            url: Source URL
            max_length: Maximum content length to analyze

        Returns:
            Classification metadata dictionary
        """
        # Truncate content if too long
        truncated_content = content[:max_length]

        system_prompt = (
            "You are an agricultural content analyzer specializing in post-harvest practices."
        )

        prompt = f"""Analyze this agricultural document excerpt and extract structured metadata for a post-harvest knowledge base.

Source URL: {url}

Document excerpt:
{truncated_content}

Extract the following information:

1. primary_topics: Main topics from this list - {POST_HARVEST_TOPICS}
2. crops_mentioned: Specific crops mentioned from this list - {TARGET_CROPS}
3. regions: Geographic areas mentioned (Ugandan districts or regions)
4. document_type: Category from {DOCUMENT_TYPES}
5. target_audience: Who should read this (farmers, extension_workers, researchers, traders, policymakers)
6. language: Primary language (English, Luganda, Swahili, etc.)
7. relevance_score: Rate 0-10 for post-harvest knowledge base relevance
8. summary: Concise 2-3 sentence summary of the main content
9. key_practices: List of specific best practices or recommendations mentioned
10. actionable: Boolean - does this contain practical, actionable advice?
11. has_data: Boolean - does this contain statistics, measurements, or quantitative data?
12. technical_level: Simple/Intermediate/Advanced - complexity level

Scoring guide:
- 9-10: Highly relevant - dedicated post-harvest guidance, research, or policy
- 7-8: Very relevant - contains substantial post-harvest information
- 5-6: Moderately relevant - mentions post-harvest topics
- 3-4: Tangentially relevant - agricultural content but not post-harvest focused
- 0-2: Not relevant - unrelated to agriculture or post-harvest

Return as a single JSON object with all fields.
"""

        try:
            response = self._generate(
                prompt=prompt, system_prompt=system_prompt, response_format="json", temperature=0.2
            )
            classification = json.loads(response)

            # Normalize field names: LLM may return primary_topics/crops_mentioned
            if "primary_topics" in classification and "topics" not in classification:
                classification["topics"] = classification.pop("primary_topics")
            if "crops_mentioned" in classification and "crops" not in classification:
                classification["crops"] = classification.pop("crops_mentioned")

            # Validate and set defaults
            classification.setdefault("relevance_score", 5.0)
            classification.setdefault("topics", [])
            classification.setdefault("crops", [])
            classification.setdefault("regions", [])
            classification.setdefault("actionable", False)
            classification.setdefault("has_data", False)

            logger.debug(
                f"Classified content ({self.provider}): relevance={classification['relevance_score']}, "
                f"topics={classification['topics']}"
            )

            return classification

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse content classification: {e}")
            return self._default_classification(content)
        except Exception as e:
            logger.error(f"Content classification error: {e}")
            return self._default_classification(content)

    def extract_information(self, text: str, query: str, max_length: int = 3000) -> str:
        """
        Extract specific information from text based on a query

        Args:
            text: Source text
            query: Question or information to extract
            max_length: Maximum text length to analyze

        Returns:
            Extracted information as string
        """
        truncated_text = text[:max_length]

        system_prompt = "You are an expert at extracting information from agricultural documents."

        prompt = f"""From this agricultural document, answer the following question or extract the requested information.

Question: {query}

Document excerpt:
{truncated_text}

Provide a concise, factual answer based only on the information in the document. 
If the answer is not found in the document, respond with "Information not found in document."
"""

        try:
            response = self._generate(
                prompt=prompt,
                system_prompt=system_prompt,
                response_format="",  # Free-form text
                temperature=0.3,
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Information extraction error: {e}")
            return "Error extracting information"

    def summarize_batch(self, texts: List[str], max_length: int = 200) -> List[str]:
        """
        Generate summaries for a batch of texts

        Args:
            texts: List of text content to summarize
            max_length: Maximum length per summary

        Returns:
            List of summaries
        """
        summaries = []

        for text in texts:
            system_prompt = "You are an expert at summarizing agricultural content."

            prompt = f"""Provide a concise {max_length}-character summary of this agricultural text, focusing on key post-harvest practices and recommendations:

{text[:2000]}

Summary:"""

            try:
                summary = self._generate(
                    prompt=prompt, system_prompt=system_prompt, response_format="", temperature=0.3
                )
                summaries.append(summary.strip()[:max_length])
            except Exception as e:
                logger.error(f"Summarization error: {e}")
                summaries.append(text[:max_length] + "...")

        return summaries

    @staticmethod
    def _default_classification(content: str) -> Dict:
        """Return default classification when LLM fails"""
        return {
            "relevance_score": 5.0,
            "topics": [],
            "crops": [],
            "regions": [],
            "document_type": "unknown",
            "target_audience": [],
            "language": "en",
            "summary": content[:200] + "...",
            "key_practices": [],
            "actionable": False,
            "has_data": False,
            "technical_level": "unknown",
        }

    def answer_question(
        self,
        question: str,
        chunks: List[Dict],
        max_tokens: int = 1024,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        RAG answer synthesis. chunks contain 'text' and 'source_url'.
        history: optional prior turns [{"role": "user"/"assistant", "content": "..."}]
        Returns the LLM's answer string (may include [1]-style citations).
        """
        from src.llm.prompts import QA_SYSTEM_PROMPT, build_qa_prompt

        prompt = build_qa_prompt(question, chunks)
        return self._generate(
            prompt=prompt,
            system_prompt=QA_SYSTEM_PROMPT,
            response_format="",
            max_tokens=max_tokens,
            history=history,
        )

    def evaluate_catalogue_candidate(self, question: str, answer: str) -> Dict:
        """Return a bounded quality score and a reusable English question."""
        prompt = f"""Assess whether this post-harvest Q&A is useful as a reusable public catalogue entry.

Question:
{question[:3000]}

Answer:
{answer[:7000]}

Return JSON with exactly:
- worth_cataloguing_score: number from 0 to 1
- optimised_question: a clear, standalone English question of at most 300 characters

Prefer practical, generally reusable questions. Reject greetings, personal requests, vague follow-ups,
and answers that depend on missing conversational context."""
        raw = self._generate(
            prompt=prompt,
            system_prompt=(
                "You curate a trusted post-harvest agriculture Q&A catalogue. "
                "Return valid JSON only and do not add facts."
            ),
            response_format="json",
            temperature=0.0,
            max_tokens=300,
        )
        result = json.loads(raw)
        score = max(0.0, min(1.0, float(result["worth_cataloguing_score"])))
        optimised = str(result["optimised_question"]).strip()[:300]
        if not optimised:
            raise ValueError("LLM returned an empty optimised_question")
        return {"worth_cataloguing_score": score, "optimised_question": optimised}

    def suggest_followup_questions(
        self,
        question: str,
        answer: str,
        chunks: List[Dict],
    ) -> List[str]:
        """Generate a small set of grounded, useful next research questions."""
        evidence = "\n\n".join(str(chunk.get("text", ""))[:600] for chunk in chunks[:4])
        prompt = f"""Suggest three useful follow-up questions for a researcher reading this answer.

Original question:
{question[:1500]}

Answer:
{answer[:5000]}

Available evidence excerpts:
{evidence[:2400]}

Return JSON with exactly one key, "questions", containing 3 concise standalone questions.
Questions should deepen, compare, quantify, or turn the answer into a practical next step.
Do not claim that the evidence contains information it does not contain."""
        raw = self._generate(
            prompt=prompt,
            system_prompt=(
                "You help researchers navigate trusted post-harvest agriculture evidence. "
                "Return valid JSON only."
            ),
            response_format="json",
            temperature=0.2,
            max_tokens=350,
        )
        result = json.loads(raw)
        questions = result.get("questions")
        if not isinstance(questions, list):
            raise ValueError("LLM returned invalid follow-up questions")
        cleaned: List[str] = []
        for value in questions:
            text = str(value).strip()[:240]
            if text and text not in cleaned:
                cleaned.append(text)
        return cleaned[:3]

    def stream_answer(
        self,
        question: str,
        chunks: List[Dict],
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Generator[str, None, None]:
        """
        Stream answer tokens for a RAG question. Yields one string per token.
        Does not use @retry — retrying a half-consumed stream is unsafe.
        """
        from src.llm.prompts import QA_SYSTEM_PROMPT, build_qa_prompt

        prompt = build_qa_prompt(question, chunks)

        messages = []
        if QA_SYSTEM_PROMPT:
            messages.append({"role": "system", "content": QA_SYSTEM_PROMPT})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        try:
            if self.provider in ("openai", "groq"):
                stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_completion_tokens=1024,
                    stream=True,
                )
                for chunk in stream:
                    delta = chunk.choices[0].delta.content
                    if delta is not None:
                        yield delta

            else:  # ollama
                stream = self.client.chat(
                    model=self.model,
                    messages=messages,
                    stream=True,
                    options={
                        "temperature": self.temperature,
                        "num_predict": 1024,
                    },
                )
                for chunk in stream:
                    delta = chunk.message.content
                    if delta:
                        yield delta

        except Exception as exc:
            if self.provider in ("openai", "groq"):
                try:
                    from openai import APIStatusError

                    if isinstance(exc, APIStatusError) and exc.status_code == 413:
                        raise LLMContextTooLargeError(str(exc)) from exc
                except ImportError:
                    pass
            logger.error(f"LLM streaming error ({self.provider}): {exc}")
            raise

    def check_connection(self) -> bool:
        """Check if LLM service is accessible"""
        try:
            if self.provider in ("openai", "groq"):
                # Simple test request — works for both since Groq uses the OpenAI SDK
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": "test"}],
                    max_completion_tokens=5,
                )
                logger.info(f"Connected to {self.provider} with model {self.model}")
                return True
            else:  # ollama
                tags = self.client.list()
                models = (
                    tags.get("models", [])
                    if isinstance(tags, dict)
                    else getattr(tags, "models", [])
                )

                available_models = [
                    (
                        m.get("name") or m.get("model")
                        if isinstance(m, dict)
                        else getattr(m, "name", None) or getattr(m, "model", None)
                    )
                    for m in models
                ]

                available_models = [m for m in available_models if m]

                logger.info(f"Connected to Ollama. Available models: {available_models}")
                return True
        except Exception as e:
            logger.error(f"Cannot connect to {self.provider}: {e}")
            return False
