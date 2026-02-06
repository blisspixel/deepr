"""Migration utilities for organizing legacy reports."""

import shutil
from pathlib import Path

import click

from deepr.cli.colors import print_error, print_success


@click.group()
def migrate():
    """Migrate and organize legacy reports."""
    pass


@migrate.command()
@click.option("--dry-run", is_flag=True, help="Show what would be done without making changes")
@click.option("--reports-dir", default="data/reports", help="Reports directory to migrate")
def organize(dry_run: bool, reports_dir: str):
    """
    Organize legacy reports into human-readable format.

    Moves flat files and UUID-only directories into organized structure
    with timestamps and readable names.
    """
    reports_path = Path(reports_dir)

    if not reports_path.exists():
        print_error(f"Reports directory not found: {reports_dir}")
        return

    click.echo(f"[*] Scanning {reports_dir} for legacy reports...")

    legacy_files = []
    legacy_dirs = []

    # Find legacy flat files (*.md directly in reports/)
    for item in reports_path.iterdir():
        if item.is_file() and item.suffix == ".md":
            legacy_files.append(item)

    # Find legacy UUID-only directories (no timestamp prefix)
    for item in reports_path.iterdir():
        if item.is_dir() and item.name != "campaigns":
            # Check if it's a UUID-only format (no timestamp)
            if not item.name[0].isdigit() or "_" not in item.name:
                # Skip if it's already a campaign
                if not item.name.startswith("campaign-"):
                    legacy_dirs.append(item)

    total = len(legacy_files) + len(legacy_dirs)

    if total == 0:
        print_success("No legacy reports found. All reports are organized!")
        return

    click.echo(f"\nFound {len(legacy_files)} flat files and {len(legacy_dirs)} legacy directories")

    if dry_run:
        click.echo("\n[DRY RUN] No changes will be made\n")

    # Create archive folder for legacy items
    archive_path = reports_path / "_legacy_archive"

    if not dry_run:
        archive_path.mkdir(exist_ok=True)

    click.echo(f"\n[ARCHIVE] Moving legacy reports to: {archive_path}\n")

    # Move flat files to archive
    for file_path in legacy_files:
        target = archive_path / file_path.name
        click.echo(f"  * {file_path.name} -> _legacy_archive/")

        if not dry_run:
            shutil.move(str(file_path), str(target))

    # Move legacy directories to archive
    for dir_path in legacy_dirs:
        target = archive_path / dir_path.name
        click.echo(f"  * {dir_path.name}/ -> _legacy_archive/")

        if not dry_run:
            shutil.move(str(dir_path), str(target))

    if dry_run:
        print_success("Dry run complete. Run without --dry-run to apply changes.")
    else:
        print_success(f"Migrated {total} legacy items to _legacy_archive/")
        click.echo("\nNote: New reports will use human-readable names with timestamps.")
        click.echo("Format: YYYY-MM-DD_HHMM_topic-name_shortid/")


@migrate.command()
@click.option("--reports-dir", default="data/reports", help="Reports directory")
def stats(reports_dir: str):
    """Show statistics about report organization."""
    reports_path = Path(reports_dir)

    if not reports_path.exists():
        print_error(f"Reports directory not found: {reports_dir}")
        return

    # Count different types
    legacy_flat = 0
    legacy_dirs = 0
    organized = 0
    campaigns = 0

    for item in reports_path.iterdir():
        if item.is_file() and item.suffix == ".md":
            legacy_flat += 1
        elif item.is_dir():
            if item.name == "campaigns":
                # Count campaign subdirectories
                if item.exists():
                    campaigns = len([d for d in item.iterdir() if d.is_dir()])
            elif item.name == "_legacy_archive":
                continue  # Skip archive folder
            elif item.name[0].isdigit() and "_" in item.name:
                organized += 1
            else:
                legacy_dirs += 1

    click.echo("Report Organization Statistics\n")
    click.echo(f"Organized reports:   {organized:>4} (timestamped, readable names)")
    click.echo(f"Legacy directories:  {legacy_dirs:>4} (UUID-only)")
    click.echo(f"Legacy flat files:   {legacy_flat:>4} (*.md in root)")
    click.echo(f"Campaigns:           {campaigns:>4} (multi-phase research)")

    total = organized + legacy_dirs + legacy_flat + campaigns

    if total > 0:
        organized_pct = (organized / total) * 100
        click.echo(f"\nOrganization: {organized_pct:.1f}% of reports use new format")

    if legacy_dirs > 0 or legacy_flat > 0:
        click.echo("\n[!] Run 'deepr migrate organize' to clean up legacy reports")


if __name__ == "__main__":
    migrate()
