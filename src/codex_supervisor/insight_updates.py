"""Guarded markdown update helpers for reusable insight records."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from codex_supervisor.insights import InsightRecord

_START_MARKER_PREFIX = "<!-- codex-supervisor:insight "
_END_MARKER_PREFIX = "<!-- /codex-supervisor:insight "


class InsightUpdateError(ValueError):
    """Raised when an insight markdown update cannot be applied safely."""


@dataclass(frozen=True)
class InsightMarkdownUpdate:
    """Deterministic markdown block rendered from a validated insight record."""

    anchor: str
    markdown: str
    promotion_criteria: tuple[str, ...]
    provenance: tuple[str, ...]


@dataclass(frozen=True)
class AppliedInsightUpdate:
    """Result of applying a deterministic insight update to a markdown file."""

    anchor: str
    markdown: str
    target_path: Path
    changed: bool


def render_insight_markdown_update(
    record: InsightRecord,
    *,
    promotion_criteria: Iterable[str] = (),
    provenance: Iterable[str] = (),
) -> InsightMarkdownUpdate:
    """Render a deterministic markdown block for a validated insight record."""

    criteria = _string_tuple(promotion_criteria, "promotion_criteria")
    provenance_entries = _string_tuple(provenance, "provenance") or record.evidence
    anchor = _insight_anchor(record.claim)
    markdown = "\n".join(
        (
            f"{_START_MARKER_PREFIX}{anchor} -->",
            f"### {record.claim}",
            "",
            f"- Confidence: `{record.confidence}`",
            f"- Scope: {record.scope}",
            "",
            "#### Evidence",
            *_markdown_bullets(record.evidence),
            "",
            "#### Supersedes",
            *_markdown_bullets(record.supersedes),
            "",
            "#### Next Action",
            "",
            record.next_action,
            "",
            "#### Promotion Criteria",
            *_markdown_bullets(criteria),
            "",
            "#### Provenance",
            *_markdown_bullets(provenance_entries),
            f"{_END_MARKER_PREFIX}{anchor} -->",
            "",
        )
    )
    return InsightMarkdownUpdate(
        anchor=anchor,
        markdown=markdown,
        promotion_criteria=criteria,
        provenance=provenance_entries,
    )


def apply_insight_update(
    target_path: Path,
    record: InsightRecord,
    *,
    promotion_criteria: Iterable[str] = (),
    provenance: Iterable[str] = (),
) -> AppliedInsightUpdate:
    """Apply a rendered insight block idempotently to a markdown target file."""

    update = render_insight_markdown_update(
        record,
        promotion_criteria=promotion_criteria,
        provenance=provenance,
    )
    current_text = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
    updated_text = _replace_or_append_insight_block(current_text, update.anchor, update.markdown)
    changed = updated_text != current_text
    if changed:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(updated_text, encoding="utf-8")
    return AppliedInsightUpdate(
        anchor=update.anchor,
        markdown=update.markdown,
        target_path=target_path,
        changed=changed,
    )


def _replace_or_append_insight_block(text: str, anchor: str, markdown: str) -> str:
    start_marker = f"{_START_MARKER_PREFIX}{anchor} -->"
    end_marker = f"{_END_MARKER_PREFIX}{anchor} -->"
    start_index = text.find(start_marker)
    if start_index == -1:
        separator = "" if text == "" or text.endswith("\n\n") else "\n\n"
        return f"{text}{separator}{markdown}"
    end_index = text.find(end_marker, start_index)
    if end_index == -1:
        msg = f"existing insight block {anchor!r} is missing its end marker"
        raise InsightUpdateError(msg)
    block_end = end_index + len(end_marker)
    while block_end < len(text) and text[block_end] == "\n":
        block_end += 1
    return f"{text[:start_index]}{markdown}{text[block_end:]}"


def _insight_anchor(claim: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", claim.lower()).strip("-")
    if not slug:
        slug = "insight"
    digest = hashlib.sha256(claim.encode("utf-8")).hexdigest()[:12]
    return f"insight-{slug[:48].strip('-')}-{digest}"


def _markdown_bullets(values: tuple[str, ...]) -> tuple[str, ...]:
    if not values:
        return ("- none",)
    return tuple(f"- {value}" for value in values)


def _string_tuple(values: Iterable[str], field_name: str) -> tuple[str, ...]:
    normalized = tuple(values)
    if any(not isinstance(value, str) or value.strip() == "" for value in normalized):
        msg = f"{field_name} entries must be nonblank strings"
        raise InsightUpdateError(msg)
    return normalized
