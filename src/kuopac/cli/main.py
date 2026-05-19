"""``kuopac`` typer app entrypoint.

Top-level ``--`` flags are captured in a :class:`RunConfig` placed on
``typer.Context.obj`` so every command sees the same configuration.
"""
from __future__ import annotations

import sys
from typing import Annotated, Optional

import typer


def _force_utf8_streams() -> None:
    """Make stdout/stderr UTF-8 — and LF-only when piped — even on Windows.

    Two Windows-specific gotchas this fixes:

    1. ``kuopac --help`` and any JP search output mojibake when the parent
       shell hasn't set ``chcp 65001`` / ``PYTHONIOENCODING``.  Force UTF-8.

    2. On Windows, text-mode stdout translates ``\\n`` to ``\\r\\n``.  That
       contaminates JSON / NDJSON output read back by another process — e.g.
       ``kuopac ... | jq -r .bibid | xargs kuopac detail`` would pass
       ``BB...\\r`` as the bibid and 404.  When stdout isn't a TTY we suppress
       the translation so byte-output matches Unix.  For TTYs we keep the
       default so terminals that need CRLF still render correctly.

    Safe no-op on platforms/streams that already use UTF-8 LF.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            kwargs: dict[str, str] = {"encoding": "utf-8", "errors": "replace"}
            isatty = getattr(stream, "isatty", lambda: False)
            if not isatty():
                kwargs["newline"] = ""
            reconfigure(**kwargs)
        except (ValueError, OSError):
            # Stream is detached or doesn't support reconfigure — accept the
            # existing encoding rather than crashing.
            pass


_force_utf8_streams()

# Disable typer's Rich-panel error formatting so ``CliError.show()`` (which
# emits a JSON envelope) runs in both ``standalone_mode`` paths — including
# inside ``typer.testing.CliRunner``.
try:
    import typer.rich_utils as _typer_rich_utils

    def _plain_rich_format_error(exc) -> None:  # type: ignore[no-untyped-def]
        hint = _maybe_global_flag_hint(exc)
        if hint is not None:
            hint.show()
            return
        exc.show()
    _typer_rich_utils.rich_format_error = _plain_rich_format_error  # type: ignore[assignment]
except ImportError:  # pragma: no cover
    pass

from .. import __version__  # noqa: E402
from .config import OutputFormat, RunConfig, default_format  # noqa: E402
from .errors import translate  # noqa: E402

app = typer.Typer(
    name="kuopac",
    help="京都大学 OPAC (KULINE) コマンドラインクライアント。\n"
         "ドキュメント: https://github.com/youseiushida/kuopac",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
    pretty_exceptions_show_locals=False,
)


def _print_version_and_exit(value: bool) -> None:
    """``--version`` callback — eagerly exits before click validates subcommand."""
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main_callback(
    ctx: typer.Context,
    format_: Annotated[
        Optional[OutputFormat],
        typer.Option("--format", "-F",
                     help="出力形式 (TTY なら table、それ以外は json)"),
    ] = None,
    json_: Annotated[
        bool, typer.Option("--json", help="--format=json のエイリアス"),
    ] = False,
    fields_: Annotated[
        Optional[list[str]],
        typer.Option(
            "--fields",
            help="ドット記法でのフィールド射影 (複数指定可: 繰り返し or カンマ区切り)",
        ),
    ] = None,
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="stderr 進捗を抑制"),
    ] = False,
    explain: Annotated[
        bool, typer.Option("--explain", help="リクエスト URL を stderr に出す"),
    ] = False,
    explain_json: Annotated[
        bool, typer.Option("--explain-json",
                           help="リクエスト情報を JSON の _meta に埋め込む"),
    ] = False,
    no_color: Annotated[
        bool, typer.Option("--no-color", help="色付けを無効化"),
    ] = False,
    user_agent: Annotated[
        str, typer.Option("--user-agent", help="HTTP UA を上書き"),
    ] = "kuopac/0.1",
    rate_limit: Annotated[
        float, typer.Option("--rate-limit",
                            help="連続リクエスト間の最小間隔 (秒)"),
    ] = 0.0,
    timeout: Annotated[
        float, typer.Option("--timeout", help="HTTP タイムアウト (秒)"),
    ] = 30.0,
    strict: Annotated[
        bool, typer.Option("--strict",
                           help="0件ヒットを exit code 1 にする"),
    ] = False,
    version_: Annotated[
        bool,
        typer.Option(
            "--version",
            help="バージョンを表示して終了",
            callback=_print_version_and_exit,
            is_eager=True,
        ),
    ] = False,
) -> None:
    chosen: OutputFormat
    if json_:
        chosen = "json"
    elif format_ is not None:
        chosen = format_  # type: ignore[assignment]
    else:
        chosen = default_format()

    ctx.obj = RunConfig(
        format=chosen,
        fields=fields_ or None,
        quiet=quiet,
        explain=explain,
        explain_json=explain_json,
        no_color=no_color,
        user_agent=user_agent,
        rate_limit=rate_limit,
        timeout=timeout,
        strict=strict,
    )


# ---- Command registration --------------------------------------------------
# Each command module exposes a ``register(app)`` function so the top-level
# wiring stays inside ``main.py``.
from .commands import (   # noqa: E402  (import order intentional)
    detail as _detail,
    did_you_mean as _did_you_mean,
    facets as _facets,
    holdings as _holdings,
    manifest as _manifest,
    schema_cmd as _schema_cmd,
    search as _search,
    status as _status,
    suggest as _suggest,
    synopsis as _synopsis,
    version as _version,
)

for mod in (_search, _detail, _holdings, _status, _suggest, _did_you_mean,
            _facets, _synopsis, _schema_cmd, _manifest, _version):
    mod.register(app)


# ---- Global error trap -----------------------------------------------------

# Names of every flag defined on ``main_callback``.  When a user puts one of
# these after the subcommand (``kuopac search --json …``), click raises
# ``NoSuchOption`` for the subcommand.  We catch that case and rewrite the
# error to nudge the user toward the right position.
_GLOBAL_FLAG_NAMES = frozenset({
    "--format", "-F", "--json", "--fields",
    "--quiet", "-q",
    "--explain", "--explain-json",
    "--no-color", "--user-agent",
    "--rate-limit", "--timeout",
    "--strict", "--version",
})


def _maybe_global_flag_hint(exc) -> "CliError | None":  # type: ignore[name-defined]
    """Map a misplaced-global ``NoSuchOption`` to a hint-bearing :class:`CliError`.

    Returns ``None`` when the offending option isn't a known global flag, so
    click's default formatting (with its own "Did you mean ..." spelling
    correction) is preserved for true typos.
    """
    import click
    if not isinstance(exc, click.exceptions.NoSuchOption):
        return None
    bad = getattr(exc, "option_name", None)
    if not bad or bad not in _GLOBAL_FLAG_NAMES:
        return None
    from .errors import CliError
    # ``ctx.info_name`` is the subcommand click was parsing when it failed.
    ctx = getattr(exc, "ctx", None)
    sub = getattr(ctx, "info_name", None) or "<subcommand>"
    hint = (
        f"{bad} は global option です。subcommand の前に置いてください: "
        f"`kuopac {bad} ... {sub} ...`"
    )
    return CliError("INVALID_ARGUMENT", hint)


def _main_with_errors() -> int:
    """Wrap ``app()`` so library exceptions become structured CLI errors.

    ``CliError`` is a :class:`click.ClickException` so ``.show()`` handles
    structured output (stderr line + JSON envelope on stdout for non-NO_HITS).
    Non-CliError exceptions are translated to one and rendered the same way.
    """
    import click
    try:
        app(standalone_mode=False)
        return 0
    except click.ClickException as e:
        hint = _maybe_global_flag_hint(e)
        if hint is not None:
            hint.show()
            return hint.exit_code
        e.show()
        return getattr(e, "exit_code", 1)
    except KeyboardInterrupt:
        return 130
    except SystemExit as e:
        return int(e.code or 0) if isinstance(e.code, int) else 0
    except Exception as e:  # noqa: BLE001 — last-resort guard
        cli_err = translate(e)
        cli_err.show()
        return cli_err.exit_code


def main() -> None:  # pragma: no cover - exercised via console script
    raise SystemExit(_main_with_errors())


if __name__ == "__main__":  # pragma: no cover
    main()
