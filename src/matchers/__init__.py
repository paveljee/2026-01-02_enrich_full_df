from .csv_matcher import append_csv_matches
from .docx_matcher import append_docx_matches
from .parquet_matcher import append_parquet_matches
from .xlsx_matcher import append_population_matches

__all__ = [
    "append_population_matches",
    "append_csv_matches",
    "append_docx_matches",
    "append_parquet_matches",
]
