import pytest

from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models import (  # noqa: E501
    post_commit_validation,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.post_commit_validation import (  # noqa: E501
    _apply_retry_obligations,
    _EvidenceAssessment,
    _EvidenceItemAssessment,
    _EvidenceObligation,
    _EvidenceSubmissionColumn,
    _FieldPin,
    _FieldPinState,
    _StandardizedPin,
    _transition_field,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.pydantic_to_paste import (  # noqa: E501
    EvidenceWithdrawal,
    FieldSubmission,
    GenderSubmission,
    WebSearchExcerpt,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.submission_fixture import (  # noqa: E501
    L_FEI_FEI_RETRY_FIXTURE,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    EVIDENCE_OUTCOME_UNMATCHED,
    EVIDENCE_OUTCOME_V1_EXACT,
    EVIDENCE_OUTCOME_WITHDRAWN,
)


def _assessment(field: str, evidence: FieldSubmission) -> _EvidenceAssessment:
    return _EvidenceAssessment(items=tuple(
        _EvidenceItemAssessment(
            field=field,
            index=index,
            evidence_number=index + 1,
            submission=item,
            outcome=(
                EVIDENCE_OUTCOME_WITHDRAWN
                if isinstance(item, EvidenceWithdrawal)
                else EVIDENCE_OUTCOME_V1_EXACT
            ),
            match=None,
        )
        for index, item in enumerate(evidence.web_search_excerpts)
    ))


def test_invalid_initial_withdrawal_does_not_release_exact_item() -> None:
    column = _EvidenceSubmissionColumn.EDUCATION
    exact = WebSearchExcerpt(excerpt="verified", url="https://example.com/verified")
    withdrawal = EvidenceWithdrawal(
        action="withdraw_unverified_evidence",
        reason="not_present_in_web_results",
        attested=True,
    )
    initial = FieldSubmission(value="initial", web_search_excerpts=[exact, withdrawal])
    obligations, violations, _ = _apply_retry_obligations(
        column, initial, _assessment(column.value, initial), _FieldPinState(),
    )
    assert len(violations) == 1
    assert obligations[0].outcome == EVIDENCE_OUTCOME_V1_EXACT
    assert obligations[1].outcome == EVIDENCE_OUTCOME_UNMATCHED

    changed = FieldSubmission(
        value="changed",
        web_search_excerpts=[
            WebSearchExcerpt(excerpt="tampered", url="https://example.com/verified"),
            WebSearchExcerpt(excerpt="corrected", url="https://example.com/corrected"),
        ],
    )
    _, retry_violations, _ = _apply_retry_obligations(
        column,
        changed,
        _assessment(column.value, changed),
        _FieldPinState(
            pins=_FieldPin.NARRATIVE,
            narrative_value=initial.value,
            evidence_obligations=obligations,
        ),
    )
    assert any("web_search_excerpts[0]" in item.message for item in retry_violations)


def test_standardized_pin_round_trips_without_provider_revalidation() -> None:
    education = L_FEI_FEI_RETRY_FIXTURE.submission.education.standardized_value
    state = _FieldPinState(
        pins=_FieldPin.STANDARDIZED,
        standardized_value=_StandardizedPin.from_value(education),
    )
    restored = _FieldPinState.model_validate_json(state.model_dump_json())
    assert restored.standardized_value == state.standardized_value


def test_withdrawal_without_narrative_change_does_not_become_immutable() -> None:
    column = _EvidenceSubmissionColumn.GENDER
    unmatched = WebSearchExcerpt(excerpt="unmatched", url="https://example.com")
    previous = _FieldPinState(
        pins=_FieldPin.NARRATIVE | _FieldPin.STANDARDIZED,
        narrative_value="old",
        evidence_obligations=(
            _EvidenceObligation(outcome=EVIDENCE_OUTCOME_UNMATCHED, submission=unmatched),
        ),
        standardized_value=_StandardizedPin.from_value("NR"),
    )
    withdrawal = EvidenceWithdrawal(
        action="withdraw_unverified_evidence",
        reason="not_present_in_web_results",
        attested=True,
    )
    submission = FieldSubmission(value="old", web_search_excerpts=[withdrawal])
    obligations, violations, changed = _apply_retry_obligations(
        column, submission, _assessment(column.value, submission), previous,
    )
    assert len(violations) == 1
    assert obligations == previous.evidence_obligations
    assert changed is False


def test_pinned_age_is_not_checked_against_a_later_push(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    field = L_FEI_FEI_RETRY_FIXTURE.submission.age_first_publication
    previous = _FieldPinState(
        pins=_FieldPin.NARRATIVE | _FieldPin.EVIDENCE | _FieldPin.STANDARDIZED,
        narrative_value=field.value,
        evidence_obligations=tuple(
            _EvidenceObligation(outcome=EVIDENCE_OUTCOME_V1_EXACT, submission=item)
            for item in field.web_search_excerpts
        ),
        standardized_value=_StandardizedPin.from_value(field.standardized_value),
    )

    def fail_if_checked(*_args: object, **_kwargs: object) -> bool:
        raise AssertionError("a pinned age must not be rechecked")

    monkeypatch.setattr(post_commit_validation, "_age_evidence_check_failed", fail_if_checked)
    audit = _transition_field(
        _EvidenceSubmissionColumn.AGE_FIRST_PUBLICATION,
        field,
        field,
        previous,
        assessment=_assessment(_EvidenceSubmissionColumn.AGE_FIRST_PUBLICATION.value, field),
        push_response_record=object(),  # type: ignore[arg-type]
    )
    assert not audit.violations
    assert audit.state == previous


def test_valid_evidence_edit_releases_narrative_and_standardized_despite_other_violation() -> None:
    column = _EvidenceSubmissionColumn.GENDER
    exact = WebSearchExcerpt(excerpt="exact", url="https://example.com/exact")
    unmatched = WebSearchExcerpt(excerpt="unmatched", url="https://example.com/other")
    corrected = WebSearchExcerpt(excerpt="corrected", url="https://example.com/other")
    previous = _FieldPinState(
        pins=_FieldPin.NARRATIVE | _FieldPin.STANDARDIZED,
        narrative_value="old",
        evidence_obligations=(
            _EvidenceObligation(outcome=EVIDENCE_OUTCOME_V1_EXACT, submission=exact),
            _EvidenceObligation(outcome=EVIDENCE_OUTCOME_UNMATCHED, submission=unmatched),
        ),
        standardized_value=_StandardizedPin.from_value("NR"),
    )
    changed = GenderSubmission(
        value="new",
        web_search_excerpts=[
            WebSearchExcerpt(excerpt="tampered", url="https://example.com/exact"),
            corrected,
        ],
        standardized_value="NR",
    )
    rejected = _transition_field(
        column, changed, changed, previous,
        assessment=_assessment(column.value, changed),
        push_response_record=object(),  # type: ignore[arg-type]
    )
    assert rejected.violations
    assert rejected.state.narrative_value == "new"
    assert rejected.state.evidence_obligations[0].submission == exact
    assert rejected.state.evidence_obligations[1].submission == corrected

    restored = GenderSubmission(
        value="new", web_search_excerpts=[exact, corrected], standardized_value="NR",
    )
    accepted = _transition_field(
        column, restored, restored, rejected.state,
        assessment=_assessment(column.value, restored),
        push_response_record=object(),  # type: ignore[arg-type]
    )
    assert not accepted.violations
    assert accepted.state.pins == (
        _FieldPin.NARRATIVE | _FieldPin.EVIDENCE | _FieldPin.STANDARDIZED
    )
