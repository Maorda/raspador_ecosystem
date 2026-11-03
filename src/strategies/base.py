from abc import ABC, abstractmethod
from typing import Any
from core.result import Result


class BaseStrategy(ABC):
    @abstractmethod
    async def execute(self, tab: Any, context: dict[str, Any], **kwargs: Any) -> Result[Any]:
        raise NotImplementedError
