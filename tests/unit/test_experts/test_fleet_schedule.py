"""Tests for the host-scheduler recipe emitter."""

from __future__ import annotations

import pytest

from deepr.experts.fleet_schedule import (
    ScheduleSpec,
    render_recipe,
    resolve_platform,
)


class TestResolvePlatform:
    def test_auto_picks_windows_on_win32(self):
        assert resolve_platform("auto", system="win32") == "windows"

    def test_auto_picks_systemd_on_linux(self):
        assert resolve_platform("auto", system="linux") == "systemd"

    def test_auto_picks_cron_on_macos(self):
        assert resolve_platform("auto", system="darwin") == "cron"

    def test_auto_rejects_an_unknown_host(self):
        with pytest.raises(ValueError, match="cannot auto-detect"):
            resolve_platform("auto", system="plan9")

    def test_explicit_platform_is_passed_through(self):
        assert resolve_platform("cron", system="win32") == "cron"

    def test_unknown_platform_rejected(self):
        with pytest.raises(ValueError, match="unknown platform"):
            resolve_platform("k8s", system="linux")


class TestScheduleSpecValidation:
    def test_rejects_empty_command(self):
        with pytest.raises(ValueError, match="command is required"):
            ScheduleSpec(command="   ")

    def test_rejects_bad_cadence(self):
        with pytest.raises(ValueError, match="cadence must be one of"):
            ScheduleSpec(command="deepr fleet status", cadence="weekly")

    def test_rejects_bad_time(self):
        with pytest.raises(ValueError, match="HH:MM"):
            ScheduleSpec(command="deepr fleet status", at="3am")
        with pytest.raises(ValueError, match="valid 24h time"):
            ScheduleSpec(command="deepr fleet status", at="25:00")

    def test_rejects_negative_jitter(self):
        with pytest.raises(ValueError, match="jitter_minutes"):
            ScheduleSpec(command="deepr fleet status", jitter_minutes=-1)

    @pytest.mark.parametrize(("cadence", "jitter"), [("hourly", 60), ("daily", 1440)])
    def test_rejects_jitter_that_reaches_the_next_interval(self, cadence, jitter):
        with pytest.raises(ValueError, match="shorter than the selected cadence"):
            ScheduleSpec(command="deepr fleet status", cadence=cadence, jitter_minutes=jitter)

    @pytest.mark.parametrize(
        "name",
        [
            "",
            ".",
            "..",
            "../outside",
            r"..\outside",
            "fleet name",
            "fleet;echo",
            "fleet\nname",
            "a" * 65,
            "CON",
            "CON.backup",
            "lpt9",
            "lpt9.logs",
        ],
    )
    def test_rejects_unsafe_scheduler_name(self, name):
        with pytest.raises(ValueError, match="name"):
            ScheduleSpec(command="deepr fleet status", name=name)

    @pytest.mark.parametrize("command", ["deepr fleet status\nwhoami", "deepr\rstatus", "deepr\x1b[31m"])
    def test_rejects_control_characters_in_command(self, command):
        with pytest.raises(ValueError, match="control"):
            ScheduleSpec(command=command)

    def test_rejects_unbalanced_command_quotes_during_validation(self):
        with pytest.raises(ValueError, match="quoted"):
            ScheduleSpec(command="deepr expert sync 'unfinished")

    def test_argv_splits_command(self):
        spec = ScheduleSpec(command="deepr expert sync 'AI Policy Expert' --scheduled -y")
        assert spec.argv == ["deepr", "expert", "sync", "AI Policy Expert", "--scheduled", "-y"]

    def test_argv_preserves_windows_backslash_paths(self):
        spec = ScheduleSpec(command=r'"C:\Program Files\Deepr\deepr.exe" fleet status C:\Reports\status.json')
        assert spec.argv == [
            r"C:\Program Files\Deepr\deepr.exe",
            "fleet",
            "status",
            r"C:\Reports\status.json",
        ]


class TestWindowsRecipe:
    def _xml(self, **kwargs) -> str:
        spec = ScheduleSpec(command="deepr fleet status", **kwargs)
        recipe = render_recipe("windows", spec)
        return recipe.files["deepr-fleet.xml"]

    def test_has_catch_up_and_power_flags(self):
        xml = self._xml()
        assert "<StartWhenAvailable>true</StartWhenAvailable>" in xml
        assert "<WakeToRun>true</WakeToRun>" in xml
        assert "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>" in xml
        assert "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>" in xml

    def test_does_not_double_start(self):
        assert "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>" in self._xml()

    def test_runs_whether_logged_on(self):
        assert "<LogonType>S4U</LogonType>" in self._xml()

    def test_splits_command_into_exec_and_arguments(self):
        xml = self._xml()
        assert "<Command>deepr</Command>" in xml
        assert "<Arguments>fleet status</Arguments>" in xml

    def test_preserves_a_spaced_argument_with_windows_quoting(self):
        spec = ScheduleSpec(command="deepr expert sync 'AI Policy Expert' --scheduled -y")
        xml = render_recipe("windows", spec).files["deepr-fleet.xml"]
        assert '<Arguments>expert sync "AI Policy Expert" --scheduled -y</Arguments>' in xml

    def test_preserves_windows_executable_and_argument_paths(self):
        spec = ScheduleSpec(command=r'"C:\Program Files\Deepr\deepr.exe" fleet status C:\Reports\status.json')
        xml = render_recipe("windows", spec).files["deepr-fleet.xml"]
        assert r"<Command>C:\Program Files\Deepr\deepr.exe</Command>" in xml
        assert r"<Arguments>fleet status C:\Reports\status.json</Arguments>" in xml

    def test_daily_uses_calendar_trigger_at_the_chosen_time(self):
        xml = self._xml(cadence="daily", at="04:30")
        assert "<CalendarTrigger>" in xml
        assert "<StartBoundary>2026-01-01T04:30:00</StartBoundary>" in xml
        assert "<DaysInterval>1</DaysInterval>" in xml

    def test_hourly_uses_repetition_interval(self):
        xml = self._xml(cadence="hourly")
        assert "<Interval>PT1H</Interval>" in xml

    def test_jitter_becomes_random_delay(self):
        assert "<RandomDelay>PT20M</RandomDelay>" in self._xml(jitter_minutes=20)

    def test_declares_utf8_to_match_the_written_file(self):
        assert self._xml().startswith('<?xml version="1.0" encoding="UTF-8"?>')

    def test_escapes_xml_special_chars_in_the_command(self):
        spec = ScheduleSpec(command="deepr fleet status > log.txt && echo done")
        xml = render_recipe("windows", spec).files["deepr-fleet.xml"]
        # The raw & / > must not appear unescaped inside the generated XML.
        assert "&amp;&amp;" in xml
        assert "&gt;" in xml
        assert " && echo" not in xml


class TestCronRecipe:
    def test_daily_line(self):
        spec = ScheduleSpec(command="deepr fleet status", cadence="daily", at="03:15")
        recipe = render_recipe("cron", spec)
        assert recipe.inline == "15 3 * * * deepr fleet status"
        assert not recipe.files

    def test_hourly_line(self):
        spec = ScheduleSpec(command="deepr fleet status", cadence="hourly", at="00:05")
        recipe = render_recipe("cron", spec)
        assert recipe.inline == "5 * * * * deepr fleet status"

    def test_warns_about_no_catch_up(self):
        recipe = render_recipe("cron", ScheduleSpec(command="deepr fleet status"))
        assert "no catch-up" in recipe.instructions

    def test_escapes_percent_before_cron_interprets_the_command(self):
        spec = ScheduleSpec(command="deepr expert consult 'Is coverage 100%?'")
        recipe = render_recipe("cron", spec)
        assert "Is coverage 100\\%?" in recipe.inline
        assert "100%?" not in recipe.inline


class TestSystemdRecipe:
    def _units(self, **kwargs) -> dict[str, str]:
        spec = ScheduleSpec(command="deepr fleet status", **kwargs)
        return render_recipe("systemd", spec).files

    def test_emits_service_and_timer(self):
        units = self._units()
        assert set(units) == {"deepr-fleet.service", "deepr-fleet.timer"}

    def test_timer_has_persistent_catch_up_and_wake(self):
        timer = self._units()["deepr-fleet.timer"]
        assert "Persistent=true" in timer
        assert "WakeSystem=true" in timer

    def test_jitter_becomes_randomized_delay_seconds(self):
        timer = self._units(jitter_minutes=15)["deepr-fleet.timer"]
        assert "RandomizedDelaySec=900" in timer

    def test_daily_oncalendar(self):
        timer = self._units(cadence="daily", at="03:00")["deepr-fleet.timer"]
        assert "OnCalendar=*-*-* 03:00:00" in timer

    def test_hourly_oncalendar(self):
        timer = self._units(cadence="hourly", at="00:07")["deepr-fleet.timer"]
        assert "OnCalendar=*-*-* *:07:00" in timer

    def test_service_runs_the_command(self):
        service = self._units()["deepr-fleet.service"]
        assert 'ExecStart="deepr" "fleet" "status"' in service
        assert "Type=oneshot" in service

    def test_service_preserves_a_spaced_argument(self):
        spec = ScheduleSpec(command="deepr expert sync 'AI Policy Expert' --scheduled -y")
        service = render_recipe("systemd", spec).files["deepr-fleet.service"]
        assert 'ExecStart="deepr" "expert" "sync" "AI Policy Expert" "--scheduled" "-y"' in service

    def test_service_preserves_literal_systemd_expansion_characters(self):
        spec = ScheduleSpec(command="deepr inspect '$HOME' '100%'")
        service = render_recipe("systemd", spec).files["deepr-fleet.service"]
        assert 'ExecStart="deepr" "inspect" "$$HOME" "100%%"' in service

    def test_service_uses_systemd_escaping_for_backslashes_and_quotes(self):
        spec = ScheduleSpec(command=r"""deepr inspect 'line\nnext' "O'Brien" 'say "hello"' """)
        service = render_recipe("systemd", spec).files["deepr-fleet.service"]
        assert r'"line\\nnext"' in service
        assert '"O\'Brien"' in service
        assert r'"say \"hello\""' in service

    def test_install_instructions_reload_and_expose_first_run_diagnostics(self):
        recipe = render_recipe("systemd", ScheduleSpec(command="deepr fleet status"))
        assert recipe.instructions.index("daemon-reload") < recipe.instructions.index("enable --now")
        assert "executes the scheduled command now" in recipe.instructions
        assert "journalctl --user -u deepr-fleet.service" in recipe.instructions


def test_output_aware_windows_instructions_reference_the_written_xml(tmp_path):
    recipe = render_recipe("windows", ScheduleSpec(command="deepr fleet status"), output_directory=tmp_path)
    assert str(tmp_path.resolve() / "deepr-fleet.xml") in recipe.instructions


def test_windows_instructions_quote_powershell_metacharacters_in_output_path(tmp_path):
    output = tmp_path / "semi;whoami;&$`O'Brien"
    recipe = render_recipe("windows", ScheduleSpec(command="deepr fleet status"), output_directory=output)
    expected_path = str(output.resolve() / "deepr-fleet.xml").replace("'", "''")
    assert f"/XML '{expected_path}'" in recipe.instructions


def test_output_aware_systemd_instructions_reference_both_written_units(tmp_path):
    recipe = render_recipe("systemd", ScheduleSpec(command="deepr fleet status"), output_directory=tmp_path)
    assert str(tmp_path.resolve() / "deepr-fleet.service") in recipe.instructions
    assert str(tmp_path.resolve() / "deepr-fleet.timer") in recipe.instructions


def test_custom_name_flows_into_filenames_and_units():
    spec = ScheduleSpec(command="deepr fleet status", name="deepr-roster")
    win = render_recipe("windows", spec)
    sysd = render_recipe("systemd", spec)
    assert "deepr-roster.xml" in win.files
    assert set(sysd.files) == {"deepr-roster.service", "deepr-roster.timer"}


def test_render_recipe_rejects_unknown_platform():
    with pytest.raises(ValueError, match="unknown platform"):
        render_recipe("k8s", ScheduleSpec(command="deepr fleet status"))
