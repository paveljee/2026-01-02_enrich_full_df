"""Render reviewed XLSX match failures from the designated DB, read-only."""

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import duckdb

from src.helpers.data_models import NameKey
from src.helpers.schema import (
    CARD_PARTITION_TABLE,
    POPULATION_TABLE,
    SAMPLES_WITH_NAMES_VIEW,
    XLSX_INNERDICT_TABLE,
)
from src.helpers.vars import (
    DRAW_LABEL,
    HCR_CATEGORY_COL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_HCR_FILENAME_COL,
    KTP_HCR_ROW_NUMBER_COL,
    KTP_INNERDICT_JSONLINES_COL,
    KTP_LAST_NAME_COL,
    KTP_NAMEKEY_COL,
    KTP_PARTITION_FLAG_SSN_COUNT_COL,
    KTP_PARTITION_FLAG_XLSX_ANY_COL,
    KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL,
    KTP_XLSX_MATCH_COL,
    KTP_XLSX_MATCH_RULE_KEY,
)

DB_PATH = Path("data/scisci_process.duckdb")
AwardID = tuple[str, int]


@dataclass(frozen=True)
class Case:
    label: str
    mode: int
    kind: str
    first: str
    last: str
    targets: tuple[AwardID, ...]
    comparators: tuple[AwardID, ...]
    argument: str

    @property
    def namekey(self) -> str:
        return NameKey(first_name=self.first, last_name=self.last).to_json_key()


CASES = (
    Case(
        "Younan Xia / Princeton initial", 3, "false inclusion", "Younan", "Xia",
        (("2018_HCR.xlsx", 5352),), (("2018_HCR.xlsx", 5353),),
        "The 2018 Physics sheet separately lists `Y. Xia` at Princeton (row 5352) "
        "and full-name `Younan Xia` at Georgia Tech (adjacent row 5353). The "
        "sampled Younan key is from Georgia Tech. V2 admitted the Princeton "
        "initial-only row, which mode 3 then accepts without identity review.",
    ),
    Case(
        "Yupeng Zhang / NTU initial", 3, "false inclusion", "Yupeng", "Zhang",
        (("2023_HCR.xlsx", 4438),),
        (("2021_HCR.xlsx", 3889), ("2022_HCR.xlsx", 4410),
         ("2023_HCR.xlsx", 4453)),
        "The 2023 Cross-Field sheet has `Y. Zhang` at Nanyang Technological "
        "University, Singapore (row 4438), and full-name `Yupeng Zhang` at "
        "Shenzhen University (row 4453, the sampled origin). Earlier full-name "
        "Yupeng rows also use Shenzhen. V2's initial alternative includes the "
        "NTU row despite no affiliation link; mode 3 accepts it.",
    ),
    Case(
        "Jian Zhang / three 2022 identities", 3, "false inclusion", "Jian", "Zhang",
        (("2022_HCR.xlsx", 4353), ("2022_HCR.xlsx", 4355)),
        (("2022_HCR.xlsx", 4354),),
        "The 2022 Cross-Field sheet lists three consecutive `Jian Zhang` award "
        "rows at the Chinese Academy of Sciences, Dresden University of "
        "Technology, and Central South University. The Dresden row is the sampled "
        "origin; none of the three lists a secondary affiliation. Treating both "
        "other same-year entries as that Dresden individual is highly likely "
        "conflation. V2 matches the identical names and mode 3 auto-accepts them.",
    ),
    Case(
        "Goekhan/Gokhan Hotamisligil", 3, "false exclusion", "Gokhan S.",
        "Hotamisligil", (("2018_HCR.xlsx", 2012),),
        (("2019_HCR.xlsx", 2059),),
        "The omitted 2018 `Goekhan S. Hotamisligil` and matched 2019–22 "
        "`Gokhan S. Hotamisligil` rows share Cross-Field and Harvard. The `oe`/`o` "
        "transliteration changes the first-name token; neither XLSX rule joins "
        "this otherwise continuous award record.",
    ),
    Case(
        "Michael Boehm/Bohm", 3, "false exclusion", "Michael", "Bohm",
        (("2016_HCR.xlsx", 584), ("2017_HCR.xlsx", 614), ("2018_HCR.xlsx", 710)),
        (("2015_HCR.xlsx", 593), ("2019_HCR.xlsx", 627),
         ("2022_HCR.xlsx", 722)),
        "Three `Michael Boehm` rows sit between matched `Michael Bohm`/`Böhm` "
        "rows. All are Clinical Medicine at Saarland's university clinic. The "
        "`oe` versus `o`/`ö` surname transliteration prevents both v2 and v1 "
        "surname matching, omitting the middle years.",
    ),
    Case(
        "Rasmus Nielsen/Nielsenlo", 4, "false exclusion", "Rasmus", "Nielsenlo",
        (("2014_HCR.xlsx", 2170), ("2017_HCR.xlsx", 2315),
         ("2018_HCR.xlsx", 2496), ("2019_HCR.xlsx", 4930)),
        (("2020_HCR.xlsx", 2688), ("2022_HCR.xlsx", 3143)),
        "The 2014–19 `Rasmus Nielsen` rows and matched 2020–22 `Rasmus "
        "Nielsenlo` rows share UC Berkeley; older rows also list Copenhagen. "
        "The extra `lo` in the later raw surname blocks both XLSX rules from "
        "including the earlier award rows.",
    ),
    Case(
        "Andrew P versus Andrew D Morris", 4, "false inclusion", "Andrew P",
        "Morris", (("2017_HCR.xlsx", 2308), ("2018_HCR.xlsx", 4695)),
        (("2017_HCR.xlsx", 2309), ("2018_HCR.xlsx", 4696)),
        "Both 2017 and 2018 list `Andrew D Morris` at Edinburgh separately from "
        "`Andrew P Morris` at Liverpool. The sampled key is Andrew P. V1 ignores "
        "the middle initial because it checks only first token `andrew` and "
        "surname `morris`, wrongly adding the Andrew D rows.",
    ),
    Case(
        "Paul G versus Paul M Richardson", 4, "false inclusion", "Paul G",
        "Richardson", (("2014_HCR.xlsx", 2024),), (("2014_HCR.xlsx", 806),),
        "The 2014 sheet separately lists Paul G Richardson in Clinical Medicine "
        "at Dana-Farber and Paul M Richardson in Microbiology at Joint Genome "
        "Institute. The sampled key follows the Dana-Farber clinical track. V1 "
        "ignores `G` versus `M` and attaches the microbiology row.",
    ),
    Case(
        "Simon White versus Simon D. M. White", 4, "false inclusion", "Simon ",
        "White", (("2014_HCR.xlsx", 3211), ("2015_HCR.xlsx", 3121),
                  ("2016_HCR.xlsx", 3261), ("2017_HCR.xlsx", 3535),
                  ("2018_HCR.xlsx", 6076), ("2019_HCR.xlsx", 6213),
                  ("2020_HCR.xlsx", 6387), ("2021_HCR.xlsx", 6601),
                  ("2022_HCR.xlsx", 6950), ("2023_HCR.xlsx", 7128),
                  ("2024_HCR.xlsx", 6887)),
        (("2014_HCR.xlsx", 303), ("2017_HCR.xlsx", 357)),
        "The source `Simon White` has a Baylor College of Medicine biology "
        "track, including sampled 2017 row 357. A separate `Simon D. M. White` "
        "has a Max Planck space-science track, simultaneously listed in "
        "2014–17 and continuing through 2024. V1's first-token/surname test "
        "conflates the entire Max Planck track with the Baylor key.",
    ),
    Case(
        "Luis versus Jose Luis Martinez", 4, "false inclusion", "Luis", "Martinez",
        (("2023_HCR.xlsx", 3000), ("2024_HCR.xlsx", 5421)),
        (("2023_HCR.xlsx", 3001), ("2024_HCR.xlsx", 2839)),
        "In both 2023 and 2024, `Jose Luis Martinez` appears at CSIC separately "
        "from `Luis Martinez` at Universidad de Jaen; the latter is the source "
        "key's continuing affiliation. V1 finds `luis` among the former's "
        "first-name tokens and adds the CSIC rows to the Jaen key.",
    ),
    Case(
        "Qiao Zhang / Tsing Hua initial", 4, "false inclusion", "Qiao", "Zhang",
        (("2018_HCR.xlsx", 3954),), (("2018_HCR.xlsx", 3235),),
        "The 2018 sheet separately lists full-name `Qiao Zhang` in Cross-Field "
        "at Suzhou University and `Q. Zhang` in Geosciences at Tsing Hua "
        "University. The source key is full-name Qiao, with no listed Tsing Hua "
        "affiliation. V2's initial alternative absorbs the Tsing Hua row despite "
        "the parallel full-name entry.",
    ),
    Case(
        "Qian Chen / Suzhou versus NUST", 4, "false inclusion", "Qian", "Chen",
        (("2022_HCR.xlsx", 1675), ("2024_HCR.xlsx", 1474)),
        (("2022_HCR.xlsx", 1674), ("2023_HCR.xlsx", 1649)),
        "The sampled key tracks Suzhou/Soochow University. The 2022 sheet "
        "separately lists same-name Cross-Field rows at Suzhou and Nanjing "
        "University of Science & Technology; the latter reappears in 2024 "
        "while Suzhou reappears in 2023. V2 exact-name matching conflates the "
        "parallel institutional tracks.",
    ),
    Case(
        "Jun Wang / Macau versus unrelated tracks", 4, "false inclusion", "Jun", "Wang",
        (("2019_HCR.xlsx", 3324), ("2022_HCR.xlsx", 4919),
         ("2023_HCR.xlsx", 4742), ("2024_HCR.xlsx", 4548),
         ("2022_HCR.xlsx", 4007), ("2023_HCR.xlsx", 4899),
         ("2024_HCR.xlsx", 4699), ("2022_HCR.xlsx", 4006),
         ("2023_HCR.xlsx", 4027)),
        (("2018_HCR.xlsx", 395), ("2023_HCR.xlsx", 375),
         ("2024_HCR.xlsx", 5483)),
        "The sampled Jun Wang follows Macau University of Science & Technology "
        "biology/microbiology with iCarbonX secondary affiliation through 2024. "
        "The same years separately list Jun Wang engineering at City University "
        "of Hong Kong, environment/ecology at South China Agricultural "
        "University, and Cross-Field at South China University of Technology. "
        "Those stable parallel tracks have no shared listed affiliation with "
        "the Macau rows; exact-name v2 matching absorbs them all.",
    ),
    Case(
        "Peng Wang / three 2023 entries", 4, "false inclusion", "Peng", "Wang",
        (("2023_HCR.xlsx", 4034), ("2023_HCR.xlsx", 4036)),
        (("2023_HCR.xlsx", 4035),),
        "The 2023 Cross-Field sheet has three consecutive Peng Wang rows at "
        "KAUST, Nanjing Agricultural University (the sampled origin), and "
        "Warwick, with no secondary affiliations. Treating the KAUST and "
        "Warwick entries as the Nanjing researcher is highly likely same-name "
        "conflation under v2.",
    ),
    Case(
        "Yu Wang / CAS versus other fields", 4, "false inclusion", "Yu", "Wang",
        (("2023_HCR.xlsx", 4073), ("2024_HCR.xlsx", 3888)),
        (("2023_HCR.xlsx", 585), ("2024_HCR.xlsx", 511)),
        "The sampled Yu Wang is on the Chinese Academy of Sciences chemistry "
        "track in 2022–24. Same-year matches add Cross-Field rows at Nanjing "
        "Normal University (2023) and Xi'an Jiaotong University with City "
        "University of Hong Kong secondary affiliation (2024), neither linked "
        "to the CAS chemistry entry. V2 uses identical name tokens alone.",
    ),
)


def _identity(row: dict[str, object]) -> AwardID:
    return str(row[KTP_HCR_FILENAME_COL]), int(str(row[KTP_HCR_ROW_NUMBER_COL]))


def _raw_name(row: dict[str, object]) -> str:
    first = next((str(row[col]) for col in (
        "hcr.firstname_middlename", "hcr.first_name", "hcr.firstname"
    ) if row.get(col)), "")
    last = next((str(row[col]) for col in ("hcr.lastname", "hcr.last_name") if row.get(col)), "")
    return " ".join(part.strip() for part in (first, last) if part)


def _raw_affiliation(row: dict[str, object]) -> str:
    return next((str(row[col]) for col in (
        "hcr.full_primary_affiliation", "hcr.primary_affiliation", "hcr.primaryaffiliation"
    ) if row.get(col)), "")


def _raw_secondary_affiliation(row: dict[str, object]) -> str:
    return next((str(row[col]) for col in (
        "hcr.full_secondary_affiliation", "hcr.secondary_affiliation",
        "hcr.secondary_affiliations", "hcr.secondaryaffiliation",
    ) if row.get(col)), "")


def render() -> str:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        con.execute("SET threads = 1")
        con.execute("SET memory_limit = '128MB'")
        case_keys = [case.namekey for case in CASES]
        partition_rows = con.execute(
            f'SELECT "{KTP_NAMEKEY_COL}", "{KTP_PARTITION_FLAG_SSN_COUNT_COL}", '
            f'"{KTP_PARTITION_FLAG_XLSX_ANY_COL}", '
            f'"{KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL}" '
            f'FROM {CARD_PARTITION_TABLE} WHERE list_contains(?, "{KTP_NAMEKEY_COL}")',
            [case_keys],
        ).fetchall()
        flags = {row[0]: row[1:] for row in partition_rows}
        edges: dict[str, dict[AwardID, dict[str, object]]] = defaultdict(dict)
        for key, blob in con.execute(
            f'SELECT "{KTP_NAMEKEY_COL}", "{KTP_INNERDICT_JSONLINES_COL}" '
            f'FROM {XLSX_INNERDICT_TABLE} WHERE list_contains(?, "{KTP_NAMEKEY_COL}")',
            [case_keys],
        ).fetchall():
            for line in blob.splitlines():
                if line.strip():
                    inner = json.loads(line)
                    edges[key][(inner[KTP_FILENAME_COL], int(inner[KTP_FRAGMENT_COL]))] = inner
        origins: dict[str, list[tuple[AwardID, str]]] = defaultdict(list)
        for first, last, filename, fragment, draw in con.execute(
            f'SELECT "{KTP_FIRST_NAME_COL}", "{KTP_LAST_NAME_COL}", '
            f'"{KTP_FILENAME_COL}", "{KTP_FRAGMENT_COL}", "{DRAW_LABEL}" '
            f'FROM {SAMPLES_WITH_NAMES_VIEW}'
        ).fetchall():
            if first is not None and last is not None and first and last:
                key = NameKey(first_name=first, last_name=last).to_json_key()
                if key in case_keys:
                    origins[key].append(((filename, int(fragment)), str(draw)))

        wanted = {
            identity
            for case in CASES
            for identity in (*case.targets, *case.comparators,
                             *(identity for identity, _ in origins[case.namekey]))
        }
        wanted_ids = [f"{filename}#{fragment}" for filename, fragment in sorted(wanted)]
        cursor = con.execute(
            f'SELECT p.* FROM {POPULATION_TABLE} p WHERE list_contains(?, '
            f'p."{KTP_HCR_FILENAME_COL}" || \'#\' || '
            f'CAST(p."{KTP_HCR_ROW_NUMBER_COL}" AS VARCHAR))',
            [wanted_ids],
        )
        columns = [col[0] for col in cursor.description]
        raw = {
            _identity(record): record
            for record in (dict(zip(columns, row, strict=True)) for row in cursor.fetchall())
        }
    finally:
        con.close()

    assert len(raw) == len(wanted), (len(raw), len(wanted))
    lines = [
        "# Mode 3/4 XLSX matching failures",
        "",
        f"Generated by `{Path(__file__).name}` from the designated DuckDB file in read-only mode.",
        "The complete raw records below are from the Step 2 `population` table; "
        "XLSX match edges and rule payloads are from persisted `xlsx_innerdicts`.",
        "Every submitted identity is a highly likely false inclusion or exclusion; "
        "the DB does not itself provide ground-truth person IDs for every year.",
        "",
    ]
    for case in CASES:
        key = case.namekey
        assert key in flags and key in edges and origins[key], case.label
        ssn_count, xlsx_any, non_exact_any = flags[key]
        computed_mode = 3 if ssn_count == 1 and xlsx_any and not non_exact_any else 4
        assert computed_mode == case.mode, (case.label, computed_mode)
        assert all(identity in raw for identity in (*case.targets, *case.comparators))
        assert all(identity in edges[key] for identity, _ in origins[key])
        for identity in case.targets:
            assert (identity in edges[key]) == (case.kind == "false inclusion"), (
                case.label, identity
            )
        lines += [
            f"## Mode {case.mode}: {case.label} — highly likely {case.kind}",
            "",
            f"NameKey: `{key}`. Sampled origin: "
            + ", ".join(f"`{file}#{row}` (draw `{draw}`)" for (file, row), draw in origins[key])
            + ".",
            "",
            case.argument,
            "",
        ]
        if case.mode == 3 and case.kind == "false inclusion":
            lines += [
                "Disposition: this mode-3 automatic match needs mode-4 manual review.",
                "",
            ]
        lines += [
            "Comparison award rows from the Step 2 population:",
            "",
            "| Role | XLSX row | Raw name | HCR category | Primary affiliation | "
            "Secondary affiliation |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        comparison = [(identity, "sampled origin") for identity, _ in origins[key]]
        comparison += [
            (identity, "same-year / trajectory comparator") for identity in case.comparators
        ]
        seen = set()
        for identity, role in comparison:
            if identity in seen:
                continue
            seen.add(identity)
            row = raw[identity]
            values = (role, f"{identity[0]}#{identity[1]}", _raw_name(row),
                      str(row[HCR_CATEGORY_COL] or ""), _raw_affiliation(row),
                      _raw_secondary_affiliation(row))
            lines.append("| " + " | ".join(value.replace("|", "\\|") for value in values) + " |")
        lines.append("")
        for identity in case.targets:
            row = raw[identity]
            lines += [
                f"### {'Falsely included' if case.kind == 'false inclusion' else 'Omitted'} "
                f"Step 2 award row: `{identity[0]}#{identity[1]}`",
                "",
                "```json",
                json.dumps(row, ensure_ascii=False, indent=2, default=str),
                "```",
                "",
            ]
            if case.kind == "false inclusion":
                payload = json.loads(str(edges[key][identity][KTP_XLSX_MATCH_COL]))
                assert payload.get(KTP_XLSX_MATCH_RULE_KEY) in {"v1", "v2"}
                lines += ["Persisted XLSX match payload:", "", "```json",
                          json.dumps(payload, ensure_ascii=False, indent=2), "```", ""]
    return "\n".join(lines).rstrip() + "\n"


def cli() -> None:
    parser = argparse.ArgumentParser(description="Render reviewed mode-3/4 XLSX failures.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(render(), encoding="utf-8")


if __name__ == "__main__":
    cli()
