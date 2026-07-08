"""Playlist sync CLI helpers and command."""

from __future__ import annotations

import pathlib as _pathlib
from typing import TYPE_CHECKING, Annotated, Any, cast

import typer
from rich.console import Console
from rich.table import Table

from tidal_dl.helper.path import path_config_base

if TYPE_CHECKING:
    from tidal_dl.helper.library_db import LibraryDB


def _sync_diff_playlists(
    playlists: list[Any],
    library_db: LibraryDB,
) -> list[dict[str, Any]]:
    """Compare Tidal playlists against the local library DB."""
    results: list[dict[str, Any]] = []

    for pl in playlists:
        tracks: list[Any] = []
        offset = 0
        while True:
            page = pl.tracks(limit=100, offset=offset)
            if not page:
                break
            tracks.extend(page)
            if len(page) < 100:
                break
            offset += 100

        total = len(tracks)
        local = 0
        for track in tracks:
            isrc = getattr(track, "isrc", None)
            if isrc and library_db.has_live_isrc(isrc):
                local += 1

        results.append({
            "name": pl.name,
            "total": total,
            "local": local,
            "missing": total - local,
            "share_url": pl.share_url,
        })

    return results


def _sync_print_summary(diff: list[dict[str, Any]], console: Console) -> None:
    table = Table(title="Playlist Sync Summary", show_lines=False)
    table.add_column("Playlist", style="cyan", no_wrap=True)
    table.add_column("Total", justify="right")
    table.add_column("Local", justify="right")
    table.add_column("Missing", justify="right")

    for row in diff:
        missing_style = "red bold" if row["missing"] > 0 else "green"
        table.add_row(
            row["name"],
            str(row["total"]),
            str(row["local"]),
            f"[{missing_style}]{row['missing']}[/{missing_style}]",
        )

    console.print(table)


def _sync_prompt_playlists(
    diff: list[dict[str, Any]],
    auto_yes: bool = False,
) -> list[str]:
    """Prompt the user to choose which playlists to sync."""
    selected: list[str] = []
    pending = [row for row in diff if row["missing"] > 0]

    if not pending:
        return selected

    if auto_yes:
        return [row["share_url"] for row in pending]

    for row in pending:
        answer = input(
            f"  Sync '{row['name']}' ({row['missing']} missing)? [Y]es / [n]o / [a]ll / [q]uit: "
        ).strip().lower()

        if answer in ("q", "quit"):
            break
        if answer in ("a", "all"):
            selected.append(row["share_url"])
            remaining = pending[pending.index(row) + 1 :]
            selected.extend(r["share_url"] for r in remaining)
            break
        if answer in ("n", "no"):
            continue
        selected.append(row["share_url"])

    return selected


def register_sync_command(app: typer.Typer) -> None:
    @app.command(name="sync")
    def sync(
        ctx: typer.Context,
        yes: Annotated[
            bool,
            typer.Option(
                "--yes",
                "-y",
                help="Skip per-playlist prompt and download all missing tracks.",
            ),
        ] = False,
    ) -> None:
        """Sync local library with your Tidal playlists."""
        from tidal_dl.cli import _ctx_tidal, _download, _resolve_session

        if not _resolve_session(ctx):
            raise typer.Exit(code=1)

        tidal = _ctx_tidal(ctx)
        console = Console()

        if tidal.session.user is None:
            console.print("[red]Sync requires an OAuth login to access your playlists.[/red]")
            console.print("Run [bold]music-dl login[/bold] first to authenticate with TIDAL.")
            raise typer.Exit(code=1)

        console.print("[cyan]Fetching your playlists...[/cyan]")
        user = cast(Any, tidal.session.user)
        all_playlists: list[Any] = []
        offset = 0
        while True:
            page = user.favorites.playlists(limit=50, offset=offset)
            if not page:
                break
            all_playlists.extend(page)
            if len(page) < 50:
                break
            offset += 50

        if not all_playlists:
            console.print("[yellow]No playlists found in your collection.[/yellow]")
            raise typer.Exit()

        console.print(f"[cyan]Found {len(all_playlists)} playlists. Checking tracks...[/cyan]")

        from tidal_dl.helper.library_db import LibraryDB

        library_db = LibraryDB(_pathlib.Path(path_config_base()) / "library.db")
        library_db.open()
        library_db.import_legacy_isrc_index(_pathlib.Path(path_config_base()) / "isrc_index.json")

        diff = _sync_diff_playlists(all_playlists, library_db)
        _sync_print_summary(diff, console)

        total_missing = sum(row["missing"] for row in diff)
        if total_missing == 0:
            console.print("\n[green]All playlists up to date.[/green]")
            raise typer.Exit()

        console.print(f"\n[cyan]{total_missing} total missing tracks across all playlists.[/cyan]\n")

        urls = _sync_prompt_playlists(diff, auto_yes=yes)
        if not urls:
            console.print("[yellow]No playlists selected. Nothing to do.[/yellow]")
            raise typer.Exit()

        result = _download(ctx, urls, try_login=False)
        if not result:
            raise typer.Exit(code=1)