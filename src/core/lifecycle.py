"""Ejecución del ciclo de vida completo dentro de un único bucle asyncio."""
from __future__ import annotations
from typing import Any
from infra.logger import get_logger

logger = get_logger("plugin_lifecycle")


async def execute_plugin_lifecycle(plugin: Any, blackboard: Any, plugin_name: str) -> None:
    primary_error: BaseException | None = None
    try:
        logger.info("plugin_initialization_started", plugin=plugin_name)
        await plugin.initialize()
        logger.info("plugin_run_started", plugin=plugin_name)
        await plugin.run(blackboard)
    except BaseException as exc:
        primary_error = exc
        logger.error(
            "plugin_execution_failed",
            plugin=plugin_name,
            error_type=type(exc).__name__,
            error=str(exc),
            exc_info=True,
        )
        raise
    finally:
        try:
            logger.info("plugin_cleanup_started", plugin=plugin_name)
            await plugin.cleanup()
            logger.info("plugin_cleanup_completed", plugin=plugin_name)
        except BaseException as cleanup_error:
            if primary_error is None:
                raise
            logger.error(
                "plugin_cleanup_failed_preserving_primary_error",
                plugin=plugin_name,
                cleanup_error_type=type(cleanup_error).__name__,
                cleanup_error=str(cleanup_error),
                exc_info=True,
            )
