import pytest
from plugins.remaju.rule_factory import RemajuRuleFactory
from plugins.remaju.strategies import AuthenticateStrategy, ExtractExpedienteStrategy
from strategies.mixins import JSCapableMixin


def test_remaju_rule_factory():
    assert RemajuRuleFactory.decide_next_action({"spinner_visible": True}) == "WAIT_SPINNER"
    assert RemajuRuleFactory.decide_next_action({"captcha_error": True}) == "RETRY_CAPTCHA"
    assert RemajuRuleFactory.decide_next_action({}) == "PROCEED_EXTRACTION"


@pytest.mark.asyncio
async def test_js_mixin_evaluation(mock_tab):
    result = await JSCapableMixin().evaluate_js_script(mock_tab, "return true")
    assert result.is_success
    assert result.value["spinner_visible"] is False


@pytest.mark.asyncio
async def test_auth_strategy_does_not_fake_success():
    result = await AuthenticateStrategy().execute(None, {})
    assert not result.is_success
    assert result.error_category == "REMAJU_INTEGRATION_NOT_IMPLEMENTED"


@pytest.mark.asyncio
async def test_extraction_strategy_does_not_generate_fake_data():
    result = await ExtractExpedienteStrategy().execute(None, {})
    assert not result.is_success
    assert result.error_category == "REMAJU_INTEGRATION_NOT_IMPLEMENTED"
