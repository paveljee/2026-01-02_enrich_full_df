from __future__ import annotations

from http import HTTPStatus
from uuid import uuid7

import pytest

from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import (
    Locale as BackendLocale,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    HTTP_CONTENT_TYPE_HEADER,
    HTTP_GET_METHOD,
    PULL_PATH,
    ContentType,
)
from src.detours.detour_ai_augment.protected.src.control_centre.dashboard.helpers.locale import (  # noqa: E501
    Locale as DashboardLocale,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_backend_store import (  # noqa: E501
    AiAugmentBackendStore,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_context import (  # noqa: E501
    AiAugmentBackendContext,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.lifecycle import (
    BackendLifecycle,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.pull_event import (
    PullResponseRecord,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard import ui as control_ui
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.lifecycle import (  # noqa: E501
    RunLifecycle,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.run_event import (  # noqa: E501
    RunEvent,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.run_outcome_event import (  # noqa: E501
    RunOutcomePath,
    RunOutcomeResponseRecord,
)
from src.detours.detour_ai_augment.tests.backend import test_http_interceptor as store_tests
from src.detours.detour_ai_augment.tests.backend.test_api import (
    persisted_http_record,
    valid_submission_body,
)
from src.detours.detour_ai_augment.tests.control_centre import test_ui as dashboard_tests

backend_test_paths = store_tests.backend_test_paths
runtime = store_tests.runtime
backend_store = store_tests.backend_store


def test_one_session_accepts_retry_attempts_but_rejects_multiple_run_outcomes(
    backend_store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
) -> None:
    """Cover a same-session case lost with a stale, refactored
    two-accepted-commits fixture. A real Store retry creates
    two validation requests but one queryable completed outcome,
    linked to its Run by the final attempt ID. A second Run
    claiming that session, after a rejected outcome is logged,
    must fail the dashboard's duplicate-session check.
    """
    store = backend_store
    payload = valid_submission_body()
    with store._writable(runtime):
        first = store._validate_commit(store_tests.commit(store, {}, payload))
        assert (
            first.validation_request_body.post_commit_validation.result
            is BackendLifecycle.REJECTED
        )
        retry_pull = store._append_authoritative_record(
            persisted_http_record(
                record_id=uuid7(),
                method=HTTP_GET_METHOD,
                path=PULL_PATH,
                response_code=HTTPStatus.OK,
                response_headers={HTTP_CONTENT_TYPE_HEADER: ContentType.MARKDOWN_UTF8},
                response_body=(
                    first.validation_request_body.post_commit_validation.detail
                    or BackendLocale.VALIDATION_ERROR_DETAIL
                ).rstrip() + "\n",
            )
        )
        assert isinstance(retry_pull, PullResponseRecord)
        assert retry_pull.validation_request_record is first
        final = store._validate_commit(
            store_tests.commit(store, payload, payload, retry_pull)
        )
        assert (
            final.validation_request_body.post_commit_validation.result
            is BackendLifecycle.ACCEPTED
        )
        commit_request_record = final.validation_request_body.commit_request_record
        outcome = store_tests.outcome_for_commit(store, commit_request_record)
        assert outcome.response_code == HTTPStatus.OK
        store._append_authoritative_record(outcome)
        snapshot = store_tests.query_snapshot(store)
        source = snapshot.ai_augment_singular_outerdicts[0]
        assert len(source.codex_innerdicts) == 1
        query_outcome = source.codex_innerdicts[0].run_outcome_response_record
        query_attempt = query_outcome.attempt
        assert query_attempt is not None
        prior_pull = (
            query_attempt.validation_request_body.commit_request_record
            .commit_request_body.pull_response_record
        )
        prior_attempt = prior_pull.validation_request_record
        assert prior_attempt is not None
        assert prior_attempt.record_id == first.record_id
        assert query_attempt.record_id == final.record_id
        assert prior_attempt.record_id != query_attempt.record_id

        session_id = query_outcome.run_outcome_request_record.session_id
        assert session_id is not None
        completed_run = dashboard_tests.queued_run(namekey=source.namekey)
        completed_run.session_id = session_id
        completed_run.completed_attempt_id = query_attempt.record_id
        completed_run.run_outcome_response_record = query_outcome
        completed_run = control_ui.apply_run_event(completed_run, RunEvent(
            run_id=completed_run.run_id,
            occurred_at_unix_usec=RunEvent.datetime_to_unix_usec(
                dashboard_tests.SESSION_TIMESTAMP
            ),
            lifecycle=RunLifecycle.COMPLETED,
        ))
        view = control_ui._ResearcherView.from_snapshot(
            source, snapshot, (completed_run,)
        )
        assert len(view.run_attempt_views) == 1
        assert view.run_attempt_views[0].run is completed_run
        assert view.run_attempt_views[0].attempt is query_attempt

        second_outcome = store_tests.outcome_for_commit(
            store, commit_request_record, path=RunOutcomePath.FAILED,
        )
        assert second_outcome.response_code == HTTPStatus.CONFLICT
        persisted_second_outcome = store._append_authoritative_record(second_outcome)
        assert isinstance(persisted_second_outcome, RunOutcomeResponseRecord)
        second_run = dashboard_tests.queued_run(namekey=source.namekey)
        second_run.session_id = session_id
        second_run.run_outcome_response_record = persisted_second_outcome
        second_run = control_ui.apply_run_event(second_run, RunEvent(
            run_id=second_run.run_id,
            occurred_at_unix_usec=RunEvent.datetime_to_unix_usec(
                dashboard_tests.SESSION_TIMESTAMP
            ),
            lifecycle=RunLifecycle.FAILED,
        ))
        with pytest.raises(
            RuntimeError, match=DashboardLocale.RUN_OUTCOME_SESSION_DUPLICATE,
        ):
            control_ui._ResearcherView.from_snapshot(
                source, snapshot, (completed_run, second_run)
            )
