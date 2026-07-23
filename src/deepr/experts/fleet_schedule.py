"""Host-scheduler recipe emitter for unattended fleet maintenance.

The overlap guard and startup jitter (``loop_lock.py``) and the delta-driven,
idempotent maintenance verbs only matter once something runs them on a cadence.
Per "hosts own the schedule, Deepr owns the verbs", Deepr does not run its own
daemon - it emits the correct *host* recipe (Windows Task Scheduler, cron,
systemd) for the operator to install, and steps out.

The recipes are tuned for **catch-up, not punctuality**, because that is the only
honest design on real machines: Windows 11 Modern Standby cannot guarantee an
exact-time wake, and a laptop is often asleep at 03:00. Deepr's verbs are
delta-driven and idempotent, so a missed run simply catches up on the next wake
with no double-spend. Concretely that means:

- Windows: ``StartWhenAvailable`` (run after a missed start), ``WakeToRun``,
  run whether or not the user is logged on, do not stop on battery, and
  ``IgnoreNew`` so a still-running job is never double-started.
- systemd: ``Persistent=true`` (fire on next boot if the timer elapsed while
  off), ``WakeSystem``, and ``RandomizedDelaySec`` to spread a roster.
- cron: a plain line; cron has no catch-up or jitter of its own, so the recipe
  says so and points at the systemd timer where catch-up matters.

This module is pure: it generates recipe text from a spec and never installs
anything (installation is a privileged, host-specific side-effect the operator
performs). Deterministic, ``$0``, no model judgment - workflow form per
docs/plans/AGENTIC_BALANCE.md.
"""

from __future__ import annotations

import shlex
import subprocess
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from re import fullmatch
from xml.sax.saxutils import escape as _xml_escape

SCHEDULE_PLATFORMS = ("windows", "cron", "systemd")
CADENCES = ("hourly", "daily")

# A fixed, safely-in-the-past start date. Task Scheduler and systemd use the
# time-of-day for recurring triggers; the date only has to predate "now", so a
# constant keeps the emitted recipe deterministic (stable across runs and tests).
_START_DATE = "2026-01-01"
_MAX_SCHEDULE_NAME_CHARS = 64
_SCHEDULE_NAME_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_.-]*"
_WINDOWS_RESERVED_FILENAMES = {
    "aux",
    "con",
    "nul",
    "prn",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}


def resolve_platform(platform: str, *, system: str) -> str:
    """Map ``platform`` (possibly ``"auto"``) to a concrete recipe target.

    ``system`` is a ``sys.platform``-style string. ``auto`` selects Windows Task
    Scheduler on Windows, systemd on Linux, and cron on macOS. Other hosts must
    choose an explicit target because guessing systemd would emit an unusable
    recipe on platforms that do not provide it.
    """
    if platform != "auto":
        if platform not in SCHEDULE_PLATFORMS:
            raise ValueError(f"unknown platform: {platform!r} (choose from {', '.join(SCHEDULE_PLATFORMS)})")
        return platform
    normalized_system = system.casefold()
    if normalized_system.startswith("win"):
        return "windows"
    if normalized_system.startswith("linux"):
        return "systemd"
    if normalized_system.startswith("darwin"):
        return "cron"
    raise ValueError(
        f"cannot auto-detect a supported scheduler for platform {system!r}; "
        f"choose --platform from {', '.join(SCHEDULE_PLATFORMS)}"
    )


def _validate_time(at: str) -> tuple[int, int]:
    parts = at.split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise ValueError(f"--at must be HH:MM, got {at!r}")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"--at must be a valid 24h time, got {at!r}")
    return hour, minute


def _split_command(command: str) -> list[str]:
    """Split portable quoted argv while preserving literal path backslashes."""
    lexer = shlex.shlex(command, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    lexer.escape = ""
    return list(lexer)


def _powershell_literal(value: str) -> str:
    """Quote one literal PowerShell argument without interpolation."""
    return "'" + value.replace("'", "''") + "'"


def _systemd_literal(value: str) -> str:
    """Quote one systemd unit argument while preserving its exact value."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("%", "%%").replace("$", "$$")
    return f'"{escaped}"'


@dataclass(frozen=True)
class ScheduleSpec:
    """A validated request for one scheduled maintenance job."""

    command: str
    cadence: str = "daily"
    at: str = "03:00"
    name: str = "deepr-fleet"
    jitter_minutes: int = 15

    def __post_init__(self) -> None:
        if not isinstance(self.command, str) or not self.command.strip():
            raise ValueError("command is required")
        if any(unicodedata.category(character).startswith("C") for character in self.command):
            raise ValueError("command must not contain control characters or line breaks")
        try:
            argv = _split_command(self.command)
        except ValueError:
            raise ValueError("command must use balanced quoted arguments") from None
        if not argv:
            raise ValueError("command is required")
        if (
            not isinstance(self.name, str)
            or len(self.name) > _MAX_SCHEDULE_NAME_CHARS
            or fullmatch(_SCHEDULE_NAME_PATTERN, self.name) is None
            or self.name in {".", ".."}
            or self.name.endswith(".")
            or self.name.partition(".")[0].casefold() in _WINDOWS_RESERVED_FILENAMES
        ):
            raise ValueError(
                "name must be 1-64 ASCII letters, digits, dots, underscores, or hyphens, "
                "start with a letter or digit, and identify one task without a path"
            )
        if self.cadence not in CADENCES:
            raise ValueError(f"cadence must be one of {', '.join(CADENCES)}, got {self.cadence!r}")
        if self.jitter_minutes < 0:
            raise ValueError("jitter_minutes must be non-negative")
        cadence_minutes = 60 if self.cadence == "hourly" else 24 * 60
        if self.jitter_minutes >= cadence_minutes:
            raise ValueError("jitter_minutes must be shorter than the selected cadence")
        _validate_time(self.at)

    @property
    def hour(self) -> int:
        return _validate_time(self.at)[0]

    @property
    def minute(self) -> int:
        return _validate_time(self.at)[1]

    @property
    def argv(self) -> list[str]:
        """Return the validated command as executable plus argument values."""
        return _split_command(self.command)


@dataclass(frozen=True)
class ScheduleRecipe:
    """An emitted recipe: one or more files plus install instructions."""

    platform: str
    files: dict[str, str] = field(default_factory=dict)
    inline: str = ""  # for cron, which is a line not a file
    instructions: str = ""


def _windows_task_xml(spec: ScheduleSpec) -> str:
    argv = spec.argv
    # Escape every value derived from user input before it enters the XML, so a
    # command containing & < > (e.g. a shell redirect) cannot produce malformed
    # XML that schtasks would reject.
    executable = _xml_escape(argv[0] if argv else "deepr")
    arguments = _xml_escape(subprocess.list2cmdline(argv[1:]))
    description = _xml_escape(f"Deepr fleet maintenance ({spec.command})")
    uri_name = _xml_escape(spec.name)
    random_delay = f"PT{spec.jitter_minutes}M"

    if spec.cadence == "daily":
        trigger = (
            "    <CalendarTrigger>\n"
            f"      <StartBoundary>{_START_DATE}T{spec.at}:00</StartBoundary>\n"
            "      <Enabled>true</Enabled>\n"
            f"      <RandomDelay>{random_delay}</RandomDelay>\n"
            "      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>\n"
            "    </CalendarTrigger>"
        )
    else:  # hourly
        trigger = (
            "    <TimeTrigger>\n"
            f"      <StartBoundary>{_START_DATE}T00:00:00</StartBoundary>\n"
            "      <Enabled>true</Enabled>\n"
            f"      <RandomDelay>{random_delay}</RandomDelay>\n"
            "      <Repetition>\n"
            "        <Interval>PT1H</Interval>\n"
            "        <StopAtDurationEnd>false</StopAtDurationEnd>\n"
            "      </Repetition>\n"
            "    </TimeTrigger>"
        )

    arguments_line = f"      <Arguments>{arguments}</Arguments>\n" if arguments else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        "  <RegistrationInfo>\n"
        f"    <Description>{description}</Description>\n"
        f"    <URI>\\{uri_name}</URI>\n"
        "  </RegistrationInfo>\n"
        "  <Triggers>\n"
        f"{trigger}\n"
        "  </Triggers>\n"
        "  <Principals>\n"
        '    <Principal id="Author">\n'
        # S4U: run whether or not the user is logged on, without storing a password.
        "      <LogonType>S4U</LogonType>\n"
        "      <RunLevel>LeastPrivilege</RunLevel>\n"
        "    </Principal>\n"
        "  </Principals>\n"
        "  <Settings>\n"
        # IgnoreNew: never double-start a job that is still running (the
        # scheduler-level overlap guard, complementing the in-verb filelock).
        "    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n"
        "    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n"
        "    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n"
        "    <StartWhenAvailable>true</StartWhenAvailable>\n"
        "    <WakeToRun>true</WakeToRun>\n"
        "    <Enabled>true</Enabled>\n"
        "    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>\n"
        "  </Settings>\n"
        '  <Actions Context="Author">\n'
        "    <Exec>\n"
        f"      <Command>{executable}</Command>\n"
        f"{arguments_line}"
        "    </Exec>\n"
        "  </Actions>\n"
        "</Task>\n"
    )


def _crontab_line(spec: ScheduleSpec) -> str:
    if spec.cadence == "daily":
        schedule = f"{spec.minute} {spec.hour} * * *"
    else:  # hourly
        schedule = f"{spec.minute} * * * *"
    # cron consumes unescaped percent signs before the shell sees the command,
    # even when the percent appears inside quotes. Prefix each one so the shell
    # receives the caller's literal value rather than a truncated command plus
    # injected standard input.
    command = spec.command.replace("%", r"\%")
    return f"{schedule} {command}"


def _systemd_units(spec: ScheduleSpec) -> dict[str, str]:
    if spec.cadence == "daily":
        on_calendar = f"*-*-* {spec.at}:00"
    else:  # hourly
        on_calendar = f"*-*-* *:{spec.minute:02d}:00"

    exec_start = " ".join(_systemd_literal(argument) for argument in spec.argv)
    service = (
        "[Unit]\n"
        f"Description=Deepr fleet maintenance ({spec.command})\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"ExecStart={exec_start}\n"
    )
    timer = (
        "[Unit]\n"
        "Description=Deepr fleet maintenance schedule\n"
        "\n"
        "[Timer]\n"
        f"OnCalendar={on_calendar}\n"
        # Persistent: fire on next boot if the timer elapsed while powered off.
        "Persistent=true\n"
        f"RandomizedDelaySec={spec.jitter_minutes * 60}\n"
        "WakeSystem=true\n"
        "\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )
    return {f"{spec.name}.service": service, f"{spec.name}.timer": timer}


def _artifact_reference(filename: str, output_directory: str | Path | None) -> Path:
    if output_directory is None:
        return Path(filename)
    return Path(output_directory).resolve() / filename


def render_recipe(
    platform: str,
    spec: ScheduleSpec,
    *,
    output_directory: str | Path | None = None,
) -> ScheduleRecipe:
    """Render a recipe and output-aware manual installation instructions."""
    if platform == "windows":
        filename = f"{spec.name}.xml"
        xml_reference = _powershell_literal(str(_artifact_reference(filename, output_directory)))
        task_reference = _powershell_literal(spec.name)
        return ScheduleRecipe(
            platform="windows",
            files={filename: _windows_task_xml(spec)},
            instructions=(
                "Register the task from PowerShell as your user:\n"
                f'  schtasks /Create /TN {task_reference} /XML {xml_reference} /RU "$env:USERNAME"\n'
                "Optional test run (executes the scheduled command now):\n"
                f"  schtasks /Run /TN {task_reference}\n"
                "Inspect registration and Last Run Result:\n"
                f"  schtasks /Query /TN {task_reference} /V /FO LIST\n"
                f"Remove: schtasks /Delete /TN {task_reference} /F"
            ),
        )
    if platform == "systemd":
        units = _systemd_units(spec)
        service_name = f"{spec.name}.service"
        timer_name = f"{spec.name}.timer"
        service_reference = shlex.quote(str(_artifact_reference(service_name, output_directory)))
        timer_reference = shlex.quote(str(_artifact_reference(timer_name, output_directory)))
        return ScheduleRecipe(
            platform="systemd",
            files=units,
            instructions=(
                "Install as a user timer:\n"
                "  mkdir -p ~/.config/systemd/user\n"
                f"  cp {service_reference} {timer_reference} ~/.config/systemd/user/\n"
                "  systemctl --user daemon-reload\n"
                f"  systemctl --user enable --now {timer_name}\n"
                "Optional test run (executes the scheduled command now):\n"
                f"  systemctl --user start {service_name}\n"
                "Inspect timer, latest service result, and logs:\n"
                f"  systemctl --user status {timer_name} {service_name}\n"
                f"  journalctl --user -u {service_name} --since today\n"
                "Optional logged-out operation (may require administrator authorization):\n"
                '  loginctl enable-linger "$USER"\n'
                f"Remove: systemctl --user disable --now {timer_name}"
            ),
        )
    if platform == "cron":
        if output_directory is None:
            install_step = "  crontab -e   # then paste the line above"
        else:
            cron_reference = shlex.quote(str(_artifact_reference(f"{spec.name}.cron", output_directory)))
            install_step = f"  Review {cron_reference}, then use crontab -e to add that line"
        return ScheduleRecipe(
            platform="cron",
            inline=_crontab_line(spec),
            instructions=(
                "Add the line to your crontab:\n"
                f"{install_step}\n"
                "Optional test run (executes the scheduled command now):\n"
                f"  {spec.command}\n"
                "Inspect installed entries: crontab -l\n"
                "Note: plain cron has no catch-up for missed runs (asleep/off) and no\n"
                "jitter. On Linux, prefer --platform systemd for Persistent catch-up and\n"
                "RandomizedDelaySec spreading. macOS currently uses cron as a limited\n"
                "fallback because native launchd recipe emission is not shipped."
            ),
        )
    raise ValueError(f"unknown platform: {platform!r}")
