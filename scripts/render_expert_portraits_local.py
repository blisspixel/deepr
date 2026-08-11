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
import subprocess
import sys
import tempfile
from pathlib import Path

from deepr.experts.expert_layout import self_path
from deepr.experts.paths import canonical_expert_dir, expert_slug
from deepr.experts.portraits import _build_prompt, default_portraits_dir
from deepr.experts.profile_store import ExpertStore

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


def _render(prompt: str) -> bytes | None:
    """The bytes of one image from the local model, or None if it produced none.

    Artomate writes `output/art-<hex>.png` relative to the working directory
    and never overwrites, so rendering into a fresh temporary directory makes
    "the file that appeared" unambiguous.
    """
    # ignore_cleanup_errors, because Artomate leaves a lock file inside its
    # own output directory and Windows refuses to remove a directory holding an
    # open handle. Without it the render succeeds and the script dies clearing
    # up after itself, losing the image it just spent five minutes on.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as work:
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
        # Read the bytes out rather than copying to a second temporary
        # directory: the previous form leaked one directory per render, since
        # nothing ever removed it.
        return produced[0].read_bytes()


def main(argv: list[str]) -> int:
    wanted = {a.lower() for a in argv[1:]}

    # Matched on the whole name or any word in it, so a two-word name like
    # "Marlow Chen" is selectable as `Marlow` rather than being unreachable.
    def _selected(chosen: str) -> bool:
        return not wanted or chosen.lower() in wanted or bool(wanted & set(chosen.lower().split()))

    experts = [e for e in _named_experts() if _selected(e[1])]
    if not experts:
        print("No experts with both a chosen name and an appearance.")
        return 1

    # Where the running app serves portraits from, which relocates under
    # DEEPR_DATA_DIR. A hardcoded `data/portraits` writes files the web server
    # will not find on any install that configures a data directory.
    portraits = default_portraits_dir()
    portraits.mkdir(parents=True, exist_ok=True)
    store = ExpertStore()
    rendered = 0

    for directory, chosen, appearance in experts:
        slug = expert_slug(directory).replace("_", "-")
        print(f"{chosen} ({directory})")
        image = _render(_build_prompt(chosen, None, None, appearance=appearance))
        if image is None:
            continue

        destination = portraits / f"{slug}.png"
        destination.write_bytes(image)
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
