from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from ..helpers.cards import build_cards, write_cards_zip
from ..helpers.context import PipelineContext, StepResult
from ..helpers.data_models import FragmentType, InnerDict, NameKey, OuterDict, ResourceGroup
from ..helpers.vars import (
    CARD_BUILD_SUBSET_DESCRIPTIONS,
    CARD_INTRODUCTION,
    CSV_ROW_INDEX_COL,
    DOCX_FRAGMENT_COL,
    DOCX_ROW_INDEX_COL,
    DOCX_TABLE_INDEX_COL,
    HCR_XLSX_KEY_PREFIX,
    KTP_DOCX_OPTIONAL_EMPTY_COLS,
    KTP_DOCX_TABLE_1_PREFIX,
    KTP_FILENAME_COL,
    KTP_SOURCE_KEY_COL,
    KTP_TABLE_1_EMPTY_VALUE_PLACEHOLDERS,
    KTP_XLSX_MATCH_COL,
    KTP_XLSX_MATCH_FIRST_TOKENS_KEY,
    KTP_XLSX_MATCH_LAST_NAME_NORM_KEY,
    KTP_XLSX_MATCH_SOURCE_KEY_LAST_KEY,
    KTP_XLSX_MATCH_SOURCE_KEY_TOKENS_KEY,
    SSNAD_FILENAME_COL,
    SSNAF_FILENAME_COL,
    SSNAP_FILENAME_COL,
    SSNAU_FILENAME_COL,
    SSNF_FILENAME_COL,
    SSNHPL0_FILENAME_COL,
    SSNHPL1_FILENAME_COL,
    SSNPAA_FILENAME_COL,
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
            SSNAU_FILENAME_COL,
            SSNAP_FILENAME_COL,
            SSNPAA_FILENAME_COL,
            SSNAF_FILENAME_COL,
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
        source_key_tokens = payload.get(KTP_XLSX_MATCH_SOURCE_KEY_TOKENS_KEY, [])
        source_key_last = payload.get(KTP_XLSX_MATCH_SOURCE_KEY_LAST_KEY)
        first_tokens = payload.get(KTP_XLSX_MATCH_FIRST_TOKENS_KEY, [])
        last_name_norm = payload.get(KTP_XLSX_MATCH_LAST_NAME_NORM_KEY)
        if not isinstance(source_key_tokens, list):
            source_key_tokens = []
        if not isinstance(first_tokens, list):
            first_tokens = []
        source_key_last_str = str(source_key_last).strip() if source_key_last is not None else ""
        last_name_norm_str = str(last_name_norm).strip() if last_name_norm is not None else ""
        source_key_token_values = sorted(
            {str(token).strip() for token in source_key_tokens if str(token).strip()}
        )
        if not source_key_token_values or not source_key_last_str:
            return False
        first_token_values = sorted(
            {str(token).strip() for token in first_tokens if str(token).strip()}
        )
        return (
            source_key_token_values == first_token_values
            and bool(last_name_norm_str)
            and source_key_last_str == last_name_norm_str
        )

    def _is_non_empty_value(value: object) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return False
            if normalized in KTP_TABLE_1_EMPTY_VALUE_PLACEHOLDERS:
                return False
            return True
        return not bool(pd.isna(value))

    def _has_complete_docx_table_fields(inner) -> bool:
        docx_cols = [
            col
            for col in inner.data.keys()
            if col.startswith(KTP_DOCX_TABLE_1_PREFIX) and col not in KTP_DOCX_OPTIONAL_EMPTY_COLS
        ]
        if not docx_cols:
            return True
        return all(_is_non_empty_value(inner.data.get(col)) for col in docx_cols)

    def _filtered_outer_dict() -> OuterDict:
        def _mode_matches(
            mode: int,
            *,
            sciscinet_exactly_one_ok: bool,
            xlsx_exact_ok: bool,
            docx_complete_ok: bool,
        ) -> bool:
            if mode == 0:
                return True
            if mode == 1:
                return sciscinet_exactly_one_ok and xlsx_exact_ok and docx_complete_ok
            if mode == 2:
                return not (sciscinet_exactly_one_ok and xlsx_exact_ok and docx_complete_ok)
            if mode == 3:
                return sciscinet_exactly_one_ok and xlsx_exact_ok
            if mode == 4:
                return not (sciscinet_exactly_one_ok and xlsx_exact_ok)
            raise ValueError(f"Unsupported card_subset_mode={mode}")

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
        docx_filenames: set[str] = set()
        if context.resources is not None:
            all_resources = (
                list(context.resources.parquet_resources.values())
                + list(context.resources.xlsx_resources.values())
                + [context.resources.world_bank_resource]
                + list(context.resources.docx_resources.values())
            )
            docx_filenames = {
                resource.name
                for resource in all_resources
                if resource.group == ResourceGroup.KTP_MANUAL_EXTRACTIONS
                and resource.fragment_type == FragmentType.DOCX_ROW
            }

        all_items = list(outer_dict.items())
        subset_mode_items: dict[int, list[tuple[NameKey, tuple[InnerDict, ...]]]] = {
            mode: [] for mode in CARD_BUILD_SUBSET_DESCRIPTIONS
        }
        sciscinet_count_failures = 0
        xlsx_match_failed = 0
        docx_table_fields_failed = 0
        sciscinet_count_pass = 0
        xlsx_match_pass = 0
        docx_table_fields_pass = 0
        for name_key, inner_dicts in all_items:
            sciscinet_count = sum(
                1 for inner in inner_dicts if _is_sciscinet_inner(inner, sciscinet_filenames)
            )
            sciscinet_exactly_one_ok = sciscinet_count == 1
            xlsx_exact_ok = all(
                _is_exact_xlsx_match_payload(inner.data.get(KTP_XLSX_MATCH_COL))
                for inner in inner_dicts
            )
            docx_innerdicts = []
            for inner in inner_dicts:
                filenames = _extract_filenames(inner.data.get(KTP_FILENAME_COL))
                if filenames & docx_filenames:
                    docx_innerdicts.append(inner)
            # New rule is docx-innerdict-scoped: require at least one docx innerdict
            # where all ktp.table_1_* fields are non-empty.
            docx_complete_ok = (
                not docx_innerdicts
                or any(_has_complete_docx_table_fields(inner) for inner in docx_innerdicts)
            )
            if sciscinet_exactly_one_ok:
                sciscinet_count_pass += 1
            else:
                sciscinet_count_failures += 1
            if xlsx_exact_ok:
                xlsx_match_pass += 1
            else:
                xlsx_match_failed += 1
            if docx_complete_ok:
                docx_table_fields_pass += 1
            else:
                docx_table_fields_failed += 1

            for mode in subset_mode_items:
                if _mode_matches(
                    mode,
                    sciscinet_exactly_one_ok=sciscinet_exactly_one_ok,
                    xlsx_exact_ok=xlsx_exact_ok,
                    docx_complete_ok=docx_complete_ok,
                ):
                    subset_mode_items[mode].append((name_key, inner_dicts))

        subset_items = subset_mode_items[subset_mode]
        total = len(all_items)
        mode_header = f"Card subset mode {subset_mode}: {subset_mode_desc}"
        table_header = f"{'Rule':<44} {'Pass':>6} {'Fail':>6}"
        table_sep = "-" * len(table_header)

        def row(label: str, passed: int, failed: int) -> str:
            return f"{label:<44} {passed:>6} {failed:>6}"

        table_lines = [
            mode_header,
            table_header,
            table_sep,
            row("sciscinet: exactly one innerdict", sciscinet_count_pass, sciscinet_count_failures),
            row("xlsx: all present ktp.xlsx_match exact", xlsx_match_pass, xlsx_match_failed),
            row(
                "docx: required ktp.table_1_* non-empty",
                docx_table_fields_pass,
                docx_table_fields_failed,
            ),
            table_sep,
            row("mode_1", len(subset_mode_items[1]), total - len(subset_mode_items[1])),
            row("mode_2", len(subset_mode_items[2]), total - len(subset_mode_items[2])),
            row("mode_3", len(subset_mode_items[3]), total - len(subset_mode_items[3])),
            row("mode_4", len(subset_mode_items[4]), total - len(subset_mode_items[4])),
            row("selected for current mode", len(subset_items), total - len(subset_items)),
            f"mode_1 description: {CARD_BUILD_SUBSET_DESCRIPTIONS[1]}",
            f"mode_2 description: {CARD_BUILD_SUBSET_DESCRIPTIONS[2]}",
            f"mode_3 description: {CARD_BUILD_SUBSET_DESCRIPTIONS[3]}",
            f"mode_4 description: {CARD_BUILD_SUBSET_DESCRIPTIONS[4]}",
        ]
        log("\n".join(table_lines))
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
