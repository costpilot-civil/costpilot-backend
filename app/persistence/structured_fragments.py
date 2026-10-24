from __future__ import annotations

import json
from typing import Any

MAX_STRUCTURED_FRAGMENTS = 128


def build_structured_fragments(attributes: dict[str, Any]) -> list[dict[str, Any]]:
    fragments: list[dict[str, Any]] = []
    seen: set[str] = set()

    def append(fragment: dict[str, Any], weight: int) -> None:
        canonical = json.dumps(fragment, sort_keys=True, ensure_ascii=False)
        if canonical in seen:
            return
        if len(fragments) >= MAX_STRUCTURED_FRAGMENTS:
            raise ValueError("Too many extracted attributes for structured retrieval.")
        seen.add(canonical)
        fragments.append({"fragment": fragment, "weight": weight})

    for name, value in attributes.items():
        if not isinstance(name, str) or not name:
            continue
        weight = (
            10 if name == "strength_class" else 3 if name == "exposure_class" else 1
        )

        if isinstance(value, dict):
            for group, group_value in value.items():
                if isinstance(group, str) and group and _is_scalar(group_value):
                    append({name: {group: group_value}}, weight)
        elif isinstance(value, (list, tuple)):
            for item in value:
                if _is_scalar(item):
                    append({name: [item]}, weight)
        elif _is_scalar(value):
            append({name: value}, weight)

    return fragments


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) and value is not None
