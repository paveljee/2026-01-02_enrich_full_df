from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CiteSection:
    ref_id: str
    text: str


def extract_cite_sections(
    text: str,
    *,
    marker_prefix: str,
    marker_suffix: str,
    ref_id_pattern: str,
    result_separator: str,
) -> tuple[CiteSection, ...]:
    marker = re.compile(
        re.escape(marker_prefix)
        + f"(?P<ref_id>{ref_id_pattern})"
        + re.escape(marker_suffix)
    )
    matches = tuple(marker.finditer(text))
    relevant_marker_count = text.count(f"{marker_prefix}turn")
    if not matches:
        if relevant_marker_count:
            raise ValueError("web output contains malformed citation markers")
        return ()
    if relevant_marker_count != len(matches):
        raise ValueError("web output contains malformed citation markers")

    sections: list[CiteSection] = []
    seen_ref_ids: set[str] = set()
    for match in matches:
        ref_id = match.group("ref_id")
        if ref_id in seen_ref_ids:
            raise ValueError(f"web output repeats citation ref_id {ref_id}")
        seen_ref_ids.add(ref_id)

        preceding_separator = text.rfind(result_separator, 0, match.start())
        section_start = (
            0
            if preceding_separator < 0
            else preceding_separator + len(result_separator)
        )
        following_separator = text.find(result_separator, match.end())
        section_end = len(text) if following_separator < 0 else following_separator
        section_text = text[section_start:section_end].strip()
        if not section_text or len(tuple(marker.finditer(section_text))) != 1:
            raise ValueError(f"could not isolate citation section for {ref_id}")
        sections.append(CiteSection(ref_id=ref_id, text=section_text))
    return tuple(sections)


def render_ai_value(value: str, footnote_numbers: tuple[int, ...]) -> str:
    marker = ""
    if footnote_numbers:
        marker = "^" + ",".join(str(number) for number in footnote_numbers) + "^"
    return f'**AI-generated text**: "{value}"{marker}'


def render_comment(value: str, timestamp: str) -> str:
    return f'- **AI-generated text**: "{value}" ({timestamp})'


def render_footnote(
    *,
    number: int,
    cite_text: str,
    excerpt: str,
    excerpt_position: int,
    context_characters: int,
    fco_timestamp: str,
    url: str,
) -> str:
    excerpt_end = excerpt_position + len(excerpt)
    context_start = max(0, excerpt_position - context_characters)
    context_end = min(len(cite_text), excerpt_end + context_characters)
    prefix = "..." if context_start > 0 else ""
    suffix = "..." if context_end < len(cite_text) else ""
    before = cite_text[context_start:excerpt_position]
    after = cite_text[excerpt_end:context_end]
    return (
        f'{number}. "{prefix}{before}**{excerpt}**{after}{suffix}", '
        f"retrieved from web run tool using arguments^{number}^ on "
        f'"{fco_timestamp}", {url}'
    )


def render_footnote_argument(number: int, arguments_json: str) -> str:
    return f"{number}. {arguments_json}"
