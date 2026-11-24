from app.services.cost_tracker import estimate_cost


def test_estimate_cost_uses_model_specific_prices():
    assert estimate_cost(1_000_000, 1_000_000, 100_000, "gemini-3.5-flash") == 4.875


def test_estimate_cost_uses_default_price_for_unknown_model():
    assert estimate_cost(1_000_000, 1_000_000, model="test-model") == 4.5
