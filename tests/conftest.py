import pytest
from infra.database import DatabaseManager
from core.blackboard import ScrapingBlackboard


@pytest.fixture
def db_manager(tmp_path):
    manager = DatabaseManager(tmp_path / "test_blackboard.db")
    manager.initialize_schema()
    return manager


@pytest.fixture
def blackboard(db_manager):
    return ScrapingBlackboard(db_manager)


from unittest.mock import AsyncMock
import pytest


@pytest.fixture
def mock_tab():
    tab = AsyncMock()
    tab.evaluate.return_value = '{"spinner_visible": false, "modal_visible": false}'
    return tab
