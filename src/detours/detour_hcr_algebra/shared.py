"""Report formatting shared by HCR-algebra detours."""

from collections.abc import Sequence


def markdown_table(headers: tuple[str, ...], rows: Sequence[tuple[str, ...]]) -> None:
    print("| " + " | ".join(headers) + " |")
    print("| " + " | ".join("---" for _ in headers) + " |")
    for cells in rows:
        print("| " + " | ".join(cells) + " |")
    print()
