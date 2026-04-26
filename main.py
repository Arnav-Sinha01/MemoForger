"""
main.py
=======
MemoForge — Module 5: Application Orchestrator
-----------------------------------------------
"""

from __future__ import annotations

import logging
import sys
import threading
import traceback
from pathlib import Path
from typing import List, Optional

import customtkinter as ctk
from app_frame import MemoForgeApp
from verification_hub import open_verification_hub

from ingestion_engine import (
    DocumentIngestor,
    DocumentChunk,
    IngestionError,
    ImageOnlyPDFError,
    UnsupportedFormatError,
)

from vlm_pipeline import (
    VLMPipeline,
    GenerationResult,
    ModelLoadError,
    PipelineError,
)

logger = logging.getLogger(__name__)

_AMBER  = ("#1a1a18", "#d4a017")
_GREEN  = ("#1a6e2e", "#6a9955")
_RED    = ("#8b1a1a", "#c0392b")
_ORANGE = ("#7a4a00", "#c87941")

class MemoForgeController(MemoForgeApp):
    def _on_generate(self) -> None:
        ready_paths, config = self.get_generation_inputs()

        if not ready_paths:
            self.status_bar.set_status("Add at least one supported document before generating.", _RED)
            self._shake_button()
            return

        self.set_generating_state(True)
        worker = threading.Thread(
            target=self._pipeline_worker,
            args=(ready_paths, config),
            name="MemoForge-Pipeline",
            daemon=True,
        )
        worker.start()

    def _pipeline_worker(self, ready_paths: List[Path], config) -> None:
        selected_model = getattr(config, "model_id", None) or "qwen3-vl:2b"
        pipeline = VLMPipeline(model_id=selected_model)
        try:
            chunks = self._ingest_documents(ready_paths, config)
            if not chunks:
                self.after(0, lambda: self._on_worker_error("Ingestion produced no usable content.", _RED))
                return

            total_chunks = len(chunks)
            self.after(0, lambda: (
                self.status_bar.set_indeterminate(True),
                self.status_bar.set_status("Checking connection with model...", _AMBER),
            ))

            pipeline.load_model(
                status_callback=lambda msg: self.after(
                    0, lambda m=msg: self.status_bar.set_status(m, _AMBER)
                )
            )

            self.after(0, lambda: (
                self.status_bar.set_indeterminate(False),
                self.status_bar.set_status("Connection successful. Processing next (0%)", _AMBER),
                self.status_bar.update_progress(0, total_chunks),
            ))

            def _progress_callback(done: int, total: int, result: GenerationResult) -> None:
                def _update(d=done, t=total, r=result):
                    self.status_bar.update_progress(d, t)
                    pct = int((d / t) * 100) if t > 0 else 0
                    if r.succeeded:
                        msg, color = f"Processing next... ({pct}%)", _AMBER
                    else:
                        msg, color = f"Chunk {d}/{t} failed: {r.error or 'unknown error'} ({pct}%)", _ORANGE
                    self.status_bar.set_status(msg, color)
                self.after(0, _update)

            results: List[GenerationResult] = pipeline.run(
                chunks,
                config=config,
                progress_callback=_progress_callback,
            )

            pipeline.unload_model()
            self.after(0, lambda: self._on_pipeline_complete(results))

        except Exception as exc:
            logger.exception("Error in pipeline worker: %s", exc)
            err_msg = f"Error: {exc}"
            self.after(0, lambda m=err_msg: self._on_worker_error(m, _RED))
        finally:
            try:
                pipeline.unload_model()
            except Exception:
                pass

    def _ingest_documents(self, ready_paths: List[Path], config) -> List[DocumentChunk]:
        ingestor = DocumentIngestor(chunk_size=512, overlap=64)
        all_chunks: List[DocumentChunk] = []
        total_files = len(ready_paths)

        for file_index, path in enumerate(ready_paths, start=1):
            display_name = path.name if len(path.name) <= 40 else path.name[:37] + "..."
            status_text = f"Ingesting {file_index}/{total_files}: {display_name}"
            
            self.after(0, lambda msg=status_text: (
                self.status_bar.set_status(msg, _AMBER),
                self.status_bar.update_progress(file_index - 1, total_files),
            ))

            try:
                all_chunks.extend(ingestor.ingest(path))
            except Exception as exc:
                self.after(0, lambda m=f"'{path.name}' failed: {exc}": self.status_bar.set_status(m, _RED))

        return all_chunks

    def _on_pipeline_complete(self, results: List[GenerationResult]) -> None:
        total_cards   = sum(len(r.flashcards) for r in results)
        total_chunks  = len(results)
        failed_chunks = sum(1 for r in results if not r.succeeded)
        succeeded     = total_chunks - failed_chunks

        if failed_chunks == 0:
            summary_color, summary_msg = _GREEN, f"Done! {total_cards} card(s) from {succeeded} chunk(s)."
        elif succeeded > 0:
            summary_color, summary_msg = _ORANGE, f"Partial success: {total_cards} card(s). {failed_chunks} chunk(s) failed."
        else:
            summary_color, summary_msg = _RED, f"All {total_chunks} chunk(s) failed."

        self.set_generating_state(False)
        self.status_bar.set_status(summary_msg, summary_color)
        open_verification_hub(parent=self, results=results, on_close=lambda: self.set_generating_state(False), modal=True)

    def _on_worker_error(self, message: str, color: str = _RED) -> None:
        self.set_generating_state(False)
        self.status_bar.set_status(message, color)


def run_app() -> None:
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s", stream=sys.stdout)

    # Colour theme is global; appearance mode is restored by MemoForgeApp from user settings.
    ctk.set_default_color_theme("dark-blue")

    try:
        app = MemoForgeController()
        logger.info("MemoForgeController initialised. Entering event loop.")
        app.mainloop()
    except KeyboardInterrupt:
        logger.info("Application closed by user.")
    except Exception as exc:
        logger.critical("Fatal error in main thread:\n%s", traceback.format_exc())
        raise

if __name__ == "__main__":
    run_app()
