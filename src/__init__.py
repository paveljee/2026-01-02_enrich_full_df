"""Top-level package for the KTP enrichment pipeline."""

from .name_utils import match_csv_docx_names, unify_first_last

__all__ = [
    "unify_first_last",
    "match_csv_docx_names",
]
