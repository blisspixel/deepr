"""Render expert portraits locally, from what each expert said it looks like.

$0 and offline. Uses Artomate, which is a fully local image generator, so no
metered image API is ever contacted. Deepr's own portrait path stays blocked
for local execution pending a capacity attestation; this is an operator tool
run by hand, not something the app can trigger.

The prompt is built by `deepr.experts.portraits._build_prompt`, so a portrait
generated here is the same prompt the application would use: the expert's own
`appearance` plus the house style, which carries the head-and-shoulders framing
an avatar needs. Passing the bare appearance instead produces a beautiful,
correct, unusable image - the first run came back as a desk scene with no face
in it, because the expert described a situation and nothing asked for a
portrait of the person in it.

    python scripts/render_expert_portraits_local.py            # every named expert
    python scripts/render_expert_portraits_local.py Keel Cairn # just these
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from deepr.experts.expert_layout import self_path
from deepr.experts.paths import canonical_expert_dir, expert_slug
from deepr.experts.portraits import _build_prompt
from deepr.experts.profile_store import ExpertStore

PORTRAITS = Path("data/portraits")
MODEL = "flux2-klein"


def _named_experts() -> list[tuple[str, str, str]]:
    """(directory name, chosen name, appearance) for everyone who has both."""
    root = canonical_expert_dir("probe").parent
    out: list[tuple[str, str, str]] = []
    for directory in sorted(root.iterdir()):
        if not directory.is_dir():
            continue
        try:
            account = json.loads(self_path(directory.name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        chosen = str(account.get("chosen_name") or "").strip()
        appearance = str(account.get("appearance") or "").strip()
        if chosen and appearance:
            out.append((directory.name, chosen, appearance))
    return out


def _render(prompt: str) -> Path | None:
    """One image from the local model, or None if it produced nothing.

    Artomate writes `output/art-<hex>.png` relative to the working directory
    and never overwrites, so rendering into a fresh temporary directory makes
    "the file that appeared" unambiguous.
    """
    with tempfile.TemporaryDirectory() as work:
        result = subprocess.run(
            ["artomate", "imagine", prompt, "model", MODEL, "ratio", "1:1"],
            cwd=work,
            capture_output=True,
            text=True,
            timeout=1800,
        )
        produced = sorted((Path(work) / "output").glob("*.png")) if (Path(work) / "output").is_dir() else []
        if not produced:
            print(f"    no image: {(result.stderr or result.stdout or '').strip()[:160]}")
            return None
        kept = Path(tempfile.mkdtemp()) / produced[0].name
        shutil.copy2(produced[0], kept)
        return kept


def main(argv: list[str]) -> int:
    wanted = {a.lower() for a in argv[1:]}
    experts = [e for e in _named_experts() if not wanted or e[1].lower() in wanted]
    if not experts:
        print("No experts with both a chosen name and an appearance.")
        return 1

    PORTRAITS.mkdir(parents=True, exist_ok=True)
    store = ExpertStore()
    rendered = 0

    for directory, chosen, appearance in experts:
        slug = expert_slug(directory).replace("_", "-")
        print(f"{chosen} ({directory})")
        image = _render(_build_prompt(chosen, None, None, appearance=appearance))
        if image is None:
            continue

        destination = PORTRAITS / f"{slug}.png"
        shutil.copy2(image, destination)
        rendered += 1
        print(f"    {destination}")

        # Point the profile at it, so the roster and the expert page both
        # find it without a second naming convention to keep in sync.
        profile = store.load(directory)
        if profile is not None:
            profile.portrait_url = f"/portraits/{slug}.png"
            store.save(profile)

    print(f"\n{rendered} of {len(experts)} rendered. $0: local model, no API call.")
    return 0 if rendered else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
