"""Import every module that registers a command on the `expert` group.

These imports used to sit at the bottom of ``experts.py``, which is
grandfathered at a size cap it must not exceed. That made adding a command a
guaranteed ratchet failure: the command lives in its own module for exactly
the size reason, and then its one-line registration pushes the oversized file
over anyway.

Collecting them here means ``experts.py`` carries one import instead of
twenty-odd, and adding a command touches a file with room in it.

Import for side effects only. Each module decorates its function with
``@expert.command(...)`` at import time, so importing is the registration.
Nothing here should be called.
"""

from __future__ import annotations

from deepr.cli.commands.semantic import expert_blueprint as _expert_blueprint  # noqa: F401
from deepr.cli.commands.semantic import expert_cleanup as _expert_cleanup  # noqa: F401
from deepr.cli.commands.semantic import expert_consult as _expert_consult  # noqa: F401
from deepr.cli.commands.semantic import expert_consult_quality as _expert_consult_quality  # noqa: F401
from deepr.cli.commands.semantic import expert_consult_traces as _expert_consult_traces  # noqa: F401
from deepr.cli.commands.semantic import expert_fleet_health as _expert_fleet_health  # noqa: F401
from deepr.cli.commands.semantic import expert_freshness as _expert_freshness  # noqa: F401
from deepr.cli.commands.semantic import expert_gap_routes as _expert_gap_routes  # noqa: F401
from deepr.cli.commands.semantic import expert_graph as _expert_graph  # noqa: F401
from deepr.cli.commands.semantic import expert_learn_web as _expert_learn_web  # noqa: F401
from deepr.cli.commands.semantic import expert_loop_status as _expert_loop_status  # noqa: F401
from deepr.cli.commands.semantic import expert_maintenance as _expert_maintenance  # noqa: F401
from deepr.cli.commands.semantic import expert_memory_card as _expert_memory_card  # noqa: F401
from deepr.cli.commands.semantic import expert_okf as _expert_okf  # noqa: F401
from deepr.cli.commands.semantic import expert_outcomes as _expert_outcomes  # noqa: F401
from deepr.cli.commands.semantic import expert_perspective as _expert_perspective  # noqa: F401
from deepr.cli.commands.semantic import expert_portrait as _expert_portrait  # noqa: F401
from deepr.cli.commands.semantic import expert_practice as _expert_practice  # noqa: F401
from deepr.cli.commands.semantic import expert_profile_card_cmd as _expert_profile_card_cmd  # noqa: F401
from deepr.cli.commands.semantic import expert_quality as _expert_quality  # noqa: F401
from deepr.cli.commands.semantic import expert_self_model as _expert_self_model  # noqa: F401
from deepr.cli.commands.semantic import expert_source as _expert_source  # noqa: F401
from deepr.cli.commands.semantic import expert_status as _expert_status  # noqa: F401
from deepr.cli.commands.semantic import expert_study as _expert_study  # noqa: F401
from deepr.cli.commands.semantic import expert_validate_export as _expert_validate_export  # noqa: F401
from deepr.cli.commands.semantic import expert_viva as _expert_viva  # noqa: F401
