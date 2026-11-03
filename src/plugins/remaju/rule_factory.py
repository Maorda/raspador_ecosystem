from typing import Any


class RemajuRuleFactory:
    @staticmethod
    def decide_next_action(dom_state: dict[str, Any]) -> str:
        if dom_state.get("spinner_visible"):
            return "WAIT_SPINNER"
        if dom_state.get("captcha_error"):
            return "RETRY_CAPTCHA"
        if dom_state.get("modal_visible"):
            return "CLOSE_MODAL"
        if dom_state.get("btn_casilla_active"):
            return "CLICK_CASILLA"
        return "PROCEED_EXTRACTION"
