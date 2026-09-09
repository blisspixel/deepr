"""Legacy report organize must not archive live product roots."""

from click.testing import CliRunner

from deepr.cli.commands.migrate import migrate


def test_organize_preserves_investigations_and_validation(tmp_path) -> None:
    reports = tmp_path / "reports"
    (reports / "investigations" / "inv_1").mkdir(parents=True)
    (reports / "validation" / "run").mkdir(parents=True)
    (reports / "expert-updates").mkdir()
    (reports / "campaigns").mkdir()
    uuid_dir = reports / "123e4567-e89b-12d3-a456-426614174000"
    uuid_dir.mkdir()
    (uuid_dir / "report.md").write_text("legacy", encoding="utf-8")

    result = CliRunner().invoke(migrate, ["organize", "--reports-dir", str(reports)])

    assert result.exit_code == 0
    assert (reports / "investigations" / "inv_1").is_dir()
    assert (reports / "validation" / "run").is_dir()
    assert (reports / "expert-updates").is_dir()
    assert (reports / "campaigns").is_dir()
    assert not uuid_dir.exists()
    assert (reports / "_legacy_archive" / uuid_dir.name / "report.md").is_file()


def test_organize_does_not_move_archive_into_itself(tmp_path) -> None:
    reports = tmp_path / "reports"
    archive = reports / "_legacy_archive"
    archive.mkdir(parents=True)
    (archive / "already.md").write_text("kept", encoding="utf-8")

    result = CliRunner().invoke(migrate, ["organize", "--reports-dir", str(reports)])

    assert result.exit_code == 0
    assert (archive / "already.md").is_file()
    assert not (archive / "_legacy_archive").exists()
