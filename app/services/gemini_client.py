from google import genai
from google.genai import types

from app import config

SYSTEM_PROMPT = f"""You are an expert science illustrator making animated diagrams
for UK GCSE students.

Return exactly ONE complete SVG element and nothing else: no markdown, no code
fences, no explanation.

Technical requirements:
1. Start with <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {config.VIEWBOX_WIDTH} {config.VIEWBOX_HEIGHT}">.
2. Keep every shape and every piece of text fully inside that viewBox, with a margin of at least 20 units.
3. Include a <title> element with a clear diagram title.
4. Include at least 3 <text> labels. Use font-size 16 or larger and font-family sans-serif.
5. Include animation using SMIL (<animate>, <animateTransform>, <animateMotion>) or CSS @keyframes that is actually used. The animation should help explain the concept.
6. Use a clean, simple style with a light background and good colour contrast.
7. Use no JavaScript, no external images, no external fonts and no external links.
8. Keep the SVG under 50 KB.
"""


def get_client():
    """Create the Gemini client, with a friendly error if the key is missing."""
    if not config.GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Put it in the .env file in the project root."
        )
    return genai.Client(api_key=config.GEMINI_API_KEY)


def build_prompt(concept):
    """Turn one concept dictionary into the user message."""
    return (
        f"Concept: {concept['name']} ({concept['subject']})\n\n"
        f"Explanation: {concept['description']}\n\n"
        f"The diagram must show: {concept['hint']}\n\n"
        "Return only the SVG."
    )



def build_correction_prompt(concept, previous_svg, failures):
    """The message for the validation retry: what went wrong, plus the previous answer."""
    problems = "\n".join(f"- {failure}" for failure in failures)
    return (
        build_prompt(concept)
        + "\n\nYour previous answer failed these automatic checks:\n"
        + problems
        + "\n\nHere is your previous answer:\n"
        + previous_svg[:30000]
        + "\n\nFix every problem listed above and return the complete corrected SVG. "
        "Return only the SVG, with no explanation."
    )



def extract_svg(text):
    """Cut out everything from '<svg' to the last '</svg>'.

    This removes markdown fences and any chatter the model added around the SVG.
    """
    start = text.find("<svg")
    end = text.rfind("</svg>")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No complete <svg>...</svg> found in the model response")
    return text[start : end + len("</svg>")]


def call_gemini(prompt):
    """Send one prompt to Gemini. Return the raw text and the token usage."""
    client = get_client()
    response = client.models.generate_content(
        model=config.MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=config.MAX_OUTPUT_TOKENS,
        ),
    )

    usage = response.usage_metadata
    finish_reason = None
    if response.candidates:
        finish_reason = str(response.candidates[0].finish_reason)

    return {
        "text": response.text or "",
        "model": config.MODEL_NAME,
        # "or 0" protects us if a field comes back empty
        "input_tokens": (usage.prompt_token_count or 0) if usage else 0,
        "output_tokens": (usage.candidates_token_count or 0) if usage else 0,
        "thought_tokens": (usage.thoughts_token_count or 0) if usage else 0,
        "finish_reason": finish_reason,
    }


def generate_svg(concept):
    """Ask Gemini for an SVG for one concept."""
    reply = call_gemini(build_prompt(concept))
    reply["svg"] = extract_svg(reply["text"])
    return reply