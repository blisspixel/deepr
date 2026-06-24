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
from dataclasses import dataclass, field
from xml.sax.saxutils import escape as _xml_escape

SCHEDULE_PLATFORMS = ("windows", "cron", "systemd")
CADENCES = ("hourly", "daily")

# A fixed, safely-in-the-past start date. Task Scheduler and systemd use the
# time-of-day for recurring triggers; the date only has to predate "now", so a
# constant keeps the emitted recipe deterministic (stable across runs and tests).
_START_DATE = "2026-01-01"


def resolve_platform(platform: str, *, system: str) -> str:
    """Map ``platform`` (possibly ``"auto"``) to a concrete recipe target.

    ``system`` is a ``sys.platform``-style string; ``auto`` picks Windows on
    ``win32`` and systemd elsewhere (the modern Linux default; cron stays an
    explicit choice).
    """
    if platform != "auto":
        if platform not in SCHEDULE_PLATFORMS:
            raise ValueError(f"unknown platform: {platform!r} (choose from {', '.join(SCHEDULE_PLATFORMS)})")
        return platform
    return "windows" if system.startswith("win") else "systemd"


def _validate_time(at: str) -> tuple[int, int]:
    parts = at.split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise ValueError(f"--at must be HH:MM, got {at!r}")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"--at must be a valid 24h time, got {at!r}")
    return hour, minute


@dataclass(frozen=True)
class ScheduleSpec:
    """A validated request for one scheduled maintenance job."""

    command: str
    cadence: str = "daily"
    at: str = "03:00"
    name: str = "deepr-fleet"
    jitter_minutes: int = 15

    def __post_init__(self) -> None:
        if not self.command.strip():
            raise ValueError("command is required")
        if self.cadence not in CADENCES:
            raise ValueError(f"cadence must be one of {', '.join(CADENCES)}, got {self.cadence!r}")
        if self.jitter_minutes < 0:
            raise ValueError("jitter_minutes must be non-negative")
        _validate_time(self.at)

    @property
    def hour(self) -> int:
        return _validate_time(self.at)[0]

    @property
    def minute(self) -> int:
        return _validate_time(self.at)[1]

    @property
    def argv(self) -> list[str]:
        """The command split into executable + arguments (POSIX tokenization)."""
        return shlex.split(self.command)


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
    arguments = _xml_escape(" ".join(argv[1:]))
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
    return f"{schedule} {spec.command}"


def _systemd_units(spec: ScheduleSpec) -> dict[str, str]:
    if spec.cadence == "daily":
        on_calendar = f"*-*-* {spec.at}:00"
    else:  # hourly
        on_calendar = f"*-*-* *:{spec.minute:02d}:00"

    service = (
        "[Unit]\n"
        f"Description=Deepr fleet maintenance ({spec.command})\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"ExecStart={spec.command}\n"
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


def render_recipe(platform: str, spec: ScheduleSpec) -> ScheduleRecipe:
    """Render the host-scheduler recipe for ``platform`` (already resolved)."""
    if platform == "windows":
        filename = f"{spec.name}.xml"
        return ScheduleRecipe(
            platform="windows",
            files={filename: _windows_task_xml(spec)},
            instructions=(
                f"Register the task (one line, run as your user):\n"
                f"  schtasks /Create /TN {spec.name} /XML {filename} /RU $env:USERNAME\n"
                f"Inspect:  schtasks /Query /TN {spec.name} /V /FO LIST\n"
                f"Remove:   schtasks /Delete /TN {spec.name} /F"
            ),
        )
    if platform == "systemd":
        units = _systemd_units(spec)
        return ScheduleRecipe(
            platform="systemd",
            files=units,
            instructions=(
                f"Install as a user timer (no root, runs while you are logged in):\n"
                f"  mkdir -p ~/.config/systemd/user\n"
                f"  cp {spec.name}.service {spec.name}.timer ~/.config/systemd/user/\n"
                f"  systemctl --user enable --now {spec.name}.timer\n"
                f"  loginctl enable-linger $USER   # let it run while you are logged out\n"
                f"Inspect:  systemctl --user list-timers {spec.name}.timer\n"
                f"Remove:   systemctl --user disable --now {spec.name}.timer"
            ),
        )
    if platform == "cron":
        return ScheduleRecipe(
            platform="cron",
            inline=_crontab_line(spec),
            instructions=(
                "Add the line to your crontab:\n"
                "  crontab -e   # then paste the line above\n"
                "Note: plain cron has no catch-up for missed runs (asleep/off) and no\n"
                "jitter. On a laptop, prefer the systemd timer (--platform systemd) for\n"
                "Persistent catch-up and RandomizedDelaySec spreading."
            ),
        )
    raise ValueError(f"unknown platform: {platform!r}")
