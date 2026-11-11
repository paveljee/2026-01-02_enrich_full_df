# Manual HCR mask review: pilot.1 and pilot.2 (preliminary)

These scripts predate the seed-first, independently investigated exhaustive-proof workflow. Their spelling-based selections and affiliation checks are working assignments, not yet attested as all actual same-researcher innerdicts.

## Source and order

- Designated read-only DB: data/scisci_process.duckdb, SHA-256 adb37937571b8f43280d148b8b5921b31e2d2603a8694104478c71dae548ffd2.
- Sampling config: config.repl.all_mode3.json, SHA-256 74ad287b3c2b46aa078d54056ca616c1dd45fa607480589b2f32b41df52bd309.
- Copied Step03 CSV: in/03_infer_names_population_with_names_df.csv, SHA-256 ff647d6c3579c16ecc5dd115f59396cdf68301a2d1e2fdfb81794c38ac2a8389, 59,665 rows.
- src/seed.py reuses the pipeline Step05 draw-batch function, pilot triples, and Pydantic config. The ordered view puts pilot.1–pilot.10 before numeric draws. It applies the current Step03 edge-whitespace rule to the read-only DB names. Each of the 59,665 draws gets one JSONL line; repeated complete NameKeys and four excluded incomplete-name draws have empty lists. The earliest drawn complete NameKey owns its seed.
- out/master.seed.jsonl SHA-256 300cdc06f8f0c8c477bd452b02a6f0416dba5279e4cc7a338c06ef330c8e2c34. out/master.jsonl after two pilot reviews SHA-256 66d796007abbc5d7081f34f351c1a8b0b56a50ca37f7e03ec19191e0188ba9c4. The seed contains 18,468 complete NameKeys; the reviewed mask has 59,665 lines, 41,198 empty lines, and 18,480 uniquely owned award references. Four incomplete-name placeholder keys are not valid production NameKeys.
- Old numeric-draw-1/2 review is preserved in var/review_numeric_1_2_historical.md and out/master.before_draw_order_repair.jsonl. Its old claim that numeric draws were the first two in overall draw order is superseded. Numeric scripts proof/1_Andrew_P_Morris.py and proof/2_Tobin_J_Marks.py have not yet been replayed on this pilot-first mask.

## Pilot.1 — Bin Gao

Seed 2024_HCR.xlsx#1890, Cross-Field, Rice University. The script proof/pilot1_Bin_Gao.py scans the complete copied CSV and selects first=Bin, last=Gao; the exact spelling yields these 11 rows. None has an ORCID, HCR researcher ID, or institutional-profile value in the source.

| HCR source row | Field | Primary affiliation |
| --- | --- | --- |
| 2018_HCR.xlsx#1818 | Cross-Field | Univ Florida |
| 2019_HCR.xlsx#3780 | Engineering | University of Florida |
| 2019_HCR.xlsx#3987 | Environment and Ecology | University of Florida |
| 2020_HCR.xlsx#3832 | Engineering | University of Florida |
| 2020_HCR.xlsx#4041 | Environment and Ecology | University of Florida |
| 2021_HCR.xlsx#4075 | Engineering | University of Florida |
| 2021_HCR.xlsx#4272 | Environment and Ecology | University of Florida |
| 2022_HCR.xlsx#196 | Biology and Biochemistry | University of Florida |
| 2022_HCR.xlsx#4653 | Environment and Ecology | University of Florida |
| 2022_HCR.xlsx#4835 | Engineering | University of Florida |
| 2024_HCR.xlsx#1890 | Cross-Field | Rice University |

Manual identity judgment for operator review: the recurring exact name, overlapping Cross-Field/engineering/environmental fields, and coherent Florida 2018–22 series support one researcher, but the 2024 move to Rice is not independently proven by a stable identifier in the provided source. Exact-name sameness alone is insufficient to establish that transition. The script pins both affiliation eras as source-evidence checks; it does not encode individual matched row numbers beyond its seed. The complete Gao surname group in this source has 38 distinct first/last pairs (154 rows); only Bin Gao has this exact first name. The closest full-name spelling candidates Bin Yao and Bing Xiao have different surnames and affiliations.

## Pilot.2 — Beatriz Roldan Cuenya

Seed 2024_HCR.xlsx#383, Chemistry, Ruhr University Bochum. The script proof/pilot2_Beatriz_Roldan_Cuenya.py scans the complete copied CSV and considers both source first/last splits:

| HCR source row | Source first / last | Field | Primary affiliation |
| --- | --- | --- | --- |
| 2021_HCR.xlsx#3079 | Beatriz / Roldan Cuenya | Cross-Field | Max Planck Society |
| 2022_HCR.xlsx#3470 | Beatriz / Roldan Cuenya | Cross-Field | Max Planck Society |
| 2023_HCR.xlsx#3497 | Beatriz / Roldan Cuenya | Cross-Field | Max Planck Society |
| 2024_HCR.xlsx#383 | Beatriz Roldan / Cuenya | Chemistry | Ruhr University Bochum |

The complete full-name tokens are unchanged; only their first/last boundary shifts. The cross-field/chemistry sequence and German institutional affiliations support the same-person judgment, while the Max Planck-to-Ruhr link is not independently identified by a source ID. Across the entire copied CSV, the two spellings above are the only Beatriz/Roldan/Cuenya rows. The later Beatriz / Roldan Cuenya NameKey remains in the mask at positions 5,405, 28,856, and 42,318 with empty lists; its three awards are owned only by pilot.2.

## Replay and limits

Running pixi run -e default python tasks/tasks-20261104-post-prod/home/Nacre/xlsx-ground-truth-20261109/src/replay.py reset the reviewed mask from the seed, assigned 11 and 4 awards to pilots 1 and 2 respectively, verified exclusive award ownership, then raised the expected FileNotFoundError for missing pilot.3 script pilot3_Lizhi_Zhang.py. This is the agreed stop point for operator review, not a full replay success. The scripts' name scopes and source assertions are inspectable, but they do not independently prove a real-world identity link across affiliation changes or eliminate unknown aliases. No v1/v2 loss or matching-rule iteration has been measured.
