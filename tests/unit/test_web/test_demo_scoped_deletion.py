"""Demo routes must never destroy real research data.

An earlier /api/demo/load deleted every queue row and every report directory
on disk as a side effect of seeding samples - "try the demo" silently
destroyed all paid research artifacts. Demo data is now namespaced with a
"demo-" prefix and both demo routes may only touch that namespace.
"""

from __future__ import annotations

import re

from deepr.web import app as web_app


def test_demo_load_only_deletes_demo_namespace_in_source() -> None:
    # Structural guard: the demo routes must scope their SQL deletes to the
    # demo- namespace. A bare DELETE FROM research_queue in app.py is the
    # artifact-destroyer regression this test exists to block.
    source = open(web_app.__file__, encoding="utf-8").read()
    bare_deletes = [m for m in re.finditer(r"DELETE FROM research_queue(?!\s+WHERE\s+id\s+LIKE\s+'demo-%')", source)]
    assert not bare_deletes, "found unscoped research_queue DELETE; demo routes must only touch demo-% ids"


def test_demo_report_rmtree_is_prefix_scoped_in_source() -> None:
    # Both demo routes iterate storage dirs and rmtree; every such loop must
    # filter on the demo- prefix before deleting.
    source = open(web_app.__file__, encoding="utf-8").read()
    rmtree_count = source.count("rmtree(job_dir")
    scoped_count = source.count('job_dir.name.startswith("demo-")')
    assert rmtree_count > 0
    assert scoped_count >= rmtree_count, "every job_dir rmtree must be scoped to the demo- namespace"


def test_demo_jobs_are_namespaced_in_source() -> None:
    source = open(web_app.__file__, encoding="utf-8").read()
    assert 'f"demo-{uuid.uuid4()}"' in source, "demo jobs must carry the demo- id prefix"
