# vlm_pipeline.py
# ─────────────────────────────────────────────────────────────────────────────
# MemoForge · VLM Pipeline (Ollama Engine Swap)
# Handles local communication with Ollama and Qwen3 2B-VL.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import base64
import json
import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, List, Optional, Tuple

import requests
try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from ingestion_engine import DocumentChunk

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "qwen3-vl:2b"
OLLAMA_BASE_URL = "http://localhost:11434"

# ── Exceptions ────────────────────────────────────────────────────────────────

class ModelLoadError(Exception): pass
class PipelineError(Exception): pass

# ── Enums & Config ────────────────────────────────────────────────────────────

class TaskType(Enum):
    FLASHCARDS = auto()
    SUMMARY = auto()
    COMBINED = auto()

@dataclass
class GenerationConfig:
    model_id: str = DEFAULT_MODEL_ID
    task_type: TaskType = TaskType.COMBINED
    max_flashcards: int = 8
    max_new_tokens: int = 1024
    temperature: float = 0.3
    top_p: float = 0.9
    repetition_penalty: float = 1.1
    summary_max_sentences: int = 5
    vision_render_dpi: int = 150
    max_workers: int = 1
    retry_on_parse_failure: bool = True
    anki_export: bool = False

# ── Dataclasses (Required by main.py and verification_hub.py) ─────────────────

@dataclass
class Flashcard:
    question: str
    answer: str
    difficulty: str = "medium"
    tags: List[str] = field(default_factory=list)
    source_chunk_index: int = -1

@dataclass
class GenerationResult:
    chunk_index: int
    source_file: str
    flashcards: List[Flashcard] = field(default_factory=list)
    summary: str = ""
    was_vision_chunk: bool = False
    error: Optional[str] = None
    latency_seconds: float = 0.0

    @property
    def succeeded(self) -> bool:
        return self.error is None

# ── Public API ────────────────────────────────────────────────────────────────

class VLMPipeline:
    def __init__(self, model_id: str = DEFAULT_MODEL_ID):
        self.model_id = (model_id or DEFAULT_MODEL_ID).strip()
        self.is_loaded = False

    def load_model(self, status_callback: Optional[Callable[[str], None]] = None) -> None:
        """Ensure Ollama is reachable and the selected model is available."""
        try:
            self._ensure_ollama_runtime(status_callback=status_callback)
            models = self._get_available_models()
            if not any(self.model_id == m or self.model_id in m for m in models):
                if status_callback:
                    status_callback(f"Model '{self.model_id}' not found. Pulling with Ollama...")
                self._pull_model(status_callback=status_callback)
                models = self._get_available_models()
                if not any(self.model_id == m or self.model_id in m for m in models):
                    raise ModelLoadError(
                        f"Model '{self.model_id}' could not be installed. "
                        f"Try manually: ollama pull {self.model_id}"
                    )
            self.is_loaded = True
            if status_callback:
                status_callback(f"Model '{self.model_id}' is ready.")
        except requests.exceptions.RequestException:
            raise ModelLoadError(f"Could not connect to Ollama at {OLLAMA_BASE_URL}. Is it running?")
        except ModelLoadError:
            raise
        except Exception as exc:
            raise ModelLoadError(f"Unable to prepare model '{self.model_id}': {exc}")

    def unload_model(self) -> None:
        """Frees VRAM by telling Ollama to drop the model from memory."""
        try:
            requests.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={"model": self.model_id, "keep_alive": 0},
                timeout=5
            )
        except Exception:
            pass
        self.is_loaded = False

    def _get_available_models(self) -> List[str]:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=8)
        resp.raise_for_status()
        return [m.get("name", "") for m in resp.json().get("models", [])]

    def _ensure_ollama_runtime(self, status_callback: Optional[Callable[[str], None]] = None) -> None:
        if self._is_ollama_api_ready():
            return

        if status_callback:
            status_callback("Ollama not running. Starting local service...")
        if not self._start_ollama_service():
            if status_callback:
                status_callback("Ollama not found. Installing automatically...")
            self._install_ollama_windows()
            if not self._start_ollama_service():
                raise ModelLoadError("Ollama could not be started after installation.")

        if not self._wait_for_ollama_api(timeout_seconds=45):
            raise ModelLoadError("Ollama service did not become ready in time.")

    def _is_ollama_api_ready(self) -> bool:
        try:
            resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
            return resp.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def _start_ollama_service(self) -> bool:
        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
            time.sleep(1.0)
            return True
        except OSError:
            return False

    def _wait_for_ollama_api(self, timeout_seconds: int = 45) -> bool:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self._is_ollama_api_ready():
                return True
            time.sleep(0.8)
        return False

    def _install_ollama_windows(self) -> None:
        try:
            winget = subprocess.run(
                ["winget", "--version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                shell=False,
            )
            if winget.returncode != 0:
                raise ModelLoadError(
                    "Ollama is missing and winget is unavailable. Install Ollama from https://ollama.com/download/windows"
                )

            install = subprocess.run(
                [
                    "winget",
                    "install",
                    "--id",
                    "Ollama.Ollama",
                    "-e",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                ],
                check=False,
                shell=False,
            )
            if install.returncode != 0:
                raise ModelLoadError("Automatic Ollama installation failed via winget.")
        except FileNotFoundError as exc:
            raise ModelLoadError(
                "Could not run winget to install Ollama. Install Ollama manually from https://ollama.com/download/windows"
            ) from exc

    def _pull_model(self, status_callback: Optional[Callable[[str], None]] = None) -> None:
        pull_resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/pull",
            json={"name": self.model_id, "stream": True},
            stream=True,
            timeout=1200,
        )
        pull_resp.raise_for_status()

        for raw_line in pull_resp.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = raw_line.strip()
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if event.get("error"):
                raise ModelLoadError(f"Ollama pull failed: {event['error']}")

            if status_callback:
                status = event.get("status", "").strip()
                total = event.get("total")
                completed = event.get("completed")
                if isinstance(total, int) and total > 0 and isinstance(completed, int):
                    pct = int((completed / total) * 100)
                    status_callback(f"Downloading '{self.model_id}'... {pct}%")
                elif status:
                    status_callback(status)

    def run(
        self, 
        chunks: List[DocumentChunk], 
        config, 
        progress_callback: Optional[Callable[[int, int, GenerationResult], None]] = None
    ) -> List[GenerationResult]:
        """Main entry point called by the orchestrator."""
        if not self.is_loaded:
            self.load_model()

        results = []
        total = len(chunks)

        for i, chunk in enumerate(chunks, 1):
            result = self._process_chunk(chunk, config)
            results.append(result)
            if progress_callback:
                progress_callback(i, total, result)

        return results

    def _process_chunk(self, chunk: DocumentChunk, config) -> GenerationResult:
        import time
        start_time = time.time()
        
        result = GenerationResult(
            chunk_index=chunk.chunk_index,
            source_file=chunk.source_file,
            was_vision_chunk=chunk.requires_vision
        )

        try:
            images_b64: List[str] = []
            text_content = chunk.text
            wants_flashcards, wants_summary = self._resolve_task_flags(config)

            # Handle Vision requests natively for image-only PDFs
            if chunk.requires_vision:
                if not fitz:
                    raise PipelineError("PyMuPDF is required for vision chunks. Run: pip install pymupdf")
                
                doc = fitz.open(chunk.source_file)
                page_num = chunk.metadata.get("page", 1) - 1
                page = doc.load_page(page_num)
                render_dpi = int(getattr(config, "vision_render_dpi", 150) or 150)
                pix = page.get_pixmap(dpi=render_dpi)
                img_bytes = pix.tobytes("png")
                images_b64.append(base64.b64encode(img_bytes).decode("utf-8"))
                text_content = "Extract the educational content visible in this slide/page image."
                doc.close()

            system_prompt = self._build_system_prompt(
                wants_flashcards=wants_flashcards,
                wants_summary=wants_summary,
                config=config,
            )

            # Construct the Ollama payload
            message = {"role": "user", "content": text_content}
            if images_b64:
                message["images"] = images_b64

            payload = {
                "model": self.model_id,
                "messages": [{"role": "system", "content": system_prompt}, message],
                "stream": False,
                "options": {
                    "temperature": float(getattr(config, "temperature", 0.3) or 0.3),
                    "top_p": float(getattr(config, "top_p", 0.9) or 0.9),
                    "repeat_penalty": float(getattr(config, "repetition_penalty", 1.1) or 1.1),
                    "num_predict": int(getattr(config, "max_new_tokens", 1024) or 1024),
                },
            }
            if wants_flashcards and not wants_summary:
                # Ask Ollama to strictly return JSON when only flashcards are requested.
                payload["format"] = "json"
            # We rely on our regex parser because strict 'json' format often breaks small LLM arrays
            max_attempts = 3 if getattr(config, "retry_on_parse_failure", True) else 1
            
            for attempt in range(max_attempts):
                try:
                    resp = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=120)
                    resp.raise_for_status()
                    
                    content = resp.json().get("message", {}).get("content", "")
                    self._parse_output(
                        content=content,
                        result=result,
                        wants_flashcards=wants_flashcards,
                        wants_summary=wants_summary,
                        config=config,
                        source_text=text_content,
                    )
                    
                    # If we expected flashcards but got none, throw an error to trigger retry
                    if wants_flashcards and not result.flashcards:
                        raise ValueError("Model hallucinated or returned empty JSON array.")
                    if wants_summary and not result.summary.strip():
                        raise ValueError("Model returned no summary text.")
                        
                    # Success
                    result.error = None
                    break

                except Exception as e:
                    result.error = str(e)
                    logger.warning(f"Chunk inference attempt {attempt+1}/{max_attempts} failed: {e}")
                    result.flashcards = []
                    result.summary = ""

        except Exception as e:
            result.error = f"Pre-inference processing error: {e}"
            logger.error(f"Chunk processing failed: {e}")
            
        result.latency_seconds = time.time() - start_time
        return result

    def _parse_output(
        self,
        content: str,
        result: GenerationResult,
        wants_flashcards: bool,
        wants_summary: bool,
        config: GenerationConfig,
        source_text: str,
    ) -> None:
        """Extract flashcards and/or summary from the model response."""
        if wants_flashcards:
            max_cards = max(1, int(getattr(config, "max_flashcards", 8) or 8))
            try:
                cards_data = self._extract_flashcard_array(content)
            except Exception as exc:
                cards_data = self._fallback_flashcards_from_text(
                    model_text=content,
                    source_text=source_text,
                    max_cards=max_cards,
                )
                if not cards_data:
                    raise ValueError(str(exc))
            for card in cards_data[:max_cards]:
                question = self._clean_generated_field(
                    str(card.get("question", card.get("front", card.get("Question", ""))))
                )
                answer = self._clean_generated_field(
                    str(card.get("answer", card.get("back", card.get("Answer", ""))))
                )
                if not question or not answer:
                    continue
                raw_tags = card.get("tags", [])
                tags = raw_tags if isinstance(raw_tags, list) else [str(raw_tags)]
                tags = [self._clean_tag(str(tag)) for tag in tags]
                tags = [tag for tag in tags if tag]
                difficulty = str(card.get("difficulty", "medium")).strip().lower()
                if difficulty not in {"easy", "medium", "hard"}:
                    difficulty = "medium"

                result.flashcards.append(
                    Flashcard(
                        question=question,
                        answer=answer,
                        difficulty=difficulty,
                        tags=tags,
                        source_chunk_index=result.chunk_index,
                    )
                )

        if wants_summary:
            summary_text = self._extract_summary_text(
                content=content,
                remove_card_json=True,
            )
            max_sentences = max(1, int(getattr(config, "summary_max_sentences", 5) or 5))
            if not summary_text.strip():
                summary_text = self._fallback_summary_from_source(
                    source_text=source_text,
                    max_sentences=max_sentences,
                )
            if not summary_text.strip():
                summary_text = self._clean_generated_field(content)[:500]
            result.summary = self._limit_summary_sentences(summary_text, max_sentences)

    def _resolve_task_flags(self, config: GenerationConfig) -> Tuple[bool, bool]:
        task = getattr(config, "task_type", getattr(config, "task", None))
        task_name = task.name if hasattr(task, "name") else str(task).upper()
        wants_flashcards = ("FLASHCARD" in task_name) or ("COMBINED" in task_name)
        wants_summary = ("SUMMARY" in task_name) or ("COMBINED" in task_name)
        return wants_flashcards, wants_summary

    @staticmethod
    def _build_system_prompt(
        wants_flashcards: bool,
        wants_summary: bool,
        config: GenerationConfig,
    ) -> str:
        prompt_parts = [
            "You are a structured study assistant.",
            "Use only the provided content.",
        ]
        if wants_flashcards:
            prompt_parts.append(
                "Return JSON flashcards as an array with objects using keys: "
                "question, answer, difficulty, tags."
            )
            if not wants_summary:
                prompt_parts.append("Output only valid JSON. Do not add commentary.")
            prompt_parts.append(
                f"Generate at most {max(1, int(getattr(config, 'max_flashcards', 8) or 8))} flashcards."
            )
            prompt_parts.append("Set difficulty to easy, medium, or hard.")
        if wants_summary:
            if wants_flashcards:
                prompt_parts.append(
                    "After the JSON flashcards, add a plain-text section that starts with 'Summary:' and contains only study notes."
                )
            else:
                prompt_parts.append(
                    "Return only plain-text study notes for the summary. Do not output JSON, code blocks, or schema text."
                )
            prompt_parts.append(
                f"Keep summary to about {max(1, int(getattr(config, 'summary_max_sentences', 5) or 5))} sentences."
            )
        return " ".join(prompt_parts)

    @staticmethod
    def _extract_flashcard_array(content: str) -> List[dict]:
        candidates: List[str] = []

        fenced_json_blocks = re.findall(r"```json\s*(.*?)```", content, re.DOTALL | re.IGNORECASE)
        fenced_any_blocks = re.findall(r"```\s*(.*?)```", content, re.DOTALL)

        candidates.extend(block.strip() for block in fenced_json_blocks if block.strip())
        candidates.extend(block.strip() for block in fenced_any_blocks if block.strip())
        candidates.append(content.strip())

        last_error: Optional[Exception] = None
        for candidate in candidates:
            try:
                parsed = VLMPipeline._decode_first_json_value(candidate)
                parsed = VLMPipeline._normalize_flashcard_payload(parsed)
                if not isinstance(parsed, list):
                    raise ValueError("Flashcard response was not a JSON list.")
                if not all(isinstance(item, dict) for item in parsed):
                    raise ValueError("Flashcard list contains non-object items.")
                return parsed
            except Exception as exc:
                last_error = exc

        raise ValueError(f"Unable to parse flashcards JSON from model output: {last_error}")

    @staticmethod
    def _decode_first_json_value(text: str):
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char not in "[{":
                continue
            try:
                parsed, _ = decoder.raw_decode(text[index:])
                return parsed
            except json.JSONDecodeError:
                continue
        raise ValueError("No JSON object/array found in model output.")

    @staticmethod
    def _normalize_flashcard_payload(parsed):
        if isinstance(parsed, dict):
            if isinstance(parsed.get("flashcards"), list):
                return parsed["flashcards"]
            return [parsed]
        return parsed

    @staticmethod
    def _fallback_flashcards_from_text(model_text: str, source_text: str, max_cards: int) -> List[dict]:
        """
        Build flashcards from non-JSON model output.

        Strategy:
        1) Parse explicit Q:/A: pairs.
        2) If absent, derive cards from informative sentences.
        """
        cards: List[dict] = []
        text = (model_text or "").strip()
        src = (source_text or "").strip()

        qa_pattern = re.compile(
            r"(?:^|\n)\s*(?:Q(?:uestion)?\s*[:\-]\s*)(.+?)\n\s*(?:A(?:nswer)?\s*[:\-]\s*)(.+?)(?=\n\s*(?:Q(?:uestion)?\s*[:\-])|\Z)",
            re.IGNORECASE | re.DOTALL,
        )
        for q_match, a_match in qa_pattern.findall(text):
            question = " ".join(q_match.split()).strip()
            answer = " ".join(a_match.split()).strip()
            if question and answer:
                cards.append(
                    {
                        "question": question,
                        "answer": answer,
                        "difficulty": "medium",
                        "tags": [],
                    }
                )
                if len(cards) >= max_cards:
                    return cards

        if cards:
            return cards

        if VLMPipeline._looks_like_structured_output(text):
            sentence_source = src
        else:
            sentence_source = text if len(text) >= 40 else src
        sentence_source = re.sub(r"```.*?```", " ", sentence_source, flags=re.DOTALL)
        sentence_source = re.sub(r"\s+", " ", sentence_source).strip()
        if not sentence_source:
            return cards

        sentences = re.split(r"(?<=[.!?])\s+", sentence_source)
        for sentence in sentences:
            sentence = sentence.strip(" -•\t\r\n")
            if len(sentence) < 35:
                continue
            topic_words = [w for w in re.split(r"\s+", sentence) if w]
            topic = " ".join(topic_words[:8]).strip(" ,.;:-")
            if not topic:
                continue
            cards.append(
                {
                    "question": f"What is a key point about {topic}?",
                    "answer": sentence,
                    "difficulty": "medium",
                    "tags": [],
                }
            )
            if len(cards) >= max_cards:
                break

        return cards

    @staticmethod
    def _extract_summary_text(content: str, remove_card_json: bool) -> str:
        text = content.strip()
        text = re.sub(r"```(?:json)?\s*.*?```", " ", text, flags=re.DOTALL | re.IGNORECASE)
        marker = re.search(r"\bsummary\b\s*[:\-]\s*", text, flags=re.IGNORECASE)
        if marker:
            text = text[marker.end():]
        if remove_card_json:
            text = re.sub(
                r"\[\s*\{.*?(?:question|answer|flashcards|difficulty|tags).*?\}\s*\]",
                " ",
                text,
                flags=re.DOTALL | re.IGNORECASE,
            )
            text = re.sub(
                r"\{\s*\"?(?:flashcards|question|answer|difficulty|tags)\"?\s*:.*?\}",
                " ",
                text,
                flags=re.DOTALL | re.IGNORECASE,
            )
        text = re.sub(
            r"\{\s*\"?[A-Za-z_][A-Za-z0-9_\-\s]*\"?\s*:\s*\"?[^{}]{0,240}\"?\s*\}",
            " ",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"^\s*summary\s*[:\-]\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(
            r"^\s*\"?[A-Za-z_][A-Za-z0-9_\-\s]*\"?\s*:\s*\"?[^{}]{0,240}\"?\}?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"\s+", " ", text).strip()
        text = VLMPipeline._clean_generated_field(text)
        return text.strip()

    @staticmethod
    def _limit_summary_sentences(summary: str, max_sentences: int) -> str:
        if not summary:
            return ""
        sentences = re.split(r"(?<=[.!?])\s+", summary.strip())
        trimmed = [s.strip() for s in sentences if s.strip()][:max_sentences]
        return " ".join(trimmed)

    @staticmethod
    def _clean_generated_field(text: str) -> str:
        cleaned = (text or "").strip()
        if not cleaned:
            return ""

        cleaned = re.sub(r"```(?:json)?|```", " ", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.replace("\\n", " ").replace("\\t", " ")
        cleaned = re.sub(r"^\s*(?:question|answer|summary|q|a)\s*[:\-]\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip().strip("`").strip()

        if cleaned.startswith("{") and cleaned.endswith("}"):
            try:
                parsed = VLMPipeline._decode_first_json_value(cleaned)
                if isinstance(parsed, dict):
                    for key in ("question", "answer", "summary", "text", "content"):
                        value = parsed.get(key)
                        if isinstance(value, str) and value.strip():
                            cleaned = value.strip()
                            break
            except Exception:
                pass

        cleaned = re.sub(r"^[\[\{]+", "", cleaned)
        cleaned = re.sub(r"[\]\}]+$", "", cleaned)
        cleaned = cleaned.strip().strip('"').strip("'").strip()
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def _clean_tag(tag: str) -> str:
        cleaned = VLMPipeline._clean_generated_field(tag).lstrip("#")
        cleaned = re.sub(r"[^\w\s\-]", "", cleaned, flags=re.UNICODE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
        return cleaned[:40]

    @staticmethod
    def _looks_like_structured_output(text: str) -> bool:
        snippet = (text or "").strip()[:4000]
        if not snippet:
            return False
        if re.search(r"\"(?:question|answer|flashcards|difficulty|tags)\"\s*:", snippet, re.IGNORECASE):
            return True
        structural_chars = sum(1 for ch in snippet if ch in "{}[]\":,")
        ratio = structural_chars / max(1, len(snippet))
        return ratio > 0.08 and ("{" in snippet or "[" in snippet)

    @staticmethod
    def _fallback_summary_from_source(source_text: str, max_sentences: int) -> str:
        source = re.sub(r"\s+", " ", (source_text or "").strip())
        if not source:
            return ""
        sentences = re.split(r"(?<=[.!?])\s+", source)
        informative = [s.strip() for s in sentences if len(s.strip()) >= 35]
        if not informative:
            informative = [source[:300].strip()]
        return " ".join(informative[:max_sentences]).strip()
