import anthropic
from config import ANTHROPIC_API_KEY

anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

MODEL = "claude-sonnet-4-5-20251001"


def call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 2000) -> str:
    """
    Call the Claude API and return the text response.
    Raises anthropic.APIError on failure — callers should handle this.
    """
    response = anthropic_client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text
