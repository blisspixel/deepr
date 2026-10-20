# Replacement rehearsal protocol archive

These are the exact local synthetic inputs used for the 2026-10-20 operational
diagnostic. They replace unrecoverable September inputs openly. They are not
the original S0, a held-out qualification set, an approved rubric or a reviewed
baseline. No answer, answer-to-method binding or assignment key is published.

`frozen-protocol/` preserves the pre-collection draft byte for byte, including
historical status fields and instructions. Its `draft-manifest.json` binds 20
input, policy, plan, draft-criteria and source-preflight files. `REVIEW.md` and
the original manifest are additional snapshot files. `archive-manifest.json`
binds all 22 archived files. Historical `collected_answers: 0` and local paths
describe that earlier snapshot, not the later diagnostic outcome. Consult the
[dated validation record](../../replacement-rehearsal-2026-10-20.md) for the
run's actual status and limits.

The protocol contains three cumulative worlds with 4, 8 and 12 source versions,
12 cases and four methods per case. Sources are invented Rivet documents,
including a scoped revision and a later withdrawal. Semantic expectations and
scoring anchors were not approved before collection. Diagnostic answers cannot
be retroactively promoted to an approved baseline by adding scoring anchors.

The policy pins `qwen3.8:27b` to a full local digest. These files preserve the
protocol, not the model weights. Repeating inference still requires the exact
digest, compatible runtime and bounded local capacity. Do not substitute a
model tag silently. Source preflight can verify the archive without inference:

```python
import hashlib
import json
from pathlib import Path

from deepr.evals.expert_value_sources import load_source_world_preparation

root = Path("docs/validation/artifacts/replacement-rehearsal-2026-10-20")
manifest = json.loads((root / "archive-manifest.json").read_bytes())
for name, expected in manifest["files"].items():
    assert hashlib.sha256((root / "frozen-protocol" / name).read_bytes()).hexdigest() == expected
inputs = root / "frozen-protocol/inputs"
load_source_world_preparation(inputs / "index.json", inputs)
```

Run that snippet with the locked development environment from the repository
root. It hashes local files and loads the existing source-preparation seam; it
does not contact a model or provider.

Aggregate receipts are separate from that frozen protocol. Their hashes are
in `evidence-manifest.json`:

- [Pre-collection decision](decision-before-collection.json), with the source
  commit, model pin, input hashes and explicit unapproved-review status.
- [Independent terminal audit](audit-receipt.json), including the failed
  worker, unknown usage, native ledger joins and integrity limits.
- [Read-only reporting projection](reporting-offline-projection.json), binding
  the repaired reporter and original worker artifacts without rewriting them.
- [Maintenance timeout](maintenance-timeout.json) and
  [concurrent workload](concurrent-workload.json), preserving the failure and
  the limits on timing comparisons.
- [Review preparation](review-preparation-receipt.json), binding the unlabelled
  private packet without exposing answers or method assignments.

These are execution and retention observations. They contain no semantic
labels, approved baseline result or improvement verdict.
