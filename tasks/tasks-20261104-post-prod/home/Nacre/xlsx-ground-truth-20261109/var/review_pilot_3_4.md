# Manual HCR mask review: pilot.3 and pilot.4

## Source, method, and scope

- Copied Step03 HCR population: `in/03_infer_names_population_with_names_df.csv`, SHA-256 `ff647d6c3579c16ecc5dd115f59396cdf68301a2d1e2fdfb81794c38ac2a8389`, 59,665 rows. Pilot seeds are `out/master.seed.jsonl` positions 3 and 4. The designated DuckDB remains read-only; no v1/v2 matching output was used.
- I began with each seed row, then scanned the entire copied HCR population using independently chosen name, near-spelling, and affiliation/field searches. Candidate retrieval was only a way to find rows for manual adjudication, not the identity rule. The proof scripts claim the adjudicated rows from source fields, keep the seed first, and reject unreviewed rows within their declared spelling scopes. The source hash guard makes the decision conditional on these exact 59,665 source rows.
- These are proposed identity judgments for operator review. The source has no stable researcher ID, ORCID, or institutional-profile URL on the accepted rows; it cannot exclude an undisclosed alias with an unrelated name.

## Pilot.3 — Lizhi Zhang

Seed: `2024_HCR.xlsx#551`, Chemistry, Shanghai Jiao Tong University. The complete exact-name group contains eight HCR awards:

| HCR source row | Field | Primary affiliation | Secondary affiliation |
| --- | --- | --- | --- |
| `2018_HCR.xlsx#3229` | Cross-Field | Cent China Normal Univ | — |
| `2019_HCR.xlsx#3560` | Cross-Field | Central China Normal University | — |
| `2020_HCR.xlsx#3626` | Cross-Field | Central China Normal University | — |
| `2021_HCR.xlsx#3859` | Cross-Field | Shanghai Jiao Tong University | Central China Normal University |
| `2022_HCR.xlsx#4373` | Cross-Field | Shanghai Jiao Tong University | Central China Normal University |
| `2023_HCR.xlsx#632` | Chemistry | Shanghai Jiao Tong University | — |
| `2024_HCR.xlsx#551` | Chemistry | Shanghai Jiao Tong University | — |
| `2024_HCR.xlsx#4713` | Environment and Ecology | Central China Normal University | — |

The 2024 rows have the same full name but different categories and primary affiliations. The 2021 and 2022 rows explicitly name **both** institutions on the same Lizhi Zhang award, bridging the 2018–20 Central China Normal and 2023–24 Shanghai Jiao Tong series. A full-population scan found exactly two rows with Shanghai Jiao Tong primary and Central China Normal secondary: these 2021/2022 Lizhi Zhang rows. This is affirmative source evidence for treating the two 2024 entries as one researcher; it is still an identity inference, not a shared-ID proof.

Independent candidate searches across all 59,665 rows: (a) any compacted first/last containing `lizhi`, or `Zhang` with given name beginning `Li`, or `Chang`/`Zang` with given name beginning `Liz`: 20 name pairs / 54 rows; (b) compacted full name within three single-character edits of `lizhizhang`: 18 pairs / 56 rows; (c) Shanghai Jiao Tong or Central China Normal in any primary/secondary field, combined with `Zhang`/`Lizhi` or given name beginning `Li`: 9 pairs / 36 rows. I inspected the returned name, year, field, and institutional groupings. `Li Li`, `Lijun`, `Lixian`, `Lixia`, `Liping`, `Yihe`, and other near-name Zhang candidates have different given names and/or unrelated institution series; none supplies a competing Lizhi spelling at the linked institutions. The accepted group is the only exact Lizhi Zhang name pair in the source. `proof/pilot3_Lizhi_Zhang.py` checks every selected year and field, the 2018–20 primary affiliation, the 2021–22 primary/secondary institutional bridge, and the field-specific split in 2024.

## Pilot.4 — Rudolf A. de Boer

Seed: `2024_HCR.xlsx#657`, Clinical Medicine, Erasmus MC. The full exact-name group contains three awards:

| HCR source row | Field | Primary affiliation | Secondary affiliation |
| --- | --- | --- | --- |
| `2022_HCR.xlsx#778` | Clinical Medicine | Erasmus MC | University of Groningen |
| `2023_HCR.xlsx#752` | Clinical Medicine | Erasmus MC | University Groningen Medical Center |
| `2024_HCR.xlsx#657` | Clinical Medicine | Erasmus MC | University of Groningen |

Independent full-population candidate searches: any first name beginning Rudolf/Rudolph or surname ending `boer` yielded 13 name pairs / 50 rows; compacted full name within four edits of `rudolfadeboer` yielded only the exact Rudolf A. de Boer pair / 3 rows; Erasmus MC or Groningen plus Clinical Medicine yielded 11 name pairs / 29 rows. The only other exact `de Boer` surname in the source is Jacob de Boer (`2015_HCR.xlsx#1294`, Environment/Ecology, VU Amsterdam), a different given name, field, and institution; `proof/pilot4_Rudolf_A_de_Boer.py` explicitly excludes his row. No alternate Rudolf de Boer spelling surfaced. The three accepted rows retain the same full name, field, primary institution, and Groningen secondary affiliation across three consecutive years.

## Replay and mask state

- `pixi run -e default xlsx-ground-truth-replay` ran pilots 1–4 in actual draw order, assigning respectively 11, 4, 8, and 3 awards, then raised the expected `FileNotFoundError` for missing `pilot5_Hidenori_Arai.py`. It did not run numeric draw proofs, which occur after all ten pilots; replay reset the previous numeric-1/2 partial assignments from the master.
- Current `out/master.jsonl` SHA-256: `71d61adfbe9f50c66d399988b52137f372d45b6316d63ad3a32ce3e5ee19a973`. Pilot.3 owns exactly the eight Lizhi source references at line 3, seed first; pilot.4 owns exactly the three Rudolf references at line 4, seed first. Later same-NameKey draw lines remain present and empty: Lizhi at 12,769, 16,546, 25,646, 26,287, 39,326, 41,574, 55,418; Rudolf at 3,625 and 22,782. Across all 59,665 draw lines, 18,489 currently assigned HCR references have unique owners.
- This is a partial mask for review, not completed population ground truth. No v1/v2 FP+FN loss or rule iteration has been performed.
