from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from ..helpers.cards import build_cards, write_cards_zip
from ..helpers.context import PipelineContext, StepResult
from ..helpers.vars import (
    CSV_ROW_INDEX_COL,
    DOCX_FRAGMENT_COL,
    DOCX_ROW_INDEX_COL,
    DOCX_TABLE_INDEX_COL,
    KTP_FILENAME_COL,
    KTP_SOURCE_KEY_COL,
    STEP_BUILD_CARDS,
)


def run(context: PipelineContext) -> StepResult:
    if context.outer_dict is None:
        raise ValueError("OuterDict not initialized. Run build_outerdict first.")

    def log(msg: str) -> None:
        if context.log:
            context.log(msg, "cyan")

    def progress_bar(done: int, total: int, width: int = 24) -> str:
        if total <= 0:
            return "[" + ("-" * width) + "]"
        filled = min(width, int(width * done / total))
        return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"

    def on_build_progress(done: int, total: int, _card_id: str) -> None:
        log(
            f"Card build progress {progress_bar(done, total)} "
            f"{done}/{total}"
        )

    def on_conversion_progress(done: int, total: int, _card_id: str) -> None:
        phase = "DOCX conversion" if context.config.output_format == "docx" else "Output write"
        log(
            f"{phase} progress {progress_bar(done, total)} "
            f"{done}/{total}"
        )

    excluded_cols = {
        KTP_FILENAME_COL,
        KTP_SOURCE_KEY_COL,
        CSV_ROW_INDEX_COL,
        DOCX_TABLE_INDEX_COL,
        DOCX_ROW_INDEX_COL,
        DOCX_FRAGMENT_COL,
    }

    cards = build_cards(
        context.outer_dict,
        total_draws=context.config.total_draws,
        intro_date=datetime.now(ZoneInfo(context.config.timezone)).strftime("%B %d, %Y"),
        excluded_cols=excluded_cols,
        progress_callback=on_build_progress,
    )
    zip_path = write_cards_zip(
        cards,
        context.config.output_dir,
        f"{context.config.xlsx_dir.name}_combined_cards.zip",
        output_format=context.config.output_format,
        reference_docx=context.config.pandoc_reference_docx,
        docx_workers=max(1, min(8, os.cpu_count() or 1)),
        progress_callback=on_conversion_progress,
    )

    return StepResult(
        step_id=STEP_BUILD_CARDS,
        artifacts={"cards": cards, "zip_path": zip_path},
        messages=[f"Cards generated: {len(cards)}", f"Output zip: {zip_path}"],
        diagnostics=[f"Cards: {len(cards)}", f"Output: {zip_path}"],
    )
