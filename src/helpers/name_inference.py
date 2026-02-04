from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..hcr_xlsx.loader import normalize_hcr_header


def infer_name_columns_from_xlsx(path: Path) -> tuple[str, str] | None:
    try:
        df = pd.read_excel(path, engine="openpyxl")
    except Exception:
        return None
    normalized = [normalize_hcr_header(str(col).lower()) for col in df.columns]

    def pick(candidates: list[str]) -> str | None:
        for cand in candidates:
            for col in normalized:
                if cand in col:
                    return col
        return None

    first = pick(["first_name", "firstname", "first name", "first"])
    last = pick(["last_name", "lastname", "last name", "family_name", "familyname", "surname", "last"])
    if not first or not last or first == last:
        return None
    return first, last
