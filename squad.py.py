import typer

app = typer.Typer(help="Windows Dev Squad — under active development.")


@app.command()
def doctor(setup_help: bool = False) -> None:
    """Report machine capabilities. Read-only."""
    if setup_help:
        typer.echo("Setup help: TODO — Phase 0.")
    else:
        typer.echo("squad doctor — Phase 0 stub. Under active development.")


@app.command()
def check() -> None:
    """Run tests, lint, and security scans. Not implemented yet."""
    typer.echo("squad check — not implemented yet.")


@app.command()
def run(dry_run: bool = False) -> None:
    """Run the squad. Not implemented yet."""
    typer.echo("squad run — not implemented yet.")


if __name__ == "__main__":
    app()