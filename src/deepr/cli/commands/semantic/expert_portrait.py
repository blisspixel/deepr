"""Expert portrait command.

Extracted from experts.py (which is at its grandfathered file-size cap) so the
oversized command module does not grow. Generates consistent-style AI portraits
for one expert or the whole library.
"""

from __future__ import annotations

import asyncio
import sys

import click

from deepr.cli.colors import console, print_error, print_success, print_warning
from deepr.cli.commands.semantic.experts import expert


@expert.command(name="portrait")
@click.argument("name", required=False)
@click.option("--all", "all_experts", is_flag=True, help="Generate for every expert in the library")
@click.option("--missing-only", is_flag=True, help="Only experts that have no portrait yet")
@click.option(
    "--style", default=None, help="Override the art style this run (else DEEPR_PORTRAIT_STYLE / house default)"
)
@click.option("--provider", type=click.Choice(["openai", "google", "xai"]), default=None, help="Image provider")
@click.option("-y", "--yes", is_flag=True, help="Skip the cost confirmation")
def expert_portrait(name, all_experts, missing_only, style, provider, yes):
    """Generate a consistent-style AI portrait for one expert or the whole library.

    Every portrait shares one house art style (set ``DEEPR_PORTRAIT_STYLE`` or pass
    ``--style``) so a roster reads as a coherent set. ~$0.04 per image.

    EXAMPLES:
      deepr expert portrait "Coffee Brewing Methods"
      deepr expert portrait --all --missing-only -y
      deepr expert portrait --all --style "flat vector, muted palette" -y
    """
    from deepr.experts.portraits import (
        PORTRAIT_COST_ESTIMATE_USD,
        detect_provider,
        generate_and_save_portrait,
        portrait_style,
    )
    from deepr.experts.profile import ExpertStore

    if not name and not all_experts:
        print_error("Specify an expert NAME or --all.")
        sys.exit(2)

    store = ExpertStore()
    if all_experts:
        targets = [e.name for e in store.list_all()]
    elif not store.load(name):
        print_error(f"Expert not found: {name}")
        sys.exit(2)
    else:
        targets = [name]

    if missing_only:
        targets = [n for n in targets if not getattr(store.load(n), "portrait_url", None)]
    if not targets:
        print_success("Nothing to do - all selected experts already have portraits.")
        return

    if not (provider or detect_provider()):
        print_error("No image provider available. Set OPENAI_API_KEY, GEMINI_API_KEY, or XAI_API_KEY.")
        sys.exit(2)

    console.print(f"[dim]Style: {portrait_style(style)}[/dim]")
    est = len(targets) * PORTRAIT_COST_ESTIMATE_USD
    if not yes and not click.confirm(f"Generate {len(targets)} portrait(s) (~${est:.2f})?", default=False):
        print_warning("Cancelled.")
        return

    async def _run_batch() -> int:
        # One event loop for the whole batch: repeated asyncio.run() per item
        # races the async HTTP client's teardown on Windows ("Event loop is
        # closed"). A single loop reaps cleanly.
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

    ok = asyncio.run(_run_batch())
    print_success(f"Generated {ok}/{len(targets)} portrait(s). Spend ~${ok * PORTRAIT_COST_ESTIMATE_USD:.2f}.")
