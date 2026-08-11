from __future__ import annotations

import json
import re
import string
from collections.abc import Mapping
from dataclasses import dataclass

LINE_BREAK = re.compile(r"\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]")
INLINE_CITATION_SEPARATOR = "\u2020"
URL_ARGUMENT_ACTIONS = ("open", "click")
REF_ID_ARGUMENT_KEY = "ref_id"
URL_ARGUMENT_KEY = "url"
MARKDOWN_ESCAPE_TRANSLATION = str.maketrans({
    character: f"\\{character}" for character in string.punctuation
})


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
        re.escape(marker_prefix) + f"(?P<ref_id>{ref_id_pattern})" + re.escape(marker_suffix)
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
            0 if preceding_separator < 0 else preceding_separator + len(result_separator)
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


def escape_markdown_text(value: str) -> str:
    return LINE_BREAK.sub(" ", value).translate(MARKDOWN_ESCAPE_TRANSLATION)


def strip_citation_markup(
    value: str,
    *,
    marker_prefix: str,
    marker_suffix: str,
) -> str:
    inline_open = re.compile(
        re.escape(marker_prefix)
        + rf"[^{re.escape(INLINE_CITATION_SEPARATOR)}]+"
        + re.escape(INLINE_CITATION_SEPARATOR)
    )
    domain_and_close = re.compile(
        re.escape(INLINE_CITATION_SEPARATOR)
        + rf"[^{re.escape(marker_suffix)}]*"
        + re.escape(marker_suffix)
    )
    return domain_and_close.sub("", inline_open.sub("", value)).replace(
        marker_suffix,
        "",
    )


def render_footnote(
    *,
    number: int,
    cite_text: str,
    citation_marker: str,
    marker_prefix: str,
    marker_suffix: str,
    excerpt: str,
    excerpt_position: int,
    context_characters: int,
    fco_timestamp: str,
    url: str,
) -> str:
    excerpt_end = excerpt_position + len(excerpt)
    context_start = max(0, excerpt_position - context_characters)
    context_end = min(len(cite_text), excerpt_end + context_characters)
    marker_start = cite_text.find(citation_marker)
    marker_end = marker_start + len(citation_marker)
    if marker_start < 0 or cite_text.find(citation_marker, marker_end) >= 0:
        raise ValueError("cite text does not contain one current-ref marker")
    if excerpt_end <= marker_start:
        context_end = min(context_end, marker_start)
    elif excerpt_position >= marker_end:
        context_start = max(context_start, marker_end)
    else:
        raise ValueError("excerpt overlaps its current-ref marker")
    prefix = "..." if context_start > 0 else ""
    suffix = "..." if context_end < len(cite_text) else ""
    before = escape_markdown_text(
        strip_citation_markup(
            cite_text[context_start:excerpt_position],
            marker_prefix=marker_prefix,
            marker_suffix=marker_suffix,
        )
    )
    escaped_excerpt = escape_markdown_text(
        strip_citation_markup(
            excerpt,
            marker_prefix=marker_prefix,
            marker_suffix=marker_suffix,
        )
    )
    after = escape_markdown_text(
        strip_citation_markup(
            cite_text[excerpt_end:context_end],
            marker_prefix=marker_prefix,
            marker_suffix=marker_suffix,
        )
    )
    return (
        f'{number}. "{prefix}{before}**{escaped_excerpt}**{after}{suffix}", '
        f"retrieved from web run tool using arguments^{number}^ on "
        f'"{fco_timestamp}", {url}'
    )


def render_footnote_argument(
    number: int,
    arguments_json: str,
    ref_urls: Mapping[str, str],
    *,
    ref_id_pattern: str,
) -> str:
    arguments = json.loads(arguments_json)
    if not isinstance(arguments, dict):
        raise ValueError("web arguments must be a JSON object")
    for action in URL_ARGUMENT_ACTIONS:
        action_items = arguments.get(action)
        if not action_items:
            continue
        if not isinstance(action_items, list):
            break
        display_items: list[object] = []
        changed = False
        for action_item in action_items:
            if not isinstance(action_item, dict):
                display_items.append(action_item)
                continue
            ref_id = action_item.get(REF_ID_ARGUMENT_KEY)
            ref_url = (
                ref_urls.get(ref_id)
                if isinstance(ref_id, str) and re.fullmatch(ref_id_pattern, ref_id)
                else None
            )
            if ref_url is None:
                display_items.append(action_item)
                continue
            display_item: dict[str, object] = {
                REF_ID_ARGUMENT_KEY: ref_id,
                URL_ARGUMENT_KEY: ref_url,
            }
            display_item.update({
                key: value
                for key, value in action_item.items()
                if key not in {REF_ID_ARGUMENT_KEY, URL_ARGUMENT_KEY}
            })
            display_items.append(display_item)
            changed = True
        if changed:
            arguments[action] = display_items
            arguments_json = json.dumps(
                arguments,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        break
    return f"{number}. {arguments_json}"
