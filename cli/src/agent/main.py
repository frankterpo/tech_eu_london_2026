import typer
from rich.console import Console
from rich.panel import Panel
from agent.commands import (
    benchmark,
    bootstrap,
    smoke,
    cloud,
    auth,
    run_cmd,
    ask,
    eval_cmd,
    patch,
    loop,
    overview,
    mine,
    extrapolate,
    swarm,
    storage_check,
    chat,
)

console = Console()

WELCOME_ART = "[bold cyan]envoice-agent[/bold cyan]  [dim]headless invoice automation + learning loop[/dim]"

app = typer.Typer(
    name="agent",
    help="Envoice CLI Agent Trainer",
    no_args_is_help=True,
)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        console.print(WELCOME_ART)
        console.print(
            Panel.fit(
                "\n".join(
                    [
                        "[bold]Quickstart[/bold]",
                        "  [cyan]agent bootstrap[/cyan]",
                        "  [cyan]agent auth save envoice[/cyan]",
                        '  [cyan]agent ask "Create a monthly sales invoice of €1200 for ACME, reverse charge, VAT IE6388047V"[/cyan]',
                        '  [cyan]agent loop "Create a monthly invoice..." --iters 3[/cyan]',
                        "  [cyan]agent chat[/cyan]              [dim]Talk to skills via Dust.tt + Gemini[/dim]",
                        "  [cyan]agent overview[/cyan]",
                    ]
                ),
                title="One-Shot + Learning Loop",
                border_style="green",
            )
        )


app.command(name="bootstrap")(bootstrap.run)
app.command(name="smoke-local")(smoke.run_local)
app.command(name="run")(run_cmd.run_skill)
app.command(name="benchmark")(benchmark.run_benchmark)
app.command(name="ask")(ask.ask)
app.command(name="eval")(eval_cmd.evaluate_run)
app.command(name="patch")(patch.apply_patch)
app.command(name="loop")(loop.run_loop)
app.command(name="overview")(overview.show_overview)
app.command(name="mine")(mine.mine_workflow)
app.command(name="extrapolate")(extrapolate.extrapolate)
app.command(name="swarm")(swarm.run_swarm)
app.command(name="storage-check")(storage_check.check_storage)
app.command(name="chat")(chat.start_chat)

# Auth group
auth_app = typer.Typer(help="Authentication management")
app.add_typer(auth_app, name="auth")
auth_app.command(name="save")(auth.save_auth)

# Cloud group
cloud_app = typer.Typer(help="Cloud operations")
app.add_typer(cloud_app, name="cloud")
cloud_app.command(name="smoke")(cloud.smoke_cloud)

if __name__ == "__main__":
    app()
