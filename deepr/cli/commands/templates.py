"""Templates commands - save and reuse research prompts."""

import click
from deepr.branding import print_section_header, CHECK, CROSS


@click.group()
def templates():
    """Manage prompt templates."""
    pass


@templates.command()
@click.argument("name")
@click.argument("prompt")
@click.option("--model", "-m", help="Default model for this template")
@click.option("--description", "-d", help="Template description")
def save(name: str, prompt: str, model: str, description: str):
    """
    Save a prompt as a reusable template.

    Example:
        deepr templates save competitive-analysis "Competitive analysis of {industry} in {region}"
        deepr templates save weekly-summary "Summarize developments in {topic} for week of {date}"
    """
    print_section_header(f"Save Template: {name}")

    try:
        import json
        from pathlib import Path
        from datetime import datetime

        # Create templates directory
        templates_dir = Path(".deepr/templates")
        templates_dir.mkdir(parents=True, exist_ok=True)

        # Create template
        template = {
            "name": name,
            "prompt": prompt,
            "model": model,
            "description": description,
            "created_at": datetime.utcnow().isoformat(),
            "usage_count": 0
        }

        # Save
        template_file = templates_dir / f"{name}.json"
        with open(template_file, 'w') as f:
            json.dump(template, f, indent=2)

        click.echo(f"\n{CHECK} Template saved: {name}")
        click.echo(f"File: {template_file}")

        if "{" in prompt:
            placeholders = [p.split("}")[0] for p in prompt.split("{")[1:]]
            click.echo(f"\nPlaceholders: {', '.join(placeholders)}")
            click.echo(f"\nUsage:")
            example_values = " ".join([f"--{p} VALUE" for p in placeholders])
            click.echo(f"  deepr templates use {name} {example_values}")

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        raise click.Abort()


@templates.command()
def list():
    """
    List all saved templates.

    Example:
        deepr templates list
    """
    print_section_header("Prompt Templates")

    try:
        import json
        from pathlib import Path

        templates_dir = Path(".deepr/templates")
        if not templates_dir.exists():
            click.echo(f"\nNo templates found")
            click.echo(f"\nCreate one: deepr templates save <name> \"<prompt>\"")
            return

        template_files = list(templates_dir.glob("*.json"))

        if not template_files:
            click.echo(f"\nNo templates found")
            return

        click.echo(f"\nFound {len(template_files)} template(s):\n")

        for tf in sorted(template_files):
            with open(tf) as f:
                template = json.load(f)

            click.echo(f"  {template['name']}")
            if template.get('description'):
                click.echo(f"    Description: {template['description']}")
            if template.get('model'):
                click.echo(f"    Model: {template['model']}")
            click.echo(f"    Used: {template.get('usage_count', 0)} times")

            # Show placeholders
            prompt = template['prompt']
            if "{" in prompt:
                placeholders = [p.split("}")[0] for p in prompt.split("{")[1:]]
                click.echo(f"    Placeholders: {', '.join(placeholders)}")

            click.echo()

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        raise click.Abort()


@templates.command()
@click.argument("name")
def show(name: str):
    """
    Show template details.

    Example:
        deepr templates show competitive-analysis
    """
    print_section_header(f"Template: {name}")

    try:
        import json
        from pathlib import Path

        template_file = Path(f".deepr/templates/{name}.json")

        if not template_file.exists():
            click.echo(f"\n{CROSS} Template not found: {name}", err=True)
            click.echo(f"\nAvailable templates:")
            templates_dir = Path(".deepr/templates")
            if templates_dir.exists():
                for tf in sorted(templates_dir.glob("*.json")):
                    click.echo(f"  - {tf.stem}")
            raise click.Abort()

        with open(template_file) as f:
            template = json.load(f)

        click.echo(f"\nName: {template['name']}")
        if template.get('description'):
            click.echo(f"Description: {template['description']}")
        if template.get('model'):
            click.echo(f"Default Model: {template['model']}")
        click.echo(f"Created: {template.get('created_at', 'Unknown')}")
        click.echo(f"Usage Count: {template.get('usage_count', 0)}")

        click.echo(f"\nPrompt:")
        click.echo(f"  {template['prompt']}")

        if "{" in template['prompt']:
            placeholders = [p.split("}")[0] for p in template['prompt'].split("{")[1:]]
            click.echo(f"\nPlaceholders:")
            for p in placeholders:
                click.echo(f"  - {p}")

    except Exception as e:
        if not isinstance(e, click.Abort):
            click.echo(f"\n{CROSS} Error: {e}", err=True)
        raise click.Abort()


@templates.command()
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete(name: str, yes: bool):
    """
    Delete a template.

    Example:
        deepr templates delete old-template --yes
    """
    print_section_header(f"Delete Template: {name}")

    try:
        from pathlib import Path

        template_file = Path(f".deepr/templates/{name}.json")

        if not template_file.exists():
            click.echo(f"\n{CROSS} Template not found: {name}", err=True)
            raise click.Abort()

        if not yes:
            if not click.confirm(f"\nDelete template '{name}'?"):
                click.echo(f"\n{CROSS} Cancelled")
                return

        template_file.unlink()
        click.echo(f"\n{CHECK} Template deleted: {name}")

    except Exception as e:
        if not isinstance(e, click.Abort):
            click.echo(f"\n{CROSS} Error: {e}", err=True)
        raise click.Abort()


@templates.command()
@click.argument("name")
@click.argument("values", nargs=-1)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@click.option("--model", "-m", help="Override template model")
def use(name: str, values: tuple, yes: bool, model: str):
    """
    Use a template to submit research.

    Provide placeholder values as --key value pairs.

    Example:
        deepr templates use competitive-analysis --industry "AI tools" --region "North America" --yes
        deepr templates use weekly-summary --topic "quantum computing" --date "2025-10-29" --yes
    """
    print_section_header(f"Use Template: {name}")

    try:
        import json
        from pathlib import Path

        template_file = Path(f".deepr/templates/{name}.json")

        if not template_file.exists():
            click.echo(f"\n{CROSS} Template not found: {name}", err=True)
            raise click.Abort()

        with open(template_file) as f:
            template = json.load(f)

        # Parse values
        placeholders = {}
        i = 0
        while i < len(values):
            if values[i].startswith("--"):
                key = values[i][2:]
                if i + 1 < len(values) and not values[i + 1].startswith("--"):
                    placeholders[key] = values[i + 1]
                    i += 2
                else:
                    click.echo(f"\n{CROSS} Missing value for --{key}", err=True)
                    raise click.Abort()
            else:
                i += 1

        # Fill template
        prompt = template['prompt']
        missing = []
        for match in [p.split("}")[0] for p in prompt.split("{")[1:]]:
            if match not in placeholders:
                missing.append(match)

        if missing:
            click.echo(f"\n{CROSS} Missing placeholder values: {', '.join(missing)}", err=True)
            click.echo(f"\nUsage:")
            example = " ".join([f"--{p} VALUE" for p in missing])
            click.echo(f"  deepr templates use {name} {example}")
            raise click.Abort()

        # Replace placeholders
        filled_prompt = prompt
        for key, value in placeholders.items():
            filled_prompt = filled_prompt.replace(f"{{{key}}}", value)

        click.echo(f"\nFilled prompt:")
        click.echo(f"  {filled_prompt[:200]}{'...' if len(filled_prompt) > 200 else ''}")

        # Use template model if not overridden
        use_model = model or template.get('model', 'o4-mini-deep-research')

        if not yes:
            if not click.confirm(f"\nSubmit research with this prompt?"):
                click.echo(f"\n{CROSS} Cancelled")
                return

        # Update usage count
        template['usage_count'] = template.get('usage_count', 0) + 1
        with open(template_file, 'w') as f:
            json.dump(template, f, indent=2)

        # Submit research
        click.echo(f"\n{CHECK} Submitting research...")

        from subprocess import run
        result = run([
            "python", "-m", "deepr.cli.main",
            "research", "submit", filled_prompt,
            "--model", use_model,
            "--yes"
        ])

        if result.returncode != 0:
            click.echo(f"\n{CROSS} Research submission failed", err=True)
            raise click.Abort()

    except Exception as e:
        if not isinstance(e, click.Abort):
            click.echo(f"\n{CROSS} Error: {e}", err=True)
        raise click.Abort()
