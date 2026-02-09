from __future__ import annotations

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
    )
    zip_path = write_cards_zip(
        cards,
        context.config.output_dir,
        f"{context.config.xlsx_dir.name}_combined_cards.zip",
        output_format=context.config.output_format,
        reference_docx=context.config.pandoc_reference_docx,
    )

    return StepResult(
        step_id=STEP_BUILD_CARDS,
        artifacts={"cards": cards, "zip_path": zip_path},
        messages=[f"Cards generated: {len(cards)}", f"Output zip: {zip_path}"],
        diagnostics=[f"Cards: {len(cards)}", f"Output: {zip_path}"],
    )
