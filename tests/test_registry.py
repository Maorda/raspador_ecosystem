import pytest
from plugins.registry import PluginRegistry, BasePlugin, PluginRegistrationError


def test_plugin_discovery_and_registry():
    assert "remaju" in PluginRegistry.list_plugins()
    plugin_cls = PluginRegistry.get_plugin("REMAJU")
    assert issubclass(plugin_cls, BasePlugin)


def test_unknown_plugin_error_is_actionable():
    with pytest.raises(KeyError, match="Disponibles"):
        PluginRegistry.get_plugin("missing-plugin")
