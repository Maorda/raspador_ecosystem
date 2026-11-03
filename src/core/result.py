from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Result(Generic[T]):
    is_success: bool
    _value: T | None = None
    _error: str | None = None
    _error_category: str | None = None

    @classmethod
    def ok(cls, value: T) -> "Result[T]":
        return cls(is_success=True, _value=value)

    @classmethod
    def fail(cls, error: str, category: str = "GENERAL_ERROR") -> "Result[T]":
        return cls(is_success=False, _error=error, _error_category=category)

    @property
    def value(self) -> T:
        if not self.is_success:
            raise ValueError(f"Cannot access value of failed Result: {self._error}")
        return self._value  # type: ignore[return-value]

    @property
    def error(self) -> str:
        return self._error or ""

    @property
    def error_category(self) -> str:
        return self._error_category or "NONE"
