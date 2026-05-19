"""``--format=json`` writer: pretty-printed envelope."""
from __future__ import annotations

import json
import sys
from typing import Any, TextIO


def write(envelope: dict[str, Any], *, stream: TextIO | None = None) -> None:
    """Dump the envelope as indented JSON terminated by a newline."""
    out = stream or sys.stdout
    json.dump(envelope, out, ensure_ascii=False, indent=2)
    out.write("\n")
