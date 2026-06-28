"""Generate worker/src/_generated.ts from the canonical Python sources.

`aiapiradar/collector_meta.py` (COLLECTOR_META + STREAM_COLLECTORS) and
`aiapiradar/app_defaults.py` (settings_defaults) are the single source of truth.
The worker previously hand-mirrored this data, which drifted (e.g. the forum_rss
label diverged). This script renders the canonical Python values into a TS
module the worker imports; `tests/test_worker_constants_sync.py` fails if the
committed file diverges.

Usage:
    python -m scripts.gen_worker_constants
"""
from __future__ import annotations

import json
from pathlib import Path

HEADER = (
    "// AUTO-GENERATED from aiapiradar/collector_meta.py + app_defaults.py.\n"
    "// Do not edit by hand — regenerate with:  python -m scripts.gen_worker_constants\n"
)

GENERATED_PATH = (
    Path(__file__).resolve().parents[1] / "worker" / "src" / "_generated.ts"
)


def _ts(value) -> str:
    """Render a Python scalar/list/dict to a valid TS/JSON literal."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_ts(v) for v in value) + "]"
    if isinstance(value, dict):
        inner = ", ".join(f"{json.dumps(k)}: {_ts(v)}" for k, v in value.items())
        return "{ " + inner + " }"
    raise TypeError(f"unsupported value type: {type(value)!r}")


def render() -> str:
    """Return the full _generated.ts content."""
    from aiapiradar.collector_meta import COLLECTOR_META, STREAM_COLLECTORS
    from aiapiradar.app_defaults import settings_defaults

    lines: list[str] = [HEADER]

    # COLLECTOR_META — preserve Python dict insertion order.
    lines.append(
        "export const COLLECTOR_META: "
        "Record<string, { label: string; dot: string; requires: string | null }> = {"
    )
    for name, meta in COLLECTOR_META.items():
        lines.append(
            f"  {json.dumps(name)}: "
            f"{{ label: {_ts(meta['label'])}, dot: {_ts(meta['dot'])}, "
            f"requires: {_ts(meta['requires'])} }},"
        )
    lines.append("}")
    lines.append("")

    # STREAM_COLLECTORS — sorted for stability.
    stream = sorted(STREAM_COLLECTORS)
    lines.append(
        "export const STREAM_COLLECTORS = new Set<string>(["
        + ", ".join(_ts(s) for s in stream)
        + "])"
    )
    lines.append("")

    # SETTINGS_DEFAULTS — preserve key order from settings_defaults().
    lines.append("export const SETTINGS_DEFAULTS = {")
    for key, value in settings_defaults().items():
        lines.append(f"  {key}: {_ts(value)},")
    lines.append("} as const")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    content = render()
    with open(GENERATED_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"wrote {GENERATED_PATH} ({len(content)} bytes)")


if __name__ == "__main__":
    main()
