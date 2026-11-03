from abc import ABC, abstractmethod
from typing import ClassVar
from core.blackboard import ScrapingBlackboard
from infra.logger import get_logger

logger = get_logger("plugin_registry")


class BasePlugin(ABC):
    @abstractmethod
    async def initialize(self) -> None:
        """Preparar recursos que se usarán en el mismo bucle asíncrono."""
        raise NotImplementedError

    @abstractmethod
    async def run(self, blackboard: ScrapingBlackboard) -> None:
        raise NotImplementedError

    @abstractmethod
    async def cleanup(self) -> None:
        """Liberar recursos antes de que termine el bucle de eventos."""
        raise NotImplementedError


class PluginRegistrationError(ValueError):
    pass


class PluginRegistry:
    _registry: ClassVar[dict[str, type[BasePlugin]]] = {}

    @classmethod
    def register(cls, name: str, plugin_class: type[BasePlugin]):
        clean_name = name.strip().lower()
        if not clean_name:
            raise PluginRegistrationError("El nombre del plugin no puede estar vacío.")
        if not issubclass(plugin_class, BasePlugin):
            raise PluginRegistrationError(f"La clase '{plugin_class.__name__}' debe heredar de BasePlugin.")
        existing = cls._registry.get(clean_name)
        if existing is not None and existing is not plugin_class:
            raise PluginRegistrationError(f"Ya existe un plugin registrado con nombre '{clean_name}'.")
        cls._registry[clean_name] = plugin_class
        logger.info("plugin_registered", plugin_name=clean_name)
        return plugin_class

    @classmethod
    def get_plugin(cls, name: str) -> type[BasePlugin]:
        clean_name = name.strip().lower()
        if clean_name not in cls._registry:
            raise KeyError(f"Plugin '{clean_name}' no encontrado. Disponibles: {', '.join(cls.list_plugins()) or '(ninguno)'}")
        return cls._registry[clean_name]

    @classmethod
    def list_plugins(cls) -> list[str]:
        return sorted(cls._registry)


def register_plugin(name: str):
    def decorator(cls: type[BasePlugin]):
        PluginRegistry.register(name, cls)
        return cls
    return decorator
