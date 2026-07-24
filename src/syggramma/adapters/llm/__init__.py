"""LLM adapter for outreach message drafting.

Tries providers in order: Anthropic → OpenRouter → Grok → template fallback.
Whichever provider answers first with a valid key wins for that draft call.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from syggramma.config import Settings

_logger = logging.getLogger("syggramma.llm")


class MultiProviderDrafter:
    """Drafts outreach messages using the first available LLM provider.

    Provider order:
    1. Anthropic native API  (ANTHROPIC_API_KEY)
    2. OpenRouter            (OPENROUTER_API_KEY)
    3. xAI Grok              (GROK_API_KEY)
    4. Template fallback     (no API keys configured)
    """

    SYSTEM_PROMPT = """You are a courteous, professional outreach assistant for
a Greek academic publisher ("Εκδόσεις Κυριακίδη").  Write email drafts in Greek.

Rules:
- Be warm but not pushy.
- Mention the professor's name, department, and the specific book/course that
  connects you to them.
- Include the legal basis and the professor's GDPR rights (Article 14 notice).
- Never make up facts.  Only use the provided context.
- Keep the email under 200 words.
"""

    def __init__(self, settings: Settings | None = None) -> None:
        self._s = settings or Settings()

        # Native APIs (tried first if keys are set)
        self._anthropic_key = self._s.anthropic_api_key
        self._anthropic_model = self._s.anthropic_model
        self._grok_key = self._s.grok_api_key
        self._grok_model = self._s.grok_model

        # OpenRouter tiered models (tried in order if OR key is set)
        self._or_key = self._s.openrouter_api_key
        self._or_models = [
            self._s.openrouter_tier1_model,   # Claude Sonnet 5  $12/M
            self._s.openrouter_tier2_model,   # Gemini 2.5 Flash $3/M
            self._s.openrouter_tier3_model,   # DeepSeek V4 Pro $1/M
            self._s.openrouter_tier4_model,   # Gemini Flash Lite FREE
        ]
        self._or_tokens = self._s.openrouter_max_tokens
        self._or_attempted: list[str] = []  # Track which provider succeeded

    async def draft(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Draft an email. Tries: Native Anthropic -> Grok -> OR T1-T4 -> template."""
        ctx = context or {}
        user_msg = self._build_user_message(prompt, ctx)

        # 1. Native Anthropic API (if key set)
        result = await self._try_anthropic(user_msg)
        if result is not None:
            return result

        # 2. Native Grok API (if key set)
        result = await self._try_grok(user_msg)
        if result is not None:
            return result

        # 3. OpenRouter tiered models (T1 -> T4)
        if self._or_key:
            for model in self._or_models:
                result = await self._try_openrouter(model, user_msg)
                if result is not None:
                    return result

        # 4. Template fallback
        return self._template_draft(prompt, ctx)

    # ── Provider attempts ──────────────────────────────────────────────────

    async def _try_anthropic(self, user_msg: str) -> str | None:
        if not self._anthropic_key:
            return None
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as http:
                response = await http.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self._anthropic_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._anthropic_model,
                        "max_tokens": self._s.anthropic_max_tokens,
                        "system": self.SYSTEM_PROMPT,
                        "messages": [{"role": "user", "content": user_msg}],
                    },
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                return str(data["content"][0]["text"]).strip()
        except Exception:
            _logger.warning("Anthropic API call failed")
            return None

    async def _try_openrouter(self, model: str, user_msg: str) -> str | None:
        if not self._or_key:
            return None
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as http:
                response = await http.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._or_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": self._or_tokens,
                        "messages": [
                            {"role": "system", "content": self.SYSTEM_PROMPT},
                            {"role": "user", "content": user_msg},
                        ],
                    },
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                return str(data["choices"][0]["message"]["content"]).strip()
        except Exception:
            _logger.warning("OpenRouter API call failed for model %s", model)
            return None

    async def _try_grok(self, user_msg: str) -> str | None:
        if not self._grok_key:
            return None
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as http:
                response = await http.post(
                    "https://api.x.ai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._grok_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._grok_model,
                        "max_tokens": self._s.grok_max_tokens,
                        "messages": [
                            {"role": "system", "content": self.SYSTEM_PROMPT},
                            {"role": "user", "content": user_msg},
                        ],
                    },
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                return str(data["choices"][0]["message"]["content"]).strip()
        except Exception:
            _logger.warning("Grok API call failed")
            return None

    # ── Shared helpers ─────────────────────────────────────────────────────

    def _build_user_message(
        self, prompt: str, context: dict[str, Any],
    ) -> str:
        parts = [prompt]
        if context:
            parts.append("\n--- Context ---")
            for key, value in context.items():
                parts.append(f"{key}: {value}")
        return "\n".join(parts)

    def _template_draft(self, prompt: str, context: dict[str, Any]) -> str:
        """Simple template-based draft when all LLMs are unavailable."""
        display_name = context.get("display_name", "Αξιότιμε/η κύριε/α")
        facts = context.get("facts", [])
        facts_text = "\n".join(f"  • {f}" for f in facts) if facts else ""

        return f"""Αγαπητέ/ή {display_name},

Με την παρούσα επικοινωνία θα θέλαμε να σας ενημερώσουμε
σχετικά με το συγγραφικό σας έργο και τη δυνατότητα συνεργασίας
με τις Εκδόσεις Κυριακίδη.

{facts_text}

Είμαστε στη διάθεσή σας για οποιαδήποτε διευκρίνιση.

Με εκτίμηση,
Εκδόσεις Κυριακίδη"""
