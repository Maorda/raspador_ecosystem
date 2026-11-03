import json
from typing import Any
from core.result import Result


class JSCapableMixin:
    async def evaluate_js_script(self, tab: Any, js_script: str) -> Result[dict[str, Any]]:
        try:
            raw = await tab.evaluate(js_script)
            if isinstance(raw, str):
                try:
                    parsed = json.loads(raw)
                    return Result.ok(parsed if isinstance(parsed, dict) else {"result": parsed})
                except json.JSONDecodeError:
                    return Result.ok({"raw": raw})
            if isinstance(raw, dict):
                return Result.ok(raw)
            return Result.ok({"result": raw})
        except Exception as exc:
            return Result.fail(str(exc), "JS_EVALUATION_ERROR")
