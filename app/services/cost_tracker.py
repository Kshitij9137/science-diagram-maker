from app import config


def estimate_cost(input_tokens, output_tokens, thought_tokens=0, model=None):
    """Estimated paid-tier cost in USD for the selected model.

    Thinking tokens are billed like output tokens, so we add them to the output.
    The free tier actually charges $0; this is the paid-tier equivalent.
    """
    price = config.PRICES.get(model or config.MODEL_NAME, config.DEFAULT_PRICE)
    billed_output = output_tokens + thought_tokens
    cost = (
        (input_tokens / 1_000_000) * price["input"]
        + (billed_output / 1_000_000) * price["output"]
    )
    return round(cost, 6)