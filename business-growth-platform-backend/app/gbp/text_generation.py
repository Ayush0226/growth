"""Bounded text generation; never infer a model's task from catalog order."""
import os

from fastapi import HTTPException
from groq import APIConnectionError, APIError, APIStatusError, Groq

TEXT_MODELS = (
    'openai/gpt-oss-20b', 'openai/gpt-oss-120b',
    'llama-3.1-8b-instant', 'llama-3.3-70b-versatile',
)
UNAVAILABLE_CODES = {'model_decommissioned', 'model_not_found', 'model_terms_required', 'model_permission_blocked'}


def call_groq_with_fallback(api_key: str, messages: list, temperature: float = 0.2):
    key = api_key or os.getenv('GROQ_API_KEY')
    if not key:
        raise HTTPException(503, 'AI replies are not configured; contact support')
    configured = os.getenv('GROQ_TEXT_MODEL', '').strip()
    if configured and configured not in TEXT_MODELS:
        raise HTTPException(503, 'The configured AI model is not a supported text model; contact support')
    candidates = tuple(dict.fromkeys(((configured,) if configured else ()) + TEXT_MODELS))
    client = Groq(api_key=key, timeout=30.0, max_retries=0)
    for model in candidates:
        try:
            options = {'reasoning_effort': 'low'} if model.startswith('openai/gpt-oss-') else {}
            return client.chat.completions.create(
                model=model, messages=messages, temperature=temperature,
                max_completion_tokens=4096, **options,
            )
        except APIConnectionError:
            raise HTTPException(503, 'The AI provider could not be reached. Please try again later.') from None
        except APIStatusError as error:
            body = error.body if isinstance(error.body, dict) else {}
            detail = body.get('error', body)
            code = detail.get('code') if isinstance(detail, dict) else None
            if error.status_code in (403, 404) or (error.status_code == 400 and code in UNAVAILABLE_CODES):
                continue
            if error.status_code == 429:
                raise HTTPException(429, 'The AI provider request limit or allowance has been reached. Please try again later.') from None
            if error.status_code in (401, 402):
                raise HTTPException(503, 'AI provider authorization or billing needs administrator attention.') from None
            if error.status_code >= 500 or error.status_code in (408, 409):
                raise HTTPException(503, 'The AI provider is temporarily unavailable. Please try again later.') from None
            raise HTTPException(502, 'The AI provider could not generate this reply. Please try again later.') from None
        except APIError:
            raise HTTPException(502, 'The AI provider returned an unusable response. Please try again later.') from None
    raise HTTPException(503, 'No supported AI text model is available. Ask the administrator to check Groq model access.')
