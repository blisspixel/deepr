"""Templates commands - save and reuse research prompts."""

import click
from deepr.cli.colors import print_section_header, print_success, print_error, print_warning, console


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

        print_success(f"Template saved: {name}")
        console.print(f"File: {template_file}")

        if "{" in prompt:
            placeholders = [p.split("}")[0] for p in prompt.split("{")[1:]]
            console.print(f"\nPlaceholders: {', '.join(placeholders)}")
            console.print(f"\nUsage:")
            example_values = " ".join([f"--{p} VALUE" for p in placeholders])
            console.print(f"  deepr templates use {name} {example_values}")

    except Exception as e:
        print_error(f"Error: {e}")
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
        print_error(f"Error: {e}")
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
            print_error(f"Template not found: {name}")
            console.print(f"\nAvailable templates:")
            templates_dir = Path(".deepr/templates")
            if templates_dir.exists():
                for tf in sorted(templates_dir.glob("*.json")):
                    console.print(f"  - {tf.stem}")
            raise click.Abort()

        with open(template_file) as f:
            template = json.load(f)

        console.print(f"\nName: {template['name']}")
        if template.get('description'):
            console.print(f"Description: {template['description']}")
        if template.get('model'):
            console.print(f"Default Model: {template['model']}")
        console.print(f"Created: {template.get('created_at', 'Unknown')}")
        console.print(f"Usage Count: {template.get('usage_count', 0)}")

        console.print(f"\nPrompt:")
        console.print(f"  {template['prompt']}")

        if "{" in template['prompt']:
            placeholders = [p.split("}")[0] for p in template['prompt'].split("{")[1:]]
            console.print(f"\nPlaceholders:")
            for p in placeholders:
                console.print(f"  - {p}")

    except Exception as e:
        if not isinstance(e, click.Abort):
            print_error(f"Error: {e}")
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
            print_error(f"Template not found: {name}")
            raise click.Abort()

        if not yes:
            if not click.confirm(f"\nDelete template '{name}'?"):
                print_warning("Cancelled")
                return

        template_file.unlink()
        print_success(f"Template deleted: {name}")

    except Exception as e:
        if not isinstance(e, click.Abort):
            print_error(f"Error: {e}")
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
            print_error(f"Template not found: {name}")
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
                    print_error(f"Missing value for --{key}")
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
            print_error(f"Missing placeholder values: {', '.join(missing)}")
            console.print(f"\nUsage:")
            example = " ".join([f"--{p} VALUE" for p in missing])
            console.print(f"  deepr templates use {name} {example}")
            raise click.Abort()

        # Replace placeholders
        filled_prompt = prompt
        for key, value in placeholders.items():
            filled_prompt = filled_prompt.replace(f"{{{key}}}", value)

        console.print(f"\nFilled prompt:")
        console.print(f"  {filled_prompt[:200]}{'...' if len(filled_prompt) > 200 else ''}")

        # Use template model if not overridden
        use_model = model or template.get('model', 'o4-mini-deep-research')

        if not yes:
            if not click.confirm(f"\nSubmit research with this prompt?"):
                print_warning("Cancelled")
                return

        # Update usage count
        template['usage_count'] = template.get('usage_count', 0) + 1
        with open(template_file, 'w') as f:
            json.dump(template, f, indent=2)

        # Submit research
        print_success("Submitting research...")

        from subprocess import run
        result = run([
            "python", "-m", "deepr.cli.main",
            "research", "submit", filled_prompt,
            "--model", use_model,
            "--yes"
        ])

        if result.returncode != 0:
            print_error("Research submission failed")
            raise click.Abort()

    except Exception as e:
        if not isinstance(e, click.Abort):
            print_error(f"Error: {e}")
        raise click.Abort()
