from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import UUID, uuid7
from zipfile import ZipFile

import pytest
from nicegui import ui
from playwright.sync_api import Locator, Page, ViewportSize, expect, sync_playwright

from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AiAugmentCohort,
    AiAugmentIneligibilityCategory,
)
from src.detours.detour_ai_augment.protected.src.control_centre.dashboard.helpers import (
    vars as control_vars,
)
from src.detours.detour_ai_augment.protected.src.control_centre.dashboard.helpers.locale import (
    Locale,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_context import (
    EXPECTED_GROUND_TRUTH_RESEARCHERS,
    EXPECTED_INELIGIBLE_RESEARCHERS,
    EXPECTED_NO_GROUND_TRUTH_RESEARCHERS,
    EXPECTED_SOURCE_RESEARCHERS,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_outer_dict import (
    AiAugmentOuterDict,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard import ui as control_ui
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.run_outcome import (  # noqa: E501
    RunLifecycle,
)
from src.helpers.data_models import InnerDict, NameKey
from src.helpers.procedures import XlsxMatchProcedure
from src.helpers.vars import (
    DRAW_LABEL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
    KTP_NAMEKEY_COL,
)

E2E_SERVER_ARGUMENT = "--serve"
E2E_SERVER_MODULE = (
    "src.detours.detour_ai_augment.tests.control_centre.test_ui_e2e"
)
E2E_HOST = "127.0.0.1"
E2E_START_TIMEOUT_SECONDS = 30
E2E_STOP_TIMEOUT_SECONDS = 10
E2E_REFRESH_WAIT_MILLISECONDS = 2_500
E2E_NARROW_VIEWPORT: ViewportSize = {"width": 915, "height": 1_000}
E2E_WIDE_VIEWPORT: ViewportSize = {"width": 1_600, "height": 1_000}
E2E_GRID_MARKER = "preserved"
E2E_ATTEMPT_BASE_TIME = datetime(2026, 8, 10, tzinfo=timezone.utc)
E2E_LONG_CARD_TOKEN = "responsive-card-content-" * 40
PYTEST_CURRENT_TEST_ENV_NAME = "PYTEST_CURRENT_TEST"
BROWSER_LEADING_RESEARCHER_COUNT = 2
BROWSER_PILOT_INELIGIBLE_DRAW = "pilot.1"
BROWSER_PILOT_ELIGIBLE_DRAW = "pilot.2"
BROWSER_COMPLETED_DRAW = "1"
E2E_CARD_FIELD_LABEL = control_ui.VARIABLE_SPECS[0].ai_column
E2E_CARD_FIELD_VALUE = "literal field value"
E2E_CARD_SECOND_FIELD_LABEL = control_ui.VARIABLE_SPECS[1].ai_column
E2E_CARD_SECOND_FIELD_VALUE = "second literal field value"
E2E_CARD_FILENAME = "source_file.xlsx"
E2E_REFERENCE_DOCX = Path("resources/pandoc-custom-reference.docx")
E2E_DOWNLOADED_DOCX_FILENAME = "pilot2_Pilot_Eligible_Researcher.docx"
E2E_LINE_HEIGHT_TOLERANCE = 0.05
E2E_CARD_BLOCK_GAP_TOLERANCE_PIXELS = 1

GRID_ROW_SELECTOR = ".ag-center-cols-container .ag-row"
GRID_ROOT_SELECTOR = ".ag-root"
GRID_HEADER_SELECTOR = ".ag-header-cell"
GRID_CELL_SELECTOR = ".ag-cell"
GRID_ARIA_ROW_COUNT_OFFSET = 1
EXPECTED_GRID_ARIA_ROW_COUNT = EXPECTED_SOURCE_RESEARCHERS + GRID_ARIA_ROW_COUNT_OFFSET


def browser_researcher(
    *,
    first_name: str,
    last_name: str,
    rnd: int,
    draw_number: str,
    cohort: AiAugmentCohort,
    ineligibility_category: AiAugmentIneligibilityCategory | None = None,
) -> AiAugmentOuterDict:
    namekey = NameKey(first_name=first_name, last_name=last_name)
    return AiAugmentOuterDict(
        namekey=namekey,
        xlsx_innerdicts=(
            InnerDict.from_mapping(
                {
                    KTP_NAMEKEY_COL: namekey.to_json_key(),
                    KTP_FIRST_NAME_COL: first_name,
                    KTP_LAST_NAME_COL: last_name,
                    DRAW_LABEL: draw_number,
                },
                XlsxMatchProcedure(),
            ),
        ),
        ssn_innerdicts=(),
        docx_innerdicts=(),
        ai_augment_rnd=rnd,
        ai_augment_cohort=cohort,
        ai_augment_ineligibility_category=ineligibility_category,
    )


def browser_researchers() -> tuple[AiAugmentOuterDict, ...]:
    researchers = [
        browser_researcher(
            first_name="Pilot Ineligible",
            last_name="Researcher",
            rnd=1,
            draw_number=BROWSER_PILOT_INELIGIBLE_DRAW,
            cohort=AiAugmentCohort.INELIGIBLE,
            ineligibility_category=(
                AiAugmentIneligibilityCategory.RELEASE_BATCH_SUBSET_8
            ),
        ),
        browser_researcher(
            first_name="Pilot Eligible",
            last_name="Researcher",
            rnd=2,
            draw_number=BROWSER_PILOT_ELIGIBLE_DRAW,
            cohort=AiAugmentCohort.GROUND_TRUTH,
        ),
    ]
    remaining_ground_truth = EXPECTED_GROUND_TRUTH_RESEARCHERS - 1
    remaining_no_ground_truth = EXPECTED_NO_GROUND_TRUTH_RESEARCHERS
    remaining_total = EXPECTED_SOURCE_RESEARCHERS - BROWSER_LEADING_RESEARCHER_COUNT
    for index in range(remaining_total):
        if index < remaining_ground_truth:
            cohort = AiAugmentCohort.GROUND_TRUTH
            ineligibility_category = None
        elif index < remaining_ground_truth + remaining_no_ground_truth:
            cohort = AiAugmentCohort.NO_GROUND_TRUTH
            ineligibility_category = None
        else:
            cohort = AiAugmentCohort.INELIGIBLE
            ineligibility_category = (
                AiAugmentIneligibilityCategory.STAGING_PARTITION_2
            )
        first_name = f"First {index + 1}"
        last_name = f"Last {index + 1}"
        researchers.append(
            browser_researcher(
                first_name=first_name,
                last_name=last_name,
                rnd=index + BROWSER_LEADING_RESEARCHER_COUNT + 1,
                draw_number=str(index + 1),
                cohort=cohort,
                ineligibility_category=ineligibility_category,
            )
        )
    return tuple(researchers)


class BrowserController:
    def __init__(self) -> None:
        self._researchers = browser_researchers()
        self._activity_by_namekey = {
            researcher.namekey.to_json_key(): RunLifecycle.READY
            for researcher in self._researchers
        }
        self._run_id_by_namekey: dict[str, UUID] = {}
        self._attempt_run_ids_by_namekey: dict[
            str,
            list[UUID],
        ] = {researcher.namekey.to_json_key(): [] for researcher in self._researchers}
        self._activity_by_run_id: dict[UUID, RunLifecycle] = {}
        self._card_render_count: Counter[str] = Counter()
        self._backend_status = control_ui._BackendStatus.RUNNING
        self._backend_availability = control_ui._BackendAvailability(
            full_api_available=True,
            ipc_available=True,
        )
        completed = self._researchers[BROWSER_LEADING_RESEARCHER_COUNT]
        completed_run_id = uuid7()
        completed_namekey = completed.namekey.to_json_key()
        self._activity_by_namekey[completed_namekey] = RunLifecycle.COMPLETED
        self._run_id_by_namekey[completed_namekey] = completed_run_id
        self._attempt_run_ids_by_namekey[completed_namekey].append(completed_run_id)
        self._activity_by_run_id[completed_run_id] = RunLifecycle.COMPLETED

    @property
    def active_run_id(self) -> None:
        return None

    @property
    def codex_busy(self) -> bool:
        return False

    @property
    def backend_status(self) -> control_ui._BackendStatus:
        return self._backend_status

    @property
    def backend_availability(self) -> control_ui._BackendAvailability:
        return self._backend_availability

    async def start(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def detect_backend_availability(
        self,
    ) -> control_ui._BackendAvailability:
        return self._backend_availability

    async def refresh_from_ipc(self) -> None:
        self._backend_status = control_ui._BackendStatus.STOPPED
        self._backend_availability = control_ui._BackendAvailability(
            full_api_available=False,
            ipc_available=True,
        )

    async def snapshot(
        self,
        *,
        selection: control_ui._UiSelection,
    ) -> control_ui._UiSnapshot:
        variable = control_ui.VARIABLE_SPEC_BY_KEY[selection.variable_key]
        rows = tuple(
            self._project(researcher=researcher, variable=variable)
            for researcher in self._researchers
            if self._matches(researcher=researcher, selection=selection)
        )
        eligible = tuple(
            researcher
            for researcher in self._researchers
            if researcher.ai_augment_cohort is not AiAugmentCohort.INELIGIBLE
        )
        activities = [
            self._activity_by_namekey[researcher.namekey.to_json_key()]
            for researcher in eligible
        ]
        return control_ui._UiSnapshot(
            counts=control_ui._DashboardCounts(
                total=len(self._researchers),
                ground_truth=sum(
                    researcher.ai_augment_cohort is AiAugmentCohort.GROUND_TRUTH
                    for researcher in self._researchers
                ),
                no_ground_truth=sum(
                    researcher.ai_augment_cohort is AiAugmentCohort.NO_GROUND_TRUTH
                    for researcher in self._researchers
                ),
                ineligible=sum(
                    researcher.ai_augment_cohort is AiAugmentCohort.INELIGIBLE
                    for researcher in self._researchers
                ),
                ready=activities.count(RunLifecycle.READY),
                queued=activities.count(RunLifecycle.QUEUED),
                running=activities.count(RunLifecycle.RUNNING),
                complete=activities.count(RunLifecycle.COMPLETED),
                failed=activities.count(RunLifecycle.FAILED),
                cancelled=activities.count(RunLifecycle.CANCELLED),
            ),
            rows=rows,
            backend_status=self._backend_status,
            backend_availability=self._backend_availability,
            active_run_id=None,
        )

    def _project(
        self,
        *,
        researcher: AiAugmentOuterDict,
        variable: control_ui._VariableSpec,
    ) -> control_ui._ResearcherGridRow:
        namekey_json = researcher.namekey.to_json_key()
        activity = self._activity_by_namekey[namekey_json]
        run_id = self._run_id_by_namekey.get(namekey_json)
        attempts = tuple(
            self._attempt_projection(
                researcher=researcher,
                variable=variable,
                run_id=attempt_run_id,
                attempt_index=attempt_index,
            )
            for attempt_index, attempt_run_id in enumerate(
                self._attempt_run_ids_by_namekey[namekey_json]
            )
        )
        projection = (
            attempts[-1]
            if attempts
            else control_ui._AttemptVariableProjection(
                run_id=run_id,
                namekey=researcher.namekey,
                draw_number=researcher.draw_number,
                first_name=researcher.namekey.first_name,
                last_name=researcher.namekey.last_name,
                ai_column=variable.ai_column,
                ai_value=None,
                table_1_column=variable.table_1_column,
                table_1_value=None,
                footnotes=None,
                footnote_arguments=None,
                commit_record_id=None,
                attempt_timestamp=None,
                attempt_lifecycle=activity,
                run_outcome_snapshot_savedness=None,
                session_status=None,
                action=control_ui._VariableProjector.action_for_lifecycle(
                    activity,
                    eligible=(
                        researcher.ai_augment_cohort
                        is not AiAugmentCohort.INELIGIBLE
                    ),
                ),
            )
        )
        return control_ui._ResearcherGridRow(
            researcher=researcher,
            latest=projection,
            attempts=attempts,
        )

    def _attempt_projection(
        self,
        *,
        researcher: AiAugmentOuterDict,
        variable: control_ui._VariableSpec,
        run_id: UUID,
        attempt_index: int,
    ) -> control_ui._AttemptVariableProjection:
        activity = self._activity_by_run_id[run_id]
        ordinal = attempt_index + 1
        has_run_outcome = activity in {
            RunLifecycle.COMPLETED,
            RunLifecycle.FAILED,
            RunLifecycle.CANCELLED,
        }
        return control_ui._AttemptVariableProjection(
            run_id=run_id,
            namekey=researcher.namekey,
            draw_number=researcher.draw_number,
            first_name=researcher.namekey.first_name,
            last_name=researcher.namekey.last_name,
            ai_column=variable.ai_column,
            ai_value=f"ai-value-{ordinal}",
            table_1_column=variable.table_1_column,
            table_1_value=None,
            footnotes=f"footnote-{ordinal}",
            footnote_arguments=f"arguments-{ordinal}",
            commit_record_id=run_id,
            attempt_timestamp=(E2E_ATTEMPT_BASE_TIME + timedelta(seconds=attempt_index)),
            attempt_lifecycle=activity,
            run_outcome_snapshot_savedness=(
                Locale.RUN_OUTCOME_SNAPSHOT_SAVED
                if has_run_outcome
                else None
            ),
            session_status=(
                Locale.SESSION_STATUS_OK if has_run_outcome else None
            ),
            action=control_ui._VariableProjector.action_for_lifecycle(
                activity,
                eligible=True,
            ),
        )

    def _matches(
        self,
        *,
        researcher: AiAugmentOuterDict,
        selection: control_ui._UiSelection,
    ) -> bool:
        activity = self._activity_by_namekey[researcher.namekey.to_json_key()]
        search = selection.search_text.casefold().strip()
        return (
            (
                selection.lifecycle_filter is None
                or selection.lifecycle_filter is activity
            )
            and (
                selection.cohort_filter is None
                or selection.cohort_filter is researcher.ai_augment_cohort
            )
            and (
                not search
                or search in researcher.namekey.first_name.casefold()
                or search in researcher.namekey.last_name.casefold()
                or search in researcher.draw_number.casefold()
                or search == str(researcher.ai_augment_rnd)
                or search in researcher.namekey.to_json_key().casefold()
            )
        )

    async def researcher_card(
        self,
        *,
        namekey: NameKey,
    ) -> control_ui._ResearcherCardView:
        researcher = next(item for item in self._researchers if item.namekey == namekey)
        namekey_json = namekey.to_json_key()
        self._card_render_count[namekey_json] += 1
        render_count = self._card_render_count[namekey_json]
        return control_ui._ResearcherCardView(
            researcher=researcher,
            markdown=(
                f"#### {KTP_FILENAME_COL}: `{E2E_CARD_FILENAME}`\n\n"
                f"render-count-{render_count}\n\n"
                f"**`{E2E_CARD_FIELD_LABEL}`**: {E2E_CARD_FIELD_VALUE}\n\n"
                f"**`{E2E_CARD_SECOND_FIELD_LABEL}`**: "
                f"{E2E_CARD_SECOND_FIELD_VALUE}\n\n"
                f"{E2E_LONG_CARD_TOKEN}"
            ),
        )

    async def queue(self, *, namekey: NameKey) -> UUID:
        researcher = next(item for item in self._researchers if item.namekey == namekey)
        if researcher.ai_augment_cohort is AiAugmentCohort.INELIGIBLE:
            raise ValueError("ineligible namekeys cannot be queued")
        run_id = uuid7()
        namekey_json = namekey.to_json_key()
        self._run_id_by_namekey[namekey_json] = run_id
        self._attempt_run_ids_by_namekey[namekey_json].append(run_id)
        self._activity_by_run_id[run_id] = RunLifecycle.QUEUED
        self._activity_by_namekey[namekey_json] = RunLifecycle.QUEUED
        return run_id

    async def rerun(self, *, namekey: NameKey) -> UUID:
        return await self.queue(namekey=namekey)

    async def cancel(self, *, run_id: UUID) -> None:
        namekey = next(
            source
            for source, candidate in self._run_id_by_namekey.items()
            if candidate == run_id
        )
        self._activity_by_run_id[run_id] = RunLifecycle.CANCELLED
        self._activity_by_namekey[namekey] = RunLifecycle.CANCELLED


def available_e2e_port() -> int:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.bind((E2E_HOST, 0))
            _, port = server_socket.getsockname()
    except PermissionError:
        pytest.skip("local sockets are unavailable in this execution environment")
    return int(port)


def serve_e2e_dashboard(*, port: int) -> None:
    controller = BrowserController()
    control_ui.SERVICES = cast(
        control_ui._ApplicationServices,
        SimpleNamespace(
            controller=controller,
            configuration=SimpleNamespace(
                pipeline_config=SimpleNamespace(
                    pandoc_reference_docx=E2E_REFERENCE_DOCX,
                )
            ),
        ),
    )
    control_ui.configure_application_lifecycle()
    ui.run(
        host=E2E_HOST,
        port=port,
        reload=False,
        show=False,
        show_welcome_message=False,
    )


def wait_for_server(process: subprocess.Popen[str], *, url: str) -> None:
    deadline = time.monotonic() + E2E_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output, _ = process.communicate()
            raise RuntimeError(f"Control Centre E2E server exited during startup:\n{output}")
        try:
            with urllib_request.urlopen(url, timeout=1):
                return
        except OSError, urllib_error.URLError:
            time.sleep(control_vars.BACKEND_READY_POLL_SECONDS)
    raise TimeoutError("Control Centre E2E server did not start")


def grid_row_for_draw(page: Page, draw: str) -> Locator:
    cell = page.locator(
        f'{GRID_CELL_SELECTOR}[col-id="{control_ui.GRID_DRAW_FIELD}"]',
        has_text=re.compile(rf"^{re.escape(draw)}$"),
    )
    return cell.locator("xpath=..")


def assert_shared_width(page: Page) -> None:
    test_ids = (
        control_ui.PAGE_HEADER_TEST_ID,
        control_ui.PAGE_SUMMARY_TEST_ID,
        control_ui.PAGE_FILTERS_TEST_ID,
        control_ui.RESEARCHER_GRID_TEST_ID,
        control_ui.ACTION_PANEL_TEST_ID,
        control_ui.PAGE_FOOTER_TEST_ID,
    )
    widths = [
        page.get_by_test_id(test_id).evaluate("element => element.getBoundingClientRect().width")
        for test_id in test_ids
    ]
    assert max(widths) - min(widths) < 1
    assert page.evaluate("document.documentElement.scrollWidth") == page.evaluate(
        "document.documentElement.clientWidth"
    )


@contextmanager
def control_centre_browser(
    repository_root: Path,
) -> Iterator[tuple[Page, list[str]]]:
    port = available_e2e_port()
    url = f"http://{E2E_HOST}:{port}"
    server_environment = os.environ.copy()
    server_environment.pop(PYTEST_CURRENT_TEST_ENV_NAME, None)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            E2E_SERVER_MODULE,
            E2E_SERVER_ARGUMENT,
            str(port),
        ],
        cwd=repository_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=server_environment,
    )
    try:
        wait_for_server(process, url=url)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport=E2E_WIDE_VIEWPORT)
            errors: list[str] = []
            page.on(
                "console",
                lambda message: errors.append(message.text) if message.type == "error" else None,
            )
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(url, wait_until="networkidle")
            page.wait_for_selector(GRID_ROW_SELECTOR)
            yield page, errors
            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=E2E_STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=E2E_STOP_TIMEOUT_SECONDS)


def test_underscore_field_labels_render_literally_in_researcher_card(
    pytestconfig: pytest.Config,
) -> None:
    with control_centre_browser(pytestconfig.rootpath) as (page, errors):
        eligible_row = grid_row_for_draw(page, BROWSER_PILOT_ELIGIBLE_DRAW)
        eligible_row.click()
        page.get_by_test_id(control_ui.VIEW_CARD_TEST_ID).click()

        field_label = page.get_by_test_id(control_ui.PAGE_FOOTER_TEST_ID).locator(
            "code", has_text=E2E_CARD_FIELD_LABEL
        )
        filename = page.get_by_test_id(control_ui.PAGE_FOOTER_TEST_ID).locator(
            "code", has_text=E2E_CARD_FILENAME
        )
        expect(field_label).to_have_text(E2E_CARD_FIELD_LABEL)
        expect(filename).to_have_text(E2E_CARD_FILENAME)
        assert errors == [], Counter(errors)


def test_main_grid_and_researcher_card_use_compact_line_spacing(
    pytestconfig: pytest.Config,
) -> None:
    with control_centre_browser(pytestconfig.rootpath) as (page, errors):
        eligible_row = grid_row_for_draw(page, BROWSER_PILOT_ELIGIBLE_DRAW)
        eligible_row.click()
        page.get_by_test_id(control_ui.EXECUTE_ACTION_TEST_ID).click()

        history = page.get_by_test_id(control_ui.ATTEMPT_HISTORY_TABLE_TEST_ID)
        history_cell = history.locator("tbody td").first
        expect(history_cell).to_be_visible()
        page.get_by_test_id(control_ui.VIEW_CARD_TEST_ID).click()

        grid_cell = eligible_row.locator(".ag-cell-value").first
        card_paragraphs = page.get_by_test_id(control_ui.PAGE_FOOTER_TEST_ID).locator("p")
        card_paragraph = card_paragraphs.first
        ratios = [
            locator.evaluate(
                "element => {"
                " const style = getComputedStyle(element);"
                " return parseFloat(style.lineHeight) / parseFloat(style.fontSize);"
                "}"
            )
            for locator in (grid_cell, card_paragraph, history_cell)
        ]
        grid_ratio, card_ratio, history_ratio = ratios
        maximum_compact_ratio = control_ui.COMPACT_LINE_HEIGHT + E2E_LINE_HEIGHT_TOLERANCE
        assert grid_ratio <= maximum_compact_ratio
        assert card_ratio <= maximum_compact_ratio
        assert grid_ratio <= history_ratio
        assert card_ratio <= history_ratio
        first_card_box = card_paragraphs.nth(1).bounding_box()
        second_card_box = card_paragraphs.nth(2).bounding_box()
        assert first_card_box is not None
        assert second_card_box is not None
        first_card_bottom = first_card_box["y"] + first_card_box["height"]
        assert second_card_box["y"] - first_card_bottom <= E2E_CARD_BLOCK_GAP_TOLERANCE_PIXELS
        assert errors == [], Counter(errors)


def test_selected_researcher_row_is_highlighted(
    pytestconfig: pytest.Config,
) -> None:
    with control_centre_browser(pytestconfig.rootpath) as (page, errors):
        selected_row = grid_row_for_draw(page, BROWSER_PILOT_ELIGIBLE_DRAW)
        unselected_row = grid_row_for_draw(page, BROWSER_PILOT_INELIGIBLE_DRAW)
        selected_row.click()

        expect(selected_row).to_have_class(re.compile(r"\bag-row-selected\b"))
        expect(selected_row).to_have_attribute("aria-selected", "true")
        selected_background = selected_row.evaluate(
            "element => getComputedStyle(element, '::before').backgroundColor"
        )
        unselected_background = unselected_row.evaluate(
            "element => getComputedStyle(element, '::before').backgroundColor"
        )
        assert selected_background != unselected_background
        assert errors == [], Counter(errors)


def test_researcher_selection_and_attempt_history_are_idempotent(
    pytestconfig: pytest.Config,
) -> None:
    with control_centre_browser(pytestconfig.rootpath) as (page, errors):
        first_row = grid_row_for_draw(page, BROWSER_PILOT_ELIGIBLE_DRAW)
        second_row = grid_row_for_draw(page, "1")
        history_panel = page.get_by_test_id(control_ui.ATTEMPT_HISTORY_PANEL_TEST_ID)
        history_table = page.get_by_test_id(control_ui.ATTEMPT_HISTORY_TABLE_TEST_ID)

        first_row.click()
        expect(first_row).to_have_class(re.compile(r"\bag-row-selected\b"))
        expect(history_table).to_be_visible()
        expect(history_panel).to_contain_text("Pilot Eligible Researcher")

        first_row.click()
        expect(first_row).to_have_class(re.compile(r"\bag-row-selected\b"))
        expect(history_table).to_be_visible()
        expect(history_panel).to_contain_text("Pilot Eligible Researcher")

        second_row.click()
        expect(second_row).to_have_class(re.compile(r"\bag-row-selected\b"))
        expect(first_row).not_to_have_class(re.compile(r"\bag-row-selected\b"))
        expect(history_table).to_be_visible()
        expect(history_panel).to_contain_text("First 1 Last 1")
        assert errors == [], Counter(errors)


def test_completed_researcher_metadata_is_available_in_visible_attempt_history(
    pytestconfig: pytest.Config,
) -> None:
    with control_centre_browser(pytestconfig.rootpath) as (page, errors):
        page.set_viewport_size(E2E_NARROW_VIEWPORT)
        completed_namekey = browser_researchers()[BROWSER_LEADING_RESEARCHER_COUNT].namekey
        page.get_by_label(Locale.SEARCH_FILTER).fill(
            completed_namekey.to_json_key()
        )
        grid = page.get_by_test_id(control_ui.RESEARCHER_GRID_TEST_ID)
        expect(grid.locator(GRID_ROW_SELECTOR)).to_have_count(1)
        completed_row = grid_row_for_draw(page, BROWSER_COMPLETED_DRAW)

        expect(
            completed_row.locator(
                f'{GRID_CELL_SELECTOR}[col-id="{control_ui.GRID_STATUS_FIELD}"]'
            )
        ).to_have_count(0)
        completed_row.click()

        history = page.get_by_test_id(control_ui.ATTEMPT_HISTORY_TABLE_TEST_ID)
        history_rows = history.locator("tbody tr")
        expect(history_rows).to_have_count(1)
        history_cells = history_rows.first.locator("td")
        expect(history_cells.nth(1)).to_have_text(
            RunLifecycle.COMPLETED.value
        )
        expect(history_cells.nth(2)).to_have_text("attempt-1")
        expect(history_cells.nth(3)).to_have_text(
            Locale.RUN_OUTCOME_SNAPSHOT_SAVED
        )
        expect(history_cells.nth(4)).to_have_text(Locale.SESSION_STATUS_OK)
        expect(page.get_by_test_id(control_ui.EXECUTE_ACTION_TEST_ID)).to_have_text(
            control_ui.ACTION_LABEL_BY_VALUE[control_ui._RunAction.RERUN.value]
        )
        view_card = page.get_by_test_id(control_ui.VIEW_CARD_TEST_ID)
        expect(view_card).to_be_enabled()
        view_card.click()
        expect(page.get_by_test_id(control_ui.PAGE_FOOTER_TEST_ID)).to_contain_text(
            E2E_CARD_FIELD_VALUE
        )
        assert errors == [], Counter(errors)


def test_displayed_researcher_card_downloads_as_docx(
    pytestconfig: pytest.Config,
) -> None:
    with control_centre_browser(pytestconfig.rootpath) as (page, errors):
        download_button = page.get_by_test_id(control_ui.DOWNLOAD_CARD_TEST_ID)
        card_markdown = page.get_by_test_id(control_ui.CARD_MARKDOWN_TEST_ID)
        expect(download_button).to_be_disabled()

        eligible_row = grid_row_for_draw(page, BROWSER_PILOT_ELIGIBLE_DRAW)
        eligible_row.click()
        expect(download_button).to_be_disabled()
        page.get_by_test_id(control_ui.VIEW_CARD_TEST_ID).click()
        expect(card_markdown).to_contain_text(E2E_CARD_FIELD_VALUE)
        expect(download_button).to_be_enabled()

        with page.expect_download() as download_info:
            download_button.click()
        download = download_info.value
        assert download.suggested_filename == E2E_DOWNLOADED_DOCX_FILENAME
        downloaded_path = download.path()
        assert downloaded_path is not None
        with ZipFile(downloaded_path) as archive:
            assert "[Content_Types].xml" in archive.namelist()
            document_xml = archive.read("word/document.xml").decode("utf-8")
        assert E2E_CARD_FIELD_VALUE in document_xml
        expect(download_button).to_be_enabled()

        grid_row_for_draw(page, BROWSER_PILOT_INELIGIBLE_DRAW).click()
        expect(card_markdown).to_be_empty()
        expect(download_button).to_be_disabled()
        assert errors == [], Counter(errors)


def test_control_centre_browser_contract(pytestconfig: pytest.Config) -> None:
    repository_root = pytestconfig.rootpath
    port = available_e2e_port()
    url = f"http://{E2E_HOST}:{port}"
    server_environment = os.environ.copy()
    server_environment.pop(PYTEST_CURRENT_TEST_ENV_NAME, None)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            E2E_SERVER_MODULE,
            E2E_SERVER_ARGUMENT,
            str(port),
        ],
        cwd=repository_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=server_environment,
    )
    try:
        wait_for_server(process, url=url)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport=E2E_NARROW_VIEWPORT)
            errors: list[str] = []
            page.on(
                "console",
                lambda message: errors.append(message.text) if message.type == "error" else None,
            )
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(url, wait_until="networkidle")
            page.wait_for_selector(GRID_ROW_SELECTOR)

            backend_status = page.get_by_test_id(
                control_ui.PAGE_HEADER_TEST_ID
            ).get_by_text("Backend API:")
            ipc_status = page.get_by_test_id(control_ui.BACKEND_IPC_STATUS_TEST_ID)
            backend_refresh = page.get_by_test_id(control_ui.BACKEND_REFRESH_TEST_ID)
            expect(backend_status).to_have_text("Backend API: running")
            expect(ipc_status).to_have_text("IPC: available")
            expect(backend_refresh).to_have_text(Locale.ACTION_REFRESH)
            expect(backend_refresh).to_be_enabled()
            status_box = backend_status.bounding_box()
            refresh_box = backend_refresh.bounding_box()
            assert status_box is not None
            assert refresh_box is not None
            assert refresh_box["x"] >= status_box["x"] + status_box["width"]
            backend_refresh.click()
            expect(backend_status).to_have_text("Backend API: stopped")
            expect(ipc_status).to_have_text("IPC: available")
            expect(backend_refresh).to_be_enabled()

            summary = page.get_by_test_id(control_ui.PAGE_SUMMARY_TEST_ID)
            expect(summary).to_contain_text(f"Total {EXPECTED_SOURCE_RESEARCHERS}")
            expect(summary).to_contain_text(
                f"ineligible {EXPECTED_INELIGIBLE_RESEARCHERS}"
            )
            grid = page.get_by_test_id(control_ui.RESEARCHER_GRID_TEST_ID)
            expect(grid.locator('[role="grid"]')).to_have_attribute(
                "aria-rowcount",
                str(EXPECTED_GRID_ARIA_ROW_COUNT),
            )
            headers = grid.locator(GRID_HEADER_SELECTOR)
            expect(headers.nth(0)).to_contain_text(control_ui.GRID_RND_FIELD)
            expect(headers.nth(1)).to_contain_text(DRAW_LABEL)
            assert_shared_width(page)

            page.set_viewport_size(E2E_WIDE_VIEWPORT)
            assert_shared_width(page)
            assert (
                grid.evaluate("element => element.getBoundingClientRect().width")
                > E2E_NARROW_VIEWPORT["width"]
            )

            draw_header = grid.locator(
                f'{GRID_HEADER_SELECTOR}[col-id="{control_ui.GRID_DRAW_FIELD}"]'
            )
            draw_header.click()
            first_row = grid.locator(GRID_ROW_SELECTOR).first
            expect(
                first_row.locator(f'{GRID_CELL_SELECTOR}[col-id="{control_ui.GRID_DRAW_FIELD}"]')
            ).to_have_text("pilot.1")

            footer = page.get_by_test_id(control_ui.PAGE_FOOTER_TEST_ID)
            card_markdown = page.get_by_test_id(control_ui.CARD_MARKDOWN_TEST_ID)
            expect(card_markdown).to_be_empty()
            ineligible_row = grid_row_for_draw(page, "pilot.1")
            ineligible_row.click()
            action_button = page.get_by_test_id(control_ui.EXECUTE_ACTION_TEST_ID)
            expect(action_button).to_be_disabled()
            expect(action_button).to_have_text(
                re.compile(
                    control_ui.ACTION_LABEL_BY_VALUE[control_ui._RunAction.DISABLED.value],
                    re.IGNORECASE,
                )
            )
            assert action_button.evaluate("element => element.tagName") == "BUTTON"

            eligible_row = grid_row_for_draw(page, "pilot.2")
            eligible_row.click()
            expect(action_button).to_be_enabled()
            expect(action_button).to_have_text(
                re.compile(
                    control_ui.ACTION_LABEL_BY_VALUE[control_ui._RunAction.QUEUE.value],
                    re.IGNORECASE,
                )
            )
            view_card_button = page.get_by_test_id(control_ui.VIEW_CARD_TEST_ID)
            expect(view_card_button).to_be_enabled()
            expect(card_markdown).to_be_empty()
            view_card_button.click()
            expect(footer).to_contain_text("render-count-1")
            ineligible_row.click()
            eligible_row.click()
            view_card_button.click()
            expect(footer).to_contain_text("render-count-1")
            page.set_viewport_size(E2E_NARROW_VIEWPORT)
            assert footer.evaluate("element => element.scrollWidth <= element.clientWidth")
            assert_shared_width(page)
            assert errors == [], Counter(errors)

            page.set_viewport_size(E2E_WIDE_VIEWPORT)
            search_input = page.get_by_label(Locale.SEARCH_FILTER)
            search_input.fill("pilot.2")
            expect(grid.locator(GRID_ROW_SELECTOR)).to_have_count(1)
            expect(search_input).to_have_value("pilot.2")
            expect(draw_header).to_have_attribute("aria-sort", "ascending")
            assert errors == [], Counter(errors)

            draw_cell = eligible_row.locator(
                f'{GRID_CELL_SELECTOR}[col-id="{control_ui.GRID_DRAW_FIELD}"]'
            )
            draw_value = draw_cell.locator(".ag-cell-value")
            box = draw_value.bounding_box()
            assert box is not None
            page.mouse.move(box["x"] + 4, box["y"] + box["height"] / 2)
            page.mouse.down()
            page.mouse.move(
                box["x"] + box["width"] - 4,
                box["y"] + box["height"] / 2,
            )
            page.mouse.up()
            assert "pilot.2" in page.evaluate("window.getSelection().toString()")

            grid.locator(GRID_ROOT_SELECTOR).evaluate(
                "(element, marker) => { element.dataset.e2eMarker = marker; }",
                E2E_GRID_MARKER,
            )
            page.wait_for_timeout(E2E_REFRESH_WAIT_MILLISECONDS)
            assert (
                grid.locator(GRID_ROOT_SELECTOR).get_attribute("data-e2e-marker") == E2E_GRID_MARKER
            )

            action_button.click()
            expect(summary).to_contain_text("queued 1")
            expect(action_button).to_have_text(
                re.compile(
                    control_ui.ACTION_LABEL_BY_VALUE[control_ui._RunAction.CANCEL.value],
                    re.IGNORECASE,
                )
            )
            expect(search_input).to_have_value("pilot.2")
            expect(draw_header).to_have_attribute("aria-sort", "ascending")
            assert "pilot.2" in page.evaluate("window.getSelection().toString()")
            assert (
                grid.locator(GRID_ROOT_SELECTOR).get_attribute("data-e2e-marker") == E2E_GRID_MARKER
            )

            eligible_row.click()
            history = page.get_by_test_id(control_ui.ATTEMPT_HISTORY_TABLE_TEST_ID)
            history_rows = history.locator("tbody tr")
            expect(history_rows).to_have_count(1)
            expect(history_rows.nth(0)).to_contain_text("attempt-1")
            expect(history_rows.nth(0)).to_contain_text(
                RunLifecycle.QUEUED.value
            )

            action_button.click()
            expect(action_button).to_have_text(
                re.compile(
                    control_ui.ACTION_LABEL_BY_VALUE[control_ui._RunAction.RERUN.value],
                    re.IGNORECASE,
                )
            )
            action_button.click()
            expect(history_rows).to_have_count(2)
            expect(history_rows.nth(0)).to_contain_text("attempt-1")
            expect(history_rows.nth(1)).to_contain_text("attempt-2")
            expect(
                eligible_row.locator(
                    f'{GRID_CELL_SELECTOR}[col-id="{control_ui.GRID_AI_VALUE_FIELD}"]'
                )
            ).to_have_text("ai-value-2")
            assert errors == [], Counter(errors)
            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=E2E_STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=E2E_STOP_TIMEOUT_SECONDS)


if __name__ == "__main__":
    try:
        server_argument, server_port = sys.argv[1:]
    except ValueError as exc:
        raise SystemExit(f"expected {E2E_SERVER_ARGUMENT} PORT") from exc
    if server_argument != E2E_SERVER_ARGUMENT:
        raise SystemExit(f"expected {E2E_SERVER_ARGUMENT} PORT")
    serve_e2e_dashboard(port=int(server_port))
