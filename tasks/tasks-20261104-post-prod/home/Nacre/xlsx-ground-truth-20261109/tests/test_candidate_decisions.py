"""Check that per-row identity decisions, not name spelling, govern mask ownership.

Allowed dependencies: stdlib and the local shared module only.
"""

import hashlib
import io
import json
import unittest
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import shared

WORKDIR = Path(__file__).resolve().parents[1]
TEST_ROOT = WORKDIR / "out/test_candidate_decisions"
SOURCE = TEST_ROOT / "source.jsonl"
MASTER = TEST_ROOT / "master.jsonl"
SEED_REF = ("2024_HCR.xlsx", 1)
CANDIDATE_REF = ("2023_HCR.xlsx", 2)


@dataclass(frozen=True)
class Handoff:
    source_sha256: str
    assignee: str = "Pavel"
    source_file: str = "source.jsonl"
    master_file: str = "master.jsonl"

    def artifact(self, name: str) -> Path:
        return {self.source_file: SOURCE, self.master_file: MASTER}[name]


def award_row(reference: tuple[str, int], first: str) -> dict[str, str]:
    row = dict.fromkeys(shared.REVIEW_SOURCE_COLUMNS, "")
    row.update({
        shared.KTP_FILENAME_COL: reference[0],
        shared.KTP_FRAGMENT_COL: str(reference[1]),
        shared.KTP_FIRST_NAME_COL: first,
        shared.KTP_LAST_NAME_COL: "Lee",
    })
    return row


def innerdict(reference: tuple[str, int]) -> dict[str, object]:
    return {
        shared.KTP_FILENAME_COL: reference[0],
        shared.KTP_FRAGMENT_COL: {"type": "excel_row", "excel_row": reference[1]},
    }


def namekey(first: str) -> str:
    return json.dumps(
        {shared.KTP_FIRST_NAME_COL: first, shared.KTP_LAST_NAME_COL: "Lee"},
        sort_keys=True,
    )


class CandidateDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        TEST_ROOT.mkdir(parents=True, exist_ok=True)

    def run_selection(self, *, candidate_first: str, accepted: bool) -> list[dict]:
        seed = award_row(SEED_REF, "Alex")
        candidate = award_row(CANDIDATE_REF, candidate_first)
        SOURCE.write_text(
            "".join(json.dumps(row) + "\n" for row in (seed, candidate)),
            encoding=shared.TEXT_ENCODING,
        )
        MASTER.write_text(
            "".join(
                json.dumps(entry) + "\n"
                for entry in (
                    {namekey("Alex"): [innerdict(SEED_REF)]},
                    {
                        namekey(candidate_first): (
                            [innerdict(CANDIDATE_REF)] if candidate_first != "Alex" else []
                        )
                    },
                )
            ),
            encoding=shared.TEXT_ENCODING,
        )
        review = shared.HcrAwardReview(
            draw="pilot.1",
            namekey=("Alex", "Lee"),
            first_award=SEED_REF,
            script_path=shared.hcr_review_script_name("pilot.1", "Alex", "Lee"),
        )
        review._audit_rows = [seed, candidate]
        selected = {SEED_REF, CANDIDATE_REF} if accepted else {SEED_REF}
        handoff = Handoff(hashlib.sha256(SOURCE.read_bytes()).hexdigest())
        with patch.object(shared, "_seed_handoff", return_value=handoff):
            with redirect_stdout(io.StringIO()):
                review.assign_awards_to_first_draw(selected_award_refs=selected)
        return [json.loads(line) for line in MASTER.read_text().splitlines()]

    def test_reject_keeps_different_namekey_owner(self) -> None:
        entries = self.run_selection(candidate_first="A.", accepted=False)
        self.assertEqual(entries[0][namekey("Alex")], [innerdict(SEED_REF)])
        self.assertEqual(entries[1][namekey("A.")], [innerdict(CANDIDATE_REF)])

    def test_accept_moves_candidate_to_seed(self) -> None:
        entries = self.run_selection(candidate_first="A.", accepted=True)
        self.assertEqual(
            entries[0][namekey("Alex")], [innerdict(SEED_REF), innerdict(CANDIDATE_REF)]
        )
        self.assertEqual(entries[1][namekey("A.")], [])

    def test_reject_same_namekey_without_owner_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "Rejected HCR awards have no remaining"):
            self.run_selection(candidate_first="Alex", accepted=False)
        entries = [json.loads(line) for line in MASTER.read_text().splitlines()]
        self.assertEqual(entries[0][namekey("Alex")], [innerdict(SEED_REF)])


if __name__ == "__main__":
    unittest.main()
