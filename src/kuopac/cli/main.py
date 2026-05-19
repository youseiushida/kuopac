"""``kuopac`` typer app entrypoint.

Top-level ``--`` flags are captured in a :class:`RunConfig` placed on
``typer.Context.obj`` so every command sees the same configuration.
"""
from __future__ import annotations

from typing import Annotated, Optional

import typer

# Disable typer's Rich-panel error formatting so ``CliError.show()`` (which
# emits a JSON envelope) runs in both ``standalone_mode`` paths — including
# inside ``typer.testing.CliRunner``.
try:
    import typer.rich_utils as _typer_rich_utils

    def _plain_rich_format_error(exc) -> None:  # type: ignore[no-untyped-def]
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
        typer.Option("--fields", help="ドット記法でのフィールド射影。複数指定可"),
    ] = None,
    limit: Annotated[
        Optional[int],
        typer.Option(
            "--limit",
            help="表示件数上限 (search / suggest / did-you-mean に適用)",
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
        limit=limit,
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
