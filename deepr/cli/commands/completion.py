"""Shell completion script generation.

clig.dev: ship tab-completion and make it discoverable. Click already
generates completion scripts natively (the `_DEEPR_COMPLETE` protocol);
this command surfaces that behind a documented `deepr completion <shell>`
verb and prints the one line a user adds to their shell rc file.
"""

import click
from click.shell_completion import get_completion_class

_INSTALL_HINT = {
    "bash": "echo 'eval \"$(deepr completion bash)\"' >> ~/.bashrc",
    "zsh": "echo 'eval \"$(deepr completion zsh)\"' >> ~/.zshrc",
    "fish": "deepr completion fish > ~/.config/fish/completions/deepr.fish",
}


@click.command()
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]))
def completion(shell: str) -> None:
    """Output a tab-completion script for SHELL (bash, zsh, or fish).

    \b
    Install (add to your shell startup file):
      bash:  eval "$(deepr completion bash)"   # in ~/.bashrc
      zsh:   eval "$(deepr completion zsh)"     # in ~/.zshrc
      fish:  deepr completion fish > ~/.config/fish/completions/deepr.fish

    The script is written to stdout so it can be piped or redirected;
    the install hint is written to stderr so it never pollutes the script.
    """
    comp_cls = get_completion_class(shell)
    if comp_cls is None:  # pragma: no cover - all three choices are supported by Click
        raise click.ClickException(f"Shell completion is unavailable for {shell}.")

    comp = comp_cls(cli_ref(), {}, "deepr", "_DEEPR_COMPLETE")
    # Script -> stdout (the contract: `eval "$(...)"` consumes stdout only).
    click.echo(comp.source())
    # Human guidance -> stderr, so redirection captures only the script.
    click.echo(f"\n# To install: {_INSTALL_HINT[shell]}", err=True)


def cli_ref() -> click.Group:
    """Return the root CLI group lazily to avoid a circular import."""
    from deepr.cli.main import cli

    return cli
