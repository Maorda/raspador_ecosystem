import asyncio
import pytest
from core.lifecycle import execute_plugin_lifecycle


class FakePlugin:
    def __init__(self, fail_at=None, cleanup_fails=False):
        self.fail_at = fail_at
        self.cleanup_fails = cleanup_fails
        self.events = []
        self.loop_ids = []

    async def initialize(self):
        self.events.append("initialize")
        self.loop_ids.append(id(asyncio.get_running_loop()))
        if self.fail_at == "initialize":
            raise ValueError("primary initialize error")

    async def run(self, blackboard):
        self.events.append("run")
        self.loop_ids.append(id(asyncio.get_running_loop()))
        if self.fail_at == "run":
            raise RuntimeError("primary run error")

    async def cleanup(self):
        self.events.append("cleanup")
        self.loop_ids.append(id(asyncio.get_running_loop()))
        if self.cleanup_fails:
            raise OSError("cleanup error")


@pytest.mark.asyncio
async def test_lifecycle_same_loop_and_order():
    plugin = FakePlugin()
    await execute_plugin_lifecycle(plugin, object(), "fake")
    assert plugin.events == ["initialize", "run", "cleanup"]
    assert len(set(plugin.loop_ids)) == 1


@pytest.mark.asyncio
async def test_cleanup_runs_when_run_fails():
    plugin = FakePlugin(fail_at="run")
    with pytest.raises(RuntimeError, match="primary run error"):
        await execute_plugin_lifecycle(plugin, object(), "fake")
    assert plugin.events == ["initialize", "run", "cleanup"]


@pytest.mark.asyncio
async def test_cleanup_runs_when_initialize_fails():
    plugin = FakePlugin(fail_at="initialize")
    with pytest.raises(ValueError, match="primary initialize error"):
        await execute_plugin_lifecycle(plugin, object(), "fake")
    assert plugin.events == ["initialize", "cleanup"]


@pytest.mark.asyncio
async def test_cleanup_error_does_not_mask_primary_error():
    plugin = FakePlugin(fail_at="run", cleanup_fails=True)
    with pytest.raises(RuntimeError, match="primary run error"):
        await execute_plugin_lifecycle(plugin, object(), "fake")


@pytest.mark.asyncio
async def test_cleanup_error_propagates_when_no_primary_error():
    plugin = FakePlugin(cleanup_fails=True)
    with pytest.raises(OSError, match="cleanup error"):
        await execute_plugin_lifecycle(plugin, object(), "fake")
