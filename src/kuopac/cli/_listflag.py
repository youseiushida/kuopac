"""Shared helper for typer ``list[str]`` flags that accept both forms:

    --flag a,b,c              (one repeat, comma-separated)
    --flag a --flag b --flag c (multiple repeats)
    --flag a,b --flag c       (mixed)

All CLI list flags (`--fields`, `--with`, `--type`, `--media`, `--field`,
`--refine`) go through :func:`split_list_flag` so the two surface forms are
indistinguishable to the rest of the command.
"""
from __future__ import annotations


def split_list_flag(
    raw_args: list[str] | None,
    *,
    lowercase: bool = False,
) -> list[str]:
    """Flatten a typer-collected ``list[str]`` into an ordered list of tokens.

    Empty tokens are dropped; order is preserved (no dedup) so callers that
    care about ordering — e.g. ``--media`` translating to multiple
    ``dtmd_exp`` params on the wire — keep their intent.

    ``lowercase=True`` casefolds each token, used by ``--with`` where the
    set of valid values is a small lowercase enum.
    """
    if not raw_args:
        return []
    out: list[str] = []
    for raw in raw_args:
        for token in raw.split(","):
            token = token.strip()
            if not token:
                continue
            if lowercase:
                token = token.lower()
            out.append(token)
    return out
