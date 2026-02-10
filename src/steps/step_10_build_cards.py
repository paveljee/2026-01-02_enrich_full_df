from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..helpers.cards import build_cards, write_cards_zip
from ..helpers.context import PipelineContext, StepResult
from ..helpers.data_models import OuterDict, ResourceGroup
from ..helpers.vars import (
    CARD_BUILD_SUBSET_DESCRIPTIONS,
    CARD_INTRODUCTION,
    CSV_ROW_INDEX_COL,
    DOCX_FRAGMENT_COL,
    DOCX_ROW_INDEX_COL,
    DOCX_TABLE_INDEX_COL,
    HCR_XLSX_KEY_PREFIX,
    KTP_FILENAME_COL,
    KTP_SOURCE_KEY_COL,
    KTP_XLSX_MATCH_COL,
    SSNA_FILENAME_COL,
    SSNAD_FILENAME_COL,
    SSNAP_FILENAME_COL,
    SSNF_FILENAME_COL,
    SSNHPL0_FILENAME_COL,
    SSNHPL1_FILENAME_COL,
    STEP_BUILD_CARDS,
)


def run(context: PipelineContext) -> StepResult:
    if context.outer_dict is None:
        raise ValueError("OuterDict not initialized. Run build_outerdict first.")
    outer_dict = context.outer_dict
    subset_mode = int(getattr(context.config, "card_subset_mode", 0))
    if subset_mode not in CARD_BUILD_SUBSET_DESCRIPTIONS:
        raise ValueError(
            f"Unsupported card_subset_mode={subset_mode}. Supported: "
            f"{sorted(CARD_BUILD_SUBSET_DESCRIPTIONS.keys())}"
        )
    subset_mode_desc = CARD_BUILD_SUBSET_DESCRIPTIONS[subset_mode]

    def log(msg: str) -> None:
        if context.log:
            context.log(msg, "cyan")

    def progress_bar(done: int, total: int, width: int = 24) -> str:
        if total <= 0:
            return "[" + ("-" * width) + "]"
        filled = min(width, int(width * done / total))
        return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"

    def hcr_bundle_name() -> str:
        hcr_paths = [
            Path(meta["path"])
            for key, meta in context.config.files_config.items()
            if key.startswith(HCR_XLSX_KEY_PREFIX) and "path" in meta
        ]
        if not hcr_paths:
            return "hcr_xlsx_inputs"
        parent_names = {path.parent.name for path in hcr_paths}
        if len(parent_names) == 1:
            return next(iter(parent_names))
        return "hcr_xlsx_inputs"

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

    def _extract_filenames(value: object) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return set()
            if raw.startswith("[") and raw.endswith("]"):
                try:
                    parsed = json.loads(raw)
                    return {
                        Path(str(item)).name
                        for item in parsed
                        if item is not None and str(item).strip()
                    }
                except json.JSONDecodeError:
                    return {Path(raw).name}
            return {Path(raw).name}
        if isinstance(value, (list, tuple, set)):
            return {
                Path(str(item)).name for item in value if item is not None and str(item).strip()
            }
        return {Path(str(value)).name}

    def _is_sciscinet_inner(inner, sciscinet_filenames: set[str]) -> bool:
        filename_cols = [
            KTP_FILENAME_COL,
            SSNAD_FILENAME_COL,
            SSNA_FILENAME_COL,
            SSNAP_FILENAME_COL,
            SSNHPL0_FILENAME_COL,
            SSNHPL1_FILENAME_COL,
            SSNF_FILENAME_COL,
        ]
        for col in filename_cols:
            values = _extract_filenames(inner.data.get(col))
            if values & sciscinet_filenames:
                return True
        return False

    def _is_exact_xlsx_match_payload(value: object) -> bool:
        if value is None:
            return True
        if not isinstance(value, str):
            return True
        raw = value.strip()
        if not raw:
            return True
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return False
        if not isinstance(payload, dict):
            return False
        for left, right in payload.items():
            if str(left).strip() != str(right).strip():
                return False
        return True

    def _filtered_outer_dict() -> OuterDict:
        sciscinet_filenames: set[str] = set()
        if context.resources is not None:
            all_resources = (
                list(context.resources.parquet_resources.values())
                + list(context.resources.xlsx_resources.values())
                + [context.resources.world_bank_resource]
                + list(context.resources.docx_resources.values())
            )
            sciscinet_filenames = {
                resource.name
                for resource in all_resources
                if resource.group == ResourceGroup.SCISCINET_HF
            }
        all_items = list(outer_dict.items())
        exactly_one = []
        zero_or_many = []
        xlsx_match_failed = 0
        for name_key, inner_dicts in all_items:
            sciscinet_count = sum(
                1 for inner in inner_dicts if _is_sciscinet_inner(inner, sciscinet_filenames)
            )
            xlsx_exact_ok = all(
                _is_exact_xlsx_match_payload(inner.data.get(KTP_XLSX_MATCH_COL))
                for inner in inner_dicts
            )
            if sciscinet_count == 1 and xlsx_exact_ok:
                exactly_one.append((name_key, inner_dicts))
            else:
                zero_or_many.append((name_key, inner_dicts))
                if not xlsx_exact_ok:
                    xlsx_match_failed += 1
        subset_items = all_items
        if subset_mode == 1:
            subset_items = exactly_one
        elif subset_mode == 2:
            subset_items = zero_or_many
        subset_1_desc = CARD_BUILD_SUBSET_DESCRIPTIONS[1]
        subset_2_desc = CARD_BUILD_SUBSET_DESCRIPTIONS[2]
        log(
            "Card subset mode "
            f"{subset_mode}: {subset_mode_desc} "
            f"(selected {len(subset_items)} of {len(all_items)} name keys; "
            f"subset_1='{subset_1_desc}' count={len(exactly_one)}, "
            f"subset_2='{subset_2_desc}' count={len(zero_or_many)}, "
            f"xlsx_exact_failures={xlsx_match_failed})"
        )
        subset_outer = OuterDict.from_name_keys([name_key for name_key, _ in subset_items])
        for name_key, inner_dicts in subset_items:
            for inner in inner_dicts:
                subset_outer.add_inner(name_key, inner)
        return subset_outer

    excluded_cols = {
        KTP_FILENAME_COL,
        KTP_SOURCE_KEY_COL,
        CSV_ROW_INDEX_COL,
        DOCX_TABLE_INDEX_COL,
        DOCX_ROW_INDEX_COL,
        DOCX_FRAGMENT_COL,
    }

    selected_outer_dict = _filtered_outer_dict()
    intro_date = datetime.now(ZoneInfo(context.config.timezone)).strftime("%B %d, %Y")
    subset_intro_note = f"Subset applied: mode {subset_mode} ({subset_mode_desc})."
    intro = f"{CARD_INTRODUCTION.format(intro_date)}\n{subset_intro_note}"
    log("Building cards from selected subset")
    cards = build_cards(
        selected_outer_dict,
        total_draws=context.config.total_draws,
        intro=intro,
        excluded_cols=excluded_cols,
        progress_callback=on_build_progress,
    )
    zip_path = write_cards_zip(
        cards,
        context.config.output_dir,
        f"{hcr_bundle_name()}_combined_cards.zip",
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
