"""LLM adapter for outreach message drafting.

Tries providers in order: Anthropic → OpenRouter → Grok → template fallback.
Whichever provider answers first with a valid key wins for that draft call.
"""

from __future__ import annotations

from typing import Any

import httpx

from syggramma.config import Settings


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
        self._settings = settings or Settings()

        # Provider 1: Anthropic
        self._anthropic_key = self._settings.anthropic_api_key
        self._anthropic_model = self._settings.anthropic_model
        self._anthropic_tokens = self._settings.anthropic_max_tokens

        # Provider 2: OpenRouter
        self._openrouter_key = self._settings.openrouter_api_key
        self._openrouter_model = self._settings.openrouter_model
        self._openrouter_tokens = self._settings.openrouter_max_tokens

        # Provider 3: Grok
        self._grok_key = self._settings.grok_api_key
        self._grok_model = self._settings.grok_model
        self._grok_tokens = self._settings.grok_max_tokens

    async def draft(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Draft an email body.  Tries providers in order; falls back to template."""
        ctx = context or {}
        user_msg = self._build_user_message(prompt, ctx)

        # Try each provider in order
        for attempt in [self._try_anthropic, self._try_openrouter, self._try_grok]:
            result = await attempt(user_msg)
            if result is not None:
                return result

        # All providers failed — use template fallback
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
                        "max_tokens": self._anthropic_tokens,
                        "system": self.SYSTEM_PROMPT,
                        "messages": [{"role": "user", "content": user_msg}],
                    },
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                return str(data["content"][0]["text"]).strip()
        except Exception:
            return None  # fall through to next provider

    async def _try_openrouter(self, user_msg: str) -> str | None:
        if not self._openrouter_key:
            return None
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as http:
                response = await http.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._openrouter_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._openrouter_model,
                        "max_tokens": self._openrouter_tokens,
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
                        "max_tokens": self._grok_tokens,
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
