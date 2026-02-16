"""Skill management commands — list, install, remove, create, and inspect skills."""

import click

from deepr.cli.colors import (
    console,
    print_error,
    print_header,
    print_key_value,
    print_success,
    print_warning,
)


@click.group()
def skill():
    """Manage expert skills — domain-specific capability packages.

    Skills give experts unique tools and domain-specific reasoning.
    Supports Python tools (local, free) and MCP bridging (external servers).

    COMMANDS:
      deepr skill list                          All available skills
      deepr skill list "Financial Analyst"      Skills on an expert
      deepr skill install "Expert" skill-name   Install a skill
      deepr skill remove "Expert" skill-name    Remove a skill
      deepr skill create my-skill               Scaffold a new skill
      deepr skill info skill-name               Show skill details
    """


@skill.command(name="list")
@click.argument("expert_name", required=False)
def list_skills(expert_name):
    """List available skills, or skills installed on an expert.

    EXAMPLES:
      deepr skill list                          # All available skills
      deepr skill list "Financial Analyst"      # Skills on an expert
    """
    from deepr.experts.skills import SkillManager

    if expert_name:
        from deepr.experts.profile_store import ExpertStore

        store = ExpertStore()
        profile = store.load(expert_name)
        if not profile:
            print_error(f"Expert not found: {expert_name}")
            return

        manager = SkillManager(expert_name=expert_name)
        installed = manager.get_installed_skills(getattr(profile, "installed_skills", []))
        available = manager.list_all()

        print_header(f"Skills: {expert_name}")

        if installed:
            console.print("\n[bold]Installed:[/bold]")
            for s in installed:
                tier_badge = f"[dim][{s.tier}][/dim]"
                console.print(f"  [green]●[/green] {s.name} — {s.description} {tier_badge}")
                console.print(f"    Tools: {', '.join(t.name for t in s.tools)}")
        else:
            console.print("\n[dim]No skills installed.[/dim]")

        # Available but not installed
        installed_names = {s.name for s in installed}
        not_installed = [s for s in available if s.name not in installed_names]
        if not_installed:
            console.print("\n[bold]Available to install:[/bold]")
            for s in not_installed:
                domains = ", ".join(s.domains[:3]) if s.domains else ""
                console.print(f"  [dim]○[/dim] {s.name} — {s.description}")
                if domains:
                    console.print(f"    [dim]Domains: {domains}[/dim]")
    else:
        manager = SkillManager()
        all_skills = manager.list_all()

        print_header("Available Skills")

        if not all_skills:
            console.print("[dim]No skills found.[/dim]")
            console.print("Create one with: deepr skill create my-skill")
            return

        for s in all_skills:
            tier_badge = f"[dim][{s.tier}][/dim]"
            console.print(f"\n  {s.name} v{s.version} {tier_badge}")
            console.print(f"    {s.description}")
            console.print(f"    Tools: {', '.join(t.name for t in s.tools)}")
            if s.domains:
                console.print(f"    Domains: {', '.join(s.domains)}")

        console.print(f"\n[dim]{len(all_skills)} skill(s) found.[/dim]")


@skill.command(name="install")
@click.argument("expert_name")
@click.argument("skill_name")
def install_skill(expert_name, skill_name):
    """Install a skill on an expert.

    EXAMPLES:
      deepr skill install "Financial Analyst" financial-data
      deepr skill install "Dev Lead" code-analysis
    """
    from deepr.experts.profile_store import ExpertStore
    from deepr.experts.skills import SkillManager

    store = ExpertStore()
    profile = store.load(expert_name)
    if not profile:
        print_error(f"Expert not found: {expert_name}")
        return

    manager = SkillManager(expert_name=expert_name)
    skill_def = manager.get_skill(skill_name)
    if not skill_def:
        print_error(f"Skill not found: {skill_name}")
        console.print("[dim]Use 'deepr skill list' to see available skills.[/dim]")
        return

    installed = getattr(profile, "installed_skills", [])
    if skill_name in installed:
        print_warning(f"Skill '{skill_name}' is already installed on {expert_name}")
        return

    profile.installed_skills = [*installed, skill_name]
    store.save(profile)

    print_success(f"Installed '{skill_name}' on {expert_name}")
    console.print(f"  Tools added: {', '.join(t.name for t in skill_def.tools)}")
    console.print(f"  Triggers: {', '.join(skill_def.triggers.keywords[:5])}")


@skill.command(name="remove")
@click.argument("expert_name")
@click.argument("skill_name")
def remove_skill(expert_name, skill_name):
    """Remove a skill from an expert.

    EXAMPLES:
      deepr skill remove "Financial Analyst" financial-data
    """
    from deepr.experts.profile_store import ExpertStore

    store = ExpertStore()
    profile = store.load(expert_name)
    if not profile:
        print_error(f"Expert not found: {expert_name}")
        return

    installed = getattr(profile, "installed_skills", [])
    if skill_name not in installed:
        print_warning(f"Skill '{skill_name}' is not installed on {expert_name}")
        return

    profile.installed_skills = [s for s in installed if s != skill_name]
    store.save(profile)
    print_success(f"Removed '{skill_name}' from {expert_name}")


@skill.command(name="create")
@click.argument("name")
def create_skill(name):
    """Scaffold a new skill in ~/.deepr/skills/.

    Creates the directory structure with skill.yaml template,
    prompt.md, and tools/__init__.py.

    EXAMPLES:
      deepr skill create my-custom-skill
    """
    from pathlib import Path

    skills_dir = Path.home() / ".deepr" / "skills" / name
    if skills_dir.exists():
        print_error(f"Skill directory already exists: {skills_dir}")
        return

    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "tools").mkdir(exist_ok=True)

    # Write skill.yaml template
    (skills_dir / "skill.yaml").write_text(
        f"""name: {name}
version: "0.1.0"
description: "Description of your skill"
author: ""
license: "MIT"

domains: []

triggers:
  keywords: []
  patterns: []

prompt_file: "prompt.md"

tools:
  - name: my_tool
    type: python
    module: tools.my_tool
    function: run
    description: "What this tool does"
    cost_tier: free
    parameters:
      type: object
      properties:
        input:
          type: string
          description: "Input to the tool"
      required: ["input"]

budget:
  max_per_call: 0.0
  default_budget: 0.0
""",
        encoding="utf-8",
    )

    (skills_dir / "prompt.md").write_text(
        f"# {name}\n\nDomain-specific instructions loaded when this skill activates.\n",
        encoding="utf-8",
    )

    (skills_dir / "tools" / "__init__.py").write_text("", encoding="utf-8")

    (skills_dir / "tools" / "my_tool.py").write_text(
        '''"""Custom tool implementation."""


def run(input: str) -> dict:
    """Execute the tool.

    Args:
        input: Tool input

    Returns:
        Result dictionary
    """
    return {"result": f"Processed: {input}"}
''',
        encoding="utf-8",
    )

    print_success(f"Created skill scaffold: {skills_dir}")
    console.print("  Files created:")
    console.print("    skill.yaml    — Metadata and tool definitions")
    console.print("    prompt.md     — Domain-specific instructions")
    console.print("    tools/        — Python tool implementations")
    console.print(f'\nInstall on an expert: deepr skill install "Expert Name" {name}')


@skill.command(name="info")
@click.argument("name")
def skill_info(name):
    """Show detailed information about a skill.

    EXAMPLES:
      deepr skill info financial-data
      deepr skill info code-analysis
    """
    from deepr.experts.skills import SkillManager

    manager = SkillManager()
    skill_def = manager.get_skill(name)
    if not skill_def:
        print_error(f"Skill not found: {name}")
        return

    print_header(f"Skill: {skill_def.name}")
    print_key_value("Version", skill_def.version)
    print_key_value("Description", skill_def.description)
    print_key_value("Tier", skill_def.tier)
    print_key_value("Path", str(skill_def.path))

    if skill_def.author:
        print_key_value("Author", skill_def.author)
    if skill_def.domains:
        print_key_value("Domains", ", ".join(skill_def.domains))

    console.print("\n[bold]Tools:[/bold]")
    for tool in skill_def.tools:
        cost_label = f"[dim]({tool.cost_tier})[/dim]"
        console.print(f"  {tool.name} — {tool.description} {cost_label}")
        console.print(f"    Type: {tool.type}", highlight=False)
        if tool.type == "python":
            console.print(f"    Module: {tool.module}.{tool.function}", highlight=False)
        elif tool.type == "mcp":
            console.print(f"    Server: {tool.server_command} {' '.join(tool.server_args)}", highlight=False)

    if skill_def.triggers.keywords:
        console.print(f"\n[bold]Trigger keywords:[/bold] {', '.join(skill_def.triggers.keywords[:10])}")
    if skill_def.triggers.patterns:
        console.print(f"[bold]Trigger patterns:[/bold] {', '.join(skill_def.triggers.patterns[:5])}")

    # Show prompt preview
    prompt = skill_def.load_prompt()
    if prompt:
        console.print("\n[bold]Prompt preview:[/bold]")
        preview = prompt[:300]
        if len(prompt) > 300:
            preview += "..."
        console.print(f"  [dim]{preview}[/dim]")
