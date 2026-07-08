"""Library scan CLI helpers and commands."""

from __future__ import annotations

import pathlib as _pathlib
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table as RichTable

from tidal_dl.config import Settings


def _scan_paths_list(settings: Settings) -> list[str]:
    raw = settings.data.scan_paths or ""
    return [p.strip() for p in raw.split(",") if p.strip()]


def _run_scan(paths: list[str], *, dry_run: bool, verbose: bool) -> None:
    from tidal_dl.helper.library_db import LibraryDB
    from tidal_dl.helper.library_scanner import scan_directory
    from tidal_dl.helper.path import path_config_base

    console = Console()
    library_db = LibraryDB(_pathlib.Path(path_config_base()) / "library.db")
    library_db.open()
    library_db.import_legacy_isrc_index(_pathlib.Path(path_config_base()) / "isrc_index.json")

    total_files = 0
    total_found = 0
    total_already = 0
    total_no_isrc = 0
    total_errors = 0
    all_error_paths: list[str] = []

    for scan_root in paths:
        root = _pathlib.Path(scan_root).expanduser()
        if not root.is_dir():
            console.print(f"[yellow]Warning:[/yellow] '{scan_root}' is not a directory — skipping.")
            continue

        console.print(f"\n[cyan]Scanning:[/cyan] {root}")

        progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            SpinnerColumn(),
            BarColumn(),
            TextColumn("{task.fields[scanned]} files"),
            refresh_per_second=20,
            expand=True,
            transient=True,
        )

        task = progress.add_task("Scanning...", scanned=0)
        scanned_count = 0

        def _on_file(p: _pathlib.Path) -> None:
            nonlocal scanned_count
            scanned_count += 1
            progress.update(task, scanned=scanned_count)
            if verbose:
                progress.print(f"  [dim]{p}[/dim]")

        with progress:
            result = scan_directory(root, library_db, dry_run=dry_run, on_file=_on_file)

        total_files += result.files_scanned
        total_found += result.isrcs_found
        total_already += result.already_indexed
        total_no_isrc += result.no_isrc
        total_errors += result.errors
        all_error_paths.extend(result.error_paths)

        console.print(
            f"  [green]{result.isrcs_found}[/green] new  "
            f"[dim]{result.already_indexed}[/dim] already indexed  "
            f"[yellow]{result.no_isrc}[/yellow] no ISRC  "
            f"[red]{result.errors}[/red] errors  "
            f"({result.elapsed_sec:.1f}s)"
        )

    if not dry_run and total_found > 0:
        library_db.commit()

    summary = RichTable.grid(padding=(0, 2))
    summary.add_column(style="bold")
    summary.add_column()
    summary.add_row("Directories scanned", str(len(paths)))
    summary.add_row("Audio files examined", str(total_files))
    summary.add_row("[green]New ISRCs indexed[/green]", str(total_found))
    summary.add_row("Already in index", str(total_already))
    summary.add_row("No ISRC tag", str(total_no_isrc))
    summary.add_row("[red]Errors[/red]", str(total_errors))
    if dry_run:
        summary.add_row("Mode", "[yellow]dry-run — nothing written[/yellow]")

    console.print()
    console.print(Panel(summary, title="[bold]Scan Summary[/bold]", expand=False))

    if all_error_paths:
        console.print("\n[red]Files with errors (first 50):[/red]")
        for ep in all_error_paths[:50]:
            console.print(f"  {ep}")


def register_scan_commands(app_scan: typer.Typer) -> None:
    @app_scan.callback(invoke_without_command=True)
    def scan_callback(
        ctx: typer.Context,
        dry_run: Annotated[
            bool,
            typer.Option("--dry-run", help="Discover ISRCs without writing to the index."),
        ] = False,
        scan_all: Annotated[
            bool,
            typer.Option("--all", help="Scan all configured paths without prompting."),
        ] = False,
        verbose: Annotated[
            bool,
            typer.Option("--verbose", "-v", help="Print each file path as it is scanned."),
        ] = False,
    ) -> None:
        if ctx.invoked_subcommand is not None:
            return

        settings = Settings()
        paths = _scan_paths_list(settings)
        console = Console()

        if not paths:
            console.print(
                "[yellow]No scan directories configured.[/yellow]\n"
                "Add one with:  [cyan]music-dl scan add <PATH>[/cyan]"
            )
            raise typer.Exit(1)

        if len(paths) == 1 or scan_all:
            chosen = paths
        else:
            console.print("[cyan]Configured scan directories:[/cyan]")
            for i, p in enumerate(paths, 1):
                console.print(f"  [{i}] {p}")
            console.print(f"  [a] All ({len(paths)} directories)")
            choice: str = typer.prompt("Select directory (number or 'a')", default="a")
            if choice.strip().lower() == "a":
                chosen = paths
            else:
                try:
                    idx = int(choice.strip()) - 1
                    if not 0 <= idx < len(paths):
                        raise ValueError
                    chosen = [paths[idx]]
                except ValueError:
                    console.print("[red]Invalid selection.[/red]")
                    raise typer.Exit(1)

        _run_scan(chosen, dry_run=dry_run, verbose=verbose)

    @app_scan.command(name="add")
    def scan_add(
        path: Annotated[str, typer.Argument(help="Directory path to add to the scan list.")],
        no_scan: Annotated[
            bool,
            typer.Option("--no-scan", help="Only save the path without scanning it."),
        ] = False,
    ) -> None:
        settings = Settings()
        current = _scan_paths_list(settings)
        normalized = path.strip().rstrip("/").rstrip("\\")
        already_configured = normalized in current
        if normalized and not already_configured:
            current.append(normalized)
            settings.data.scan_paths = ",".join(current)
            settings.save()
            print(f"Added: {normalized}")
        else:
            print(f"Already configured: {normalized}")
        if not no_scan:
            _run_scan([normalized], dry_run=False, verbose=False)

    @app_scan.command(name="remove")
    def scan_remove(
        path: Annotated[str, typer.Argument(help="Directory path to remove from the scan list.")],
    ) -> None:
        settings = Settings()
        current = _scan_paths_list(settings)
        normalized = path.strip().rstrip("/").rstrip("\\")
        updated = [p for p in current if p != normalized]
        if len(updated) == len(current):
            print(f"Not found in scan paths: {normalized}")
        else:
            settings.data.scan_paths = ",".join(updated)
            settings.save()
            print(f"Removed: {normalized}")
        print(f"Scan paths: {settings.data.scan_paths or '(none)'}")

    @app_scan.command(name="show")
    def scan_show() -> None:
        settings = Settings()
        paths = _scan_paths_list(settings)
        if not paths:
            print("No scan paths configured. Add one with: music-dl scan add <PATH>")
            return
        for i, p in enumerate(paths, 1):
            exists = _pathlib.Path(p).expanduser().is_dir()
            status = "[green]ok[/green]" if exists else "[red]missing[/red]"
            Console().print(f"  [{i}] {p}  {status}")