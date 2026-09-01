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
from uuid import UUID, uuid4

import pytest
from playwright.sync_api import Page, ViewportSize, expect, sync_playwright

from src.detours.detour_ai_augment.src.control_centre.dashboard import ui as control_ui
from src.helpers.data_models import NameKey
from src.helpers.vars import KTP_FILENAME_COL

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]

E2E_SERVER_ARGUMENT = "--serve"
E2E_SERVER_MODULE = "src.detours.detour_ai_augment.tests.test_control_centre_e2e"
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
E2E_CARD_FIELD_LABEL = control_ui.VARIABLE_SPECS[0].ai_column
E2E_CARD_FIELD_VALUE = "literal field value"
E2E_CARD_SECOND_FIELD_LABEL = control_ui.VARIABLE_SPECS[1].ai_column
E2E_CARD_SECOND_FIELD_VALUE = "second literal field value"
E2E_CARD_FILENAME = "source_file.xlsx"
E2E_LINE_HEIGHT_TOLERANCE = 0.05
E2E_CARD_BLOCK_GAP_TOLERANCE_PIXELS = 1

GRID_ROW_SELECTOR = ".ag-center-cols-container .ag-row"
GRID_ROOT_SELECTOR = ".ag-root"
GRID_HEADER_SELECTOR = ".ag-header-cell"
GRID_CELL_SELECTOR = ".ag-cell"
GRID_ARIA_ROW_COUNT_OFFSET = 1
EXPECTED_GRID_ARIA_ROW_COUNT = control_ui.EXPECTED_SOURCE_RESEARCHERS + GRID_ARIA_ROW_COUNT_OFFSET


def browser_researchers() -> tuple[control_ui.Researcher, ...]:
    researchers = [
        control_ui.Researcher(
            namekey=control_ui.Namekey(
                NameKey(
                    first_name="Pilot Ineligible",
                    last_name="Researcher",
                ).to_json_key()
            ),
            rnd=1,
            draw_numbers=(BROWSER_PILOT_INELIGIBLE_DRAW,),
            first_name="Pilot Ineligible",
            last_name="Researcher",
            cohort=control_ui.ResearcherCohort.INELIGIBLE,
            ineligibility_category=(control_ui.IneligibilityCategory.RELEASE_BATCH_SUBSET_8),
        ),
        control_ui.Researcher(
            namekey=control_ui.Namekey(
                NameKey(
                    first_name="Pilot Eligible",
                    last_name="Researcher",
                ).to_json_key()
            ),
            rnd=2,
            draw_numbers=(BROWSER_PILOT_ELIGIBLE_DRAW,),
            first_name="Pilot Eligible",
            last_name="Researcher",
            cohort=control_ui.ResearcherCohort.GROUND_TRUTH,
        ),
    ]
    remaining_ground_truth = control_ui.EXPECTED_GROUND_TRUTH_RESEARCHERS - 1
    remaining_no_ground_truth = control_ui.EXPECTED_NO_GROUND_TRUTH_RESEARCHERS
    remaining_total = control_ui.EXPECTED_SOURCE_RESEARCHERS - BROWSER_LEADING_RESEARCHER_COUNT
    for index in range(remaining_total):
        if index < remaining_ground_truth:
            cohort = control_ui.ResearcherCohort.GROUND_TRUTH
            ineligibility_category = None
        elif index < remaining_ground_truth + remaining_no_ground_truth:
            cohort = control_ui.ResearcherCohort.NO_GROUND_TRUTH
            ineligibility_category = None
        else:
            cohort = control_ui.ResearcherCohort.INELIGIBLE
            ineligibility_category = control_ui.IneligibilityCategory.STAGING_PARTITION_2
        first_name = f"First {index + 1}"
        last_name = f"Last {index + 1}"
        researchers.append(
            control_ui.Researcher(
                namekey=control_ui.Namekey(
                    NameKey(
                        first_name=first_name,
                        last_name=last_name,
                    ).to_json_key()
                ),
                rnd=index + BROWSER_LEADING_RESEARCHER_COUNT + 1,
                draw_numbers=(str(index + 1),),
                first_name=first_name,
                last_name=last_name,
                cohort=cohort,
                ineligibility_category=ineligibility_category,
            )
        )
    return tuple(researchers)


class BrowserController:
    def __init__(self) -> None:
        self._researchers = browser_researchers()
        self._status_by_namekey = {
            researcher.namekey: control_ui.RunStatus.READY for researcher in self._researchers
        }
        self._run_id_by_namekey: dict[control_ui.Namekey, UUID] = {}
        self._attempt_run_ids_by_namekey: dict[
            control_ui.Namekey,
            list[UUID],
        ] = {researcher.namekey: [] for researcher in self._researchers}
        self._status_by_run_id: dict[UUID, control_ui.RunStatus] = {}
        self._card_render_count: Counter[control_ui.Namekey] = Counter()

    @property
    def active_run_id(self) -> None:
        return None

    @property
    def codex_busy(self) -> bool:
        return False

    async def start(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def snapshot(
        self,
        *,
        selection: control_ui.UiSelection,
    ) -> control_ui.UiSnapshot:
        variable = control_ui.VARIABLE_SPEC_BY_KEY[selection.variable_key]
        rows = tuple(
            self._project(researcher=researcher, variable=variable)
            for researcher in self._researchers
            if self._matches(researcher=researcher, selection=selection)
        )
        eligible = tuple(
            researcher
            for researcher in self._researchers
            if researcher.cohort is not control_ui.ResearcherCohort.INELIGIBLE
        )
        statuses = [self._status_by_namekey[researcher.namekey] for researcher in eligible]
        return control_ui.UiSnapshot(
            counts=control_ui.DashboardCounts(
                total=len(self._researchers),
                ground_truth=sum(
                    researcher.cohort is control_ui.ResearcherCohort.GROUND_TRUTH
                    for researcher in self._researchers
                ),
                no_ground_truth=sum(
                    researcher.cohort is control_ui.ResearcherCohort.NO_GROUND_TRUTH
                    for researcher in self._researchers
                ),
                ineligible=sum(
                    researcher.cohort is control_ui.ResearcherCohort.INELIGIBLE
                    for researcher in self._researchers
                ),
                ready=statuses.count(control_ui.RunStatus.READY),
                queued=statuses.count(control_ui.RunStatus.QUEUED),
                running=statuses.count(control_ui.RunStatus.RUNNING),
                complete=statuses.count(control_ui.RunStatus.COMPLETE),
                failed=statuses.count(control_ui.RunStatus.FAILED),
                canceled=statuses.count(control_ui.RunStatus.CANCELED),
            ),
            rows=rows,
            backend_status=control_ui.BackendStatus.RUNNING,
            active_run_id=None,
        )

    def _project(
        self,
        *,
        researcher: control_ui.Researcher,
        variable: control_ui.VariableSpec,
    ) -> control_ui.ResearcherGridRow:
        status = self._status_by_namekey[researcher.namekey]
        run_id = self._run_id_by_namekey.get(researcher.namekey)
        attempts = tuple(
            self._attempt_projection(
                researcher=researcher,
                variable=variable,
                run_id=attempt_run_id,
                attempt_index=attempt_index,
            )
            for attempt_index, attempt_run_id in enumerate(
                self._attempt_run_ids_by_namekey[researcher.namekey]
            )
        )
        projection = (
            attempts[-1]
            if attempts
            else control_ui.AttemptVariableProjection(
                run_id=run_id,
                namekey=researcher.namekey,
                draw_number=researcher.draw_number,
                first_name=researcher.first_name,
                last_name=researcher.last_name,
                ai_column=variable.ai_column,
                ai_value=None,
                table_1_column=variable.table_1_column,
                table_1_value=None,
                footnotes=None,
                footnote_arguments=None,
                attempt_id=None,
                attempt_timestamp=None,
                attempt_status=status,
                action=control_ui.VariableProjector.action_for_status(
                    status,
                    eligible=(researcher.cohort is not control_ui.ResearcherCohort.INELIGIBLE),
                ),
            )
        )
        return control_ui.ResearcherGridRow(
            namekey=researcher.namekey,
            rnd=researcher.rnd,
            cohort=researcher.cohort,
            ineligibility_category=researcher.ineligibility_category,
            latest=projection,
            attempts=attempts,
        )

    def _attempt_projection(
        self,
        *,
        researcher: control_ui.Researcher,
        variable: control_ui.VariableSpec,
        run_id: UUID,
        attempt_index: int,
    ) -> control_ui.AttemptVariableProjection:
        status = self._status_by_run_id[run_id]
        ordinal = attempt_index + 1
        return control_ui.AttemptVariableProjection(
            run_id=run_id,
            namekey=researcher.namekey,
            draw_number=researcher.draw_number,
            first_name=researcher.first_name,
            last_name=researcher.last_name,
            ai_column=variable.ai_column,
            ai_value=f"ai-value-{ordinal}",
            table_1_column=variable.table_1_column,
            table_1_value=None,
            footnotes=f"footnote-{ordinal}",
            footnote_arguments=f"arguments-{ordinal}",
            attempt_id=control_ui.AttemptId(f"attempt-{ordinal}"),
            attempt_timestamp=(E2E_ATTEMPT_BASE_TIME + timedelta(seconds=attempt_index)),
            attempt_status=status,
            action=control_ui.VariableProjector.action_for_status(
                status,
                eligible=True,
            ),
        )

    def _matches(
        self,
        *,
        researcher: control_ui.Researcher,
        selection: control_ui.UiSelection,
    ) -> bool:
        status = self._status_by_namekey[researcher.namekey]
        search = selection.search_text.casefold().strip()
        return (
            (selection.status_filter is None or selection.status_filter is status)
            and (selection.cohort_filter is None or selection.cohort_filter is researcher.cohort)
            and (
                not search
                or search in researcher.first_name.casefold()
                or search in researcher.last_name.casefold()
                or search in researcher.draw_number.casefold()
                or search == str(researcher.rnd)
                or search in researcher.namekey.casefold()
            )
        )

    async def researcher_card(
        self,
        *,
        namekey: control_ui.Namekey,
    ) -> control_ui.ResearcherCardView:
        researcher = next(item for item in self._researchers if item.namekey == namekey)
        self._card_render_count[namekey] += 1
        render_count = self._card_render_count[namekey]
        return control_ui.ResearcherCardView(
            namekey=namekey,
            draw_number=researcher.draw_number,
            first_name=researcher.first_name,
            last_name=researcher.last_name,
            markdown=(
                f"#### {KTP_FILENAME_COL}: `{E2E_CARD_FILENAME}`\n\n"
                f"render-count-{render_count}\n\n"
                f"**`{E2E_CARD_FIELD_LABEL}`**: {E2E_CARD_FIELD_VALUE}\n\n"
                f"**`{E2E_CARD_SECOND_FIELD_LABEL}`**: "
                f"{E2E_CARD_SECOND_FIELD_VALUE}\n\n"
                f"{E2E_LONG_CARD_TOKEN}"
            ),
        )

    async def queue(self, *, namekey: control_ui.Namekey) -> UUID:
        researcher = next(item for item in self._researchers if item.namekey == namekey)
        if researcher.cohort is control_ui.ResearcherCohort.INELIGIBLE:
            raise ValueError("ineligible namekeys cannot be queued")
        run_id = uuid4()
        self._run_id_by_namekey[namekey] = run_id
        self._attempt_run_ids_by_namekey[namekey].append(run_id)
        self._status_by_run_id[run_id] = control_ui.RunStatus.QUEUED
        self._status_by_namekey[namekey] = control_ui.RunStatus.QUEUED
        return run_id

    async def rerun(self, *, namekey: control_ui.Namekey) -> UUID:
        return await self.queue(namekey=namekey)

    async def cancel(self, *, run_id: UUID) -> None:
        namekey = next(
            source
            for source, candidate in self._run_id_by_namekey.items()
            if candidate == run_id
        )
        self._status_by_run_id[run_id] = control_ui.RunStatus.CANCELED
        self._status_by_namekey[namekey] = control_ui.RunStatus.CANCELED


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
        control_ui.ApplicationServices,
        SimpleNamespace(controller=controller),
    )
    control_ui.configure_application_lifecycle()
    control_ui.ui.run(
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
            time.sleep(control_ui.BACKEND_READY_POLL_SECONDS)
    raise TimeoutError("Control Centre E2E server did not start")


def grid_row_for_draw(page: Page, draw: str):
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
def control_centre_browser() -> Iterator[tuple[Page, list[str]]]:
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
        cwd=REPOSITORY_ROOT,
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


def test_underscore_field_labels_render_literally_in_researcher_card() -> None:
    with control_centre_browser() as (page, errors):
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


def test_main_grid_and_researcher_card_use_compact_line_spacing() -> None:
    with control_centre_browser() as (page, errors):
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


def test_selected_researcher_row_is_highlighted() -> None:
    with control_centre_browser() as (page, errors):
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


def test_researcher_selection_and_attempt_history_are_idempotent() -> None:
    with control_centre_browser() as (page, errors):
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


def test_control_centre_browser_contract() -> None:
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
        cwd=REPOSITORY_ROOT,
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

            summary = page.get_by_test_id(control_ui.PAGE_SUMMARY_TEST_ID)
            expect(summary).to_contain_text(f"Total {control_ui.EXPECTED_SOURCE_RESEARCHERS}")
            expect(summary).to_contain_text(
                f"ineligible {control_ui.EXPECTED_INELIGIBLE_RESEARCHERS}"
            )
            grid = page.get_by_test_id(control_ui.RESEARCHER_GRID_TEST_ID)
            expect(grid.locator('[role="grid"]')).to_have_attribute(
                "aria-rowcount",
                str(EXPECTED_GRID_ARIA_ROW_COUNT),
            )
            headers = grid.locator(GRID_HEADER_SELECTOR)
            expect(headers.nth(0)).to_contain_text(control_ui.GRID_RND_FIELD)
            expect(headers.nth(1)).to_contain_text(control_ui.DRAW_LABEL)
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
            assert footer.inner_text().strip() == ""
            ineligible_row = grid_row_for_draw(page, "pilot.1")
            ineligible_row.click()
            action_button = page.get_by_test_id(control_ui.EXECUTE_ACTION_TEST_ID)
            expect(action_button).to_be_disabled()
            expect(action_button).to_have_text(
                re.compile(
                    control_ui.ACTION_LABEL_BY_VALUE[control_ui.RunAction.DISABLED.value],
                    re.IGNORECASE,
                )
            )
            assert action_button.evaluate("element => element.tagName") == "BUTTON"

            eligible_row = grid_row_for_draw(page, "pilot.2")
            eligible_row.click()
            expect(action_button).to_be_enabled()
            expect(action_button).to_have_text(
                re.compile(
                    control_ui.ACTION_LABEL_BY_VALUE[control_ui.RunAction.QUEUE.value],
                    re.IGNORECASE,
                )
            )
            view_card_button = page.get_by_test_id(control_ui.VIEW_CARD_TEST_ID)
            expect(view_card_button).to_be_enabled()
            assert footer.inner_text().strip() == ""
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
            search_input = page.get_by_label(control_ui.Locale.SEARCH_FILTER)
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
                    control_ui.ACTION_LABEL_BY_VALUE[control_ui.RunAction.CANCEL.value],
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
            expect(history_rows.nth(0)).to_contain_text(control_ui.RunStatus.QUEUED.value)

            action_button.click()
            expect(action_button).to_have_text(
                re.compile(
                    control_ui.ACTION_LABEL_BY_VALUE[control_ui.RunAction.RERUN.value],
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
