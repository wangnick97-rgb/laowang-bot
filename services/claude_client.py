import anthropic
from config.settings import ANTHROPIC_API_KEY, MODEL_FAST, MODEL_SMART
from config.prompts import PROMPTS
from db.usage_logs import log_usage

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Features that warrant the smarter (more expensive) model
_SMART_FEATURES = {"brand_positioning", "sales_assist"}


async def call_claude(
    feature_key: str,
    user_message: str,
    user_id: int,
    max_tokens: int = 900,
    extra_context: str = "",
) -> str:
    """
    Call Claude for a given feature.

    extra_context: appended to the system prompt (e.g. today's date for news).
    """
    model = MODEL_SMART if feature_key in _SMART_FEATURES else MODEL_FAST
    system = PROMPTS[feature_key]
    if extra_context:
        system = system + "\n\n" + extra_context

    response = _client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )

    text = response.content[0].text

    # Fire-and-forget usage log (sync is fine here; Supabase calls are fast)
    try:
        log_usage(
            user_id=user_id,
            feature=feature_key,
            model=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
    except Exception:
        pass  # Never let logging break the user experience

    return text
