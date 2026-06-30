"""Expert portrait command.

Extracted from experts.py (which is at its grandfathered file-size cap) so the
oversized command module does not grow. Generates consistent-style AI portraits
for one expert or the whole library.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import click

from deepr.cli.colors import console, print_error, print_success, print_warning
from deepr.cli.commands.semantic.experts import expert


def _resolve_targets(
    store: Any,
    *,
    name: str | None,
    all_experts: bool,
    missing_only: bool,
    force: bool,
) -> list[str] | None:
    """Resolve the expert names to portray, or None after printing an error."""
    if not name and not all_experts:
        print_error("Specify an expert NAME or --all.")
        return None

    if all_experts:
        targets = [e.name for e in store.list_all()]
    elif not store.load(name):
        print_error(f"Expert not found: {name}")
        return None
    else:
        targets = [name]

    if missing_only:
        targets = [n for n in targets if not getattr(store.load(n), "portrait_url", None)]
    elif not force:
        skipped = [n for n in targets if getattr(store.load(n), "portrait_url", None)]
        targets = [n for n in targets if n not in skipped]
        if skipped:
            print_warning(f"Skipped {len(skipped)} expert(s) with existing portraits. Use --force to regenerate.")
    return targets


async def _run_portrait_batch(store: Any, targets: list[str], *, provider: str | None, style: str | None) -> int:
    """Generate portraits for ``targets`` in one event loop. Returns the count done.

    A single loop (vs asyncio.run per item) avoids racing the async HTTP client's
    teardown on Windows ("Event loop is closed").
    """
    from deepr.experts.portraits import generate_and_save_portrait

    done = 0
    for target in targets:
        profile = store.load(target)
        try:
            url = await generate_and_save_portrait(profile, store, provider=provider, style=style)
            console.print(f"  [green]done[/green] {target}  ->  {url}")
            done += 1
        except Exception as e:
            console.print(f"  [red]failed[/red] {target}: {e}")
    return done


@expert.command(name="portrait")
@click.argument("name", required=False)
@click.option("--all", "all_experts", is_flag=True, help="Generate for every expert in the library")
@click.option("--missing-only", is_flag=True, help="Only experts that have no portrait yet")
@click.option("--force", is_flag=True, help="Regenerate existing portraits")
@click.option(
    "--style", default=None, help="Override the art style this run (else DEEPR_PORTRAIT_STYLE / house default)"
)
@click.option("--provider", type=click.Choice(["openai", "google", "xai"]), default=None, help="Image provider")
@click.option("-y", "--yes", is_flag=True, help="Skip the cost confirmation")
def expert_portrait(name, all_experts, missing_only, force, style, provider, yes):
    """Generate a consistent-style AI portrait for one expert or the whole library.

    Every portrait shares one house art style (set ``DEEPR_PORTRAIT_STYLE`` or pass
    ``--style``) so a roster reads as a coherent set. ~$0.04 per image.

    EXAMPLES:
      deepr expert portrait "Coffee Brewing Methods"
      deepr expert portrait --all --missing-only -y
      deepr expert portrait "Coffee Brewing Methods" --provider xai --force
      deepr expert portrait --all --style "flat vector, muted palette" -y
    """
    from deepr.experts.portraits import detect_provider, portrait_cost, portrait_style
    from deepr.experts.profile import ExpertStore

    store = ExpertStore()
    targets = _resolve_targets(store, name=name, all_experts=all_experts, missing_only=missing_only, force=force)
    if targets is None:
        sys.exit(2)
    if not targets:
        print_success("Nothing to do - all selected experts already have portraits.")
        return
    effective = provider or detect_provider()
    if not effective:
        print_error(
            "No image generator available. Set DEEPR_LOCAL_IMAGE_URL (local FLUX/ComfyUI, $0) "
            "or pass --provider openai/google/xai for explicit paid image generation. "
            "Set DEEPR_ALLOW_METERED_IMAGE_AUTO=1 only if metered image auto-selection is intentional."
        )
        sys.exit(2)

    unit = portrait_cost(effective)
    console.print(f"[dim]Provider: {effective} (~${unit:.2f}/image)  Style: {portrait_style(style)}[/dim]")
    est = len(targets) * unit
    if not yes and not click.confirm(f"Generate {len(targets)} portrait(s) (~${est:.2f})?", default=False):
        print_warning("Cancelled.")
        return

    ok = asyncio.run(_run_portrait_batch(store, targets, provider=effective, style=style))
    print_success(f"Generated {ok}/{len(targets)} portrait(s). Spend ~${ok * unit:.2f}.")
