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

    def test_auto_picks_systemd_elsewhere(self):
        assert resolve_platform("auto", system="linux") == "systemd"
        assert resolve_platform("auto", system="darwin") == "systemd"

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

    def test_argv_splits_command(self):
        spec = ScheduleSpec(command="deepr expert sync 'AI Policy Expert' --scheduled -y")
        assert spec.argv == ["deepr", "expert", "sync", "AI Policy Expert", "--scheduled", "-y"]


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
        assert "ExecStart=deepr fleet status" in service
        assert "Type=oneshot" in service


def test_custom_name_flows_into_filenames_and_units():
    spec = ScheduleSpec(command="deepr fleet status", name="deepr-roster")
    win = render_recipe("windows", spec)
    sysd = render_recipe("systemd", spec)
    assert "deepr-roster.xml" in win.files
    assert set(sysd.files) == {"deepr-roster.service", "deepr-roster.timer"}


def test_render_recipe_rejects_unknown_platform():
    with pytest.raises(ValueError, match="unknown platform"):
        render_recipe("k8s", ScheduleSpec(command="deepr fleet status"))
