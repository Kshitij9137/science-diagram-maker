from app import config


def estimate_cost(input_tokens, output_tokens, thought_tokens=0):
    """Estimated cost in USD at paid-tier prices.

    Thinking tokens are billed like output tokens, so we add them to the output.
    The free tier actually charges $0. This is what the same usage WOULD cost.
    """
    billed_output = output_tokens + thought_tokens
    cost = (
        (input_tokens / 1_000_000) * config.PRICE_INPUT_PER_M
        + (billed_output / 1_000_000) * config.PRICE_OUTPUT_PER_M
    )
    return round(cost, 6)