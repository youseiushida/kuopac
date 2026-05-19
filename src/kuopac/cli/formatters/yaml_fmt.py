"""``--format=yaml`` writer (optional extra; requires ``pyyaml``)."""
from __future__ import annotations

import sys
from typing import Any, TextIO


def write(envelope: dict[str, Any], *, stream: TextIO | None = None) -> None:
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover - only hit without optional extra
        raise RuntimeError(
            "yaml output requires the 'cli-yaml' extra: pip install kuopac[cli-yaml]"
        ) from e
    out = stream or sys.stdout
    yaml.safe_dump(
        envelope, out, allow_unicode=True, sort_keys=False, default_flow_style=False
    )
