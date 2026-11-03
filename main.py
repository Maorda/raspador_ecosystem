from __future__ import annotations
import asyncio
import typer
from infra.database import DatabaseManager
from infra.logger import configure_logging, get_logger
from core.blackboard import ScrapingBlackboard
from core.lifecycle import execute_plugin_lifecycle
from plugins.registry import PluginRegistry
import plugins  # noqa: F401 — registra los plugins mediante decoradores

app = typer.Typer(help="CLI del ecosistema de scraping")
logger = get_logger("main")


@app.command()
def migrate() -> None:
    """Inicializa/migra el esquema SQLite de forma idempotente."""
    configure_logging()
    try:
        DatabaseManager().initialize_schema()
        logger.info("schema_migrated_successfully")
    except Exception as exc:
        logger.error("schema_migration_failed", error=str(exc), exc_info=True)
        raise typer.Exit(code=1) from exc


@app.command()
def run(
    name: str = typer.Option("remaju", "--name", help="Nombre del plugin registrado."),
) -> None:
    """Ejecuta el ciclo de vida completo en un único bucle de eventos."""
    configure_logging()
    try:
        plugin_cls = PluginRegistry.get_plugin(name)
        plugin = plugin_cls()
        db = DatabaseManager()
        db.initialize_schema()
        blackboard = ScrapingBlackboard(db)
        asyncio.run(execute_plugin_lifecycle(plugin, blackboard, name.strip().lower()))
    except Exception as exc:
        logger.error(
            "plugin_run_command_failed",
            plugin=name,
            error_type=type(exc).__name__,
            error=str(exc),
            exc_info=True,
        )
        raise typer.Exit(code=1) from exc


@app.command("list-plugins")
def list_plugins() -> None:
    """Muestra los plugins registrados."""
    configure_logging()
    for name in PluginRegistry.list_plugins():
        typer.echo(name)


if __name__ == "__main__":
    app()
