import json
import re
from typing import Any, Callable, Dict, List, Optional, Tuple
import httpx


class LLMError(Exception):
    pass


class MultiProviderLLM:
    """
    Zero-downtime multi-provider AI brain with automatic fallback:
    Cerebras (1M tokens/day) -> Groq (1,000 req/day) -> Gemini Flash
    -> OpenRouter -> Ollama (Local) -> Pollinations (Zero-Key Free Fallback)
    """

    def __init__(self, config: Dict[str, Any], log_fn: Optional[Callable[[str], None]] = None):
        self.config = config
        self.log = log_fn or (lambda msg: None)
        self.last_provider_used: str = ""

    def get_active_providers(self) -> List[str]:
        order = self.config.get("provider_order") or [
            "groq",
            "gemini",
            "cerebras",
            "openrouter",
            "custom",
            "ollama",
            "pollinations",
        ]
        active: List[str] = []
        for p in order:
            if p == "cerebras" and self.config.get("cerebras_api_key"):
                active.append(p)
            elif p == "groq" and self.config.get("groq_api_key"):
                active.append(p)
            elif p == "gemini" and self.config.get("gemini_api_key"):
                active.append(p)
            elif p == "openrouter" and self.config.get("openrouter_api_key"):
                active.append(p)
            elif p == "custom" and self.config.get("custom_api_url") and self.config.get("custom_api_key"):
                active.append(p)
            elif p == "ollama" and self.config.get("ollama_model"):
                active.append(p)
            elif p == "pollinations" and self.config.get("pollinations_enabled", True):
                active.append(p)
        if not active:
            active.append("pollinations")
        return active

    async def _call_openai_compat(
        self,
        url: str,
        api_key: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 3500,
        extra_headers: Optional[Dict[str, str]] = None,
        timeout: float = 90.0,
    ) -> str:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if extra_headers:
            headers.update(extra_headers)

        payload: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                raise LLMError(f"HTTP {resp.status_code}: {resp.text[:260]}")
            data = resp.json()
            msg = data["choices"][0]["message"]
            content = (msg.get("content") or msg.get("reasoning") or msg.get("reasoning_content") or "").strip()
            # Strip <think>...</think> blocks if emitted by reasoning models
            content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
            if not content:
                raise LLMError("Empty response content")
            return content

    async def _call_gemini(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 3500,
    ) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                raise LLMError(f"HTTP {resp.status_code}: {resp.text[:260]}")
            data = resp.json()
            candidates = data.get("candidates") or []
            if not candidates:
                raise LLMError(f"Empty Gemini candidates: {str(data)[:180]}")
            parts = candidates[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts).strip()

    async def _call_pollinations(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 3200,
    ) -> str:
        """
        Zero-API-key free public text AI endpoint (tries unified & legacy routes).
        """
        endpoints = [
            ("https://text.pollinations.ai/openai", "openai"),
            ("https://gen.pollinations.ai/v1/chat/completions", "openai"),
            ("https://text.pollinations.ai/openai", "mistral"),
        ]
        last_err = ""
        for url, model in endpoints:
            try:
                return await self._call_openai_compat(
                    url=url,
                    api_key="",
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=75.0,
                )
            except Exception as exc:
                last_err = str(exc)
        raise LLMError(f"Pollinations Zero-Key endpoint busy: {last_err[:200]}")

    async def _call_provider(
        self,
        provider: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 3500,
    ) -> str:
        if provider == "cerebras":
            model = self.config.get("cerebras_model") or "llama-3.3-70b"
            return await self._call_openai_compat(
                "https://api.cerebras.ai/v1/chat/completions",
                self.config["cerebras_api_key"],
                model,
                system_prompt,
                user_prompt,
                temperature,
                max_tokens,
            )
        if provider == "groq":
            primary_model = self.config.get("groq_model") or "qwen/qwen3.8-27b"
            groq_models = list(dict.fromkeys([primary_model, "qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]))
            last_err = ""
            for gm in groq_models:
                try:
                    return await self._call_openai_compat(
                        "https://api.groq.com/openai/v1/chat/completions",
                        self.config["groq_api_key"],
                        gm,
                        system_prompt,
                        user_prompt,
                        temperature,
                        max_tokens,
                    )
                except Exception as exc:
                    last_err = str(exc)
                    if gm != groq_models[-1]:
                        self.log(f"Groq {gm} busy, auto-switching to {groq_models[-1]}...")
            raise LLMError(last_err)
        if provider == "gemini":
            primary_gem = self.config.get("gemini_model") or "gemini-flash-latest"
            gem_models = list(dict.fromkeys([primary_gem, "gemini-flash-latest", "gemini-3-flash-preview", "gemini-3.1-flash-lite"]))
            last_err = ""
            for gmod in gem_models:
                try:
                    return await self._call_gemini(
                        self.config["gemini_api_key"],
                        gmod,
                        system_prompt,
                        user_prompt,
                        temperature,
                        max_tokens,
                    )
                except Exception as exc:
                    last_err = str(exc)
            raise LLMError(last_err)
        if provider == "openrouter":
            primary_or = self.config.get("openrouter_model") or "google/gemma-4-31b-it:free"
            or_models = list(dict.fromkeys([primary_or, "google/gemma-4-31b-it:free", "google/gemma-4-26b-a4b-it:free", "nvidia/nemotron-3.5-lightning:free", "openrouter/free"]))
            last_err = ""
            for om in or_models:
                try:
                    return await self._call_openai_compat(
                        "https://openrouter.ai/api/v1/chat/completions",
                        self.config["openrouter_api_key"],
                        om,
                        system_prompt,
                        user_prompt,
                        temperature,
                        max_tokens,
                        extra_headers={
                            "HTTP-Referer": "http://127.0.0.1:8765",
                            "X-Title": "NEXUS STUDIO AI Video Factory",
                        },
                    )
                except Exception as exc:
                    last_err = str(exc)
            raise LLMError(last_err)
        if provider == "custom":
            base = (self.config.get("custom_api_url") or "").rstrip("/")
            url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
            model = self.config.get("custom_api_model") or "gpt-4o-mini"
            return await self._call_openai_compat(
                url,
                self.config.get("custom_api_key", ""),
                model,
                system_prompt,
                user_prompt,
                temperature,
                max_tokens,
            )
        if provider == "ollama":
            base = (self.config.get("ollama_url") or "http://localhost:11434").rstrip("/")
            model = self.config.get("ollama_model") or "llama3.2"
            return await self._call_openai_compat(
                f"{base}/v1/chat/completions",
                "ollama",
                model,
                system_prompt,
                user_prompt,
                temperature,
                max_tokens,
                timeout=120.0,
            )
        if provider == "pollinations":
            return await self._call_pollinations(system_prompt, user_prompt, temperature, max_tokens)

        raise LLMError(f"Unknown provider: {provider}")

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 3500,
    ) -> Tuple[str, str]:
        providers = self.get_active_providers()
        errors: List[str] = []
        for provider in providers:
            try:
                label = "ZERO-KEY AI" if provider == "pollinations" else provider.upper()
                self.log(f"AI Brain -> {label}...")
                text = await self._call_provider(provider, system_prompt, user_prompt, temperature, max_tokens)
                self.last_provider_used = provider
                return text, provider
            except Exception as exc:
                msg = str(exc)
                errors.append(f"{provider}: {msg[:150]}")
                self.log(f"{provider.upper()} unavailable ({msg[:80]}). Trying next provider...")

        raise LLMError("All AI providers failed:\n" + "\n".join(errors))

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.55,
        max_tokens: int = 4000,
    ) -> Tuple[Dict[str, Any], str]:
        strict_sys = (
            system_prompt
            + "\n\nCRITICAL JSON RULE: Return ONLY one valid, parseable JSON object. "
            "No preamble, no trailing notes, properly escape quotes and newlines inside strings."
        )
        raw, provider = await self.generate(strict_sys, user_prompt, temperature=temperature, max_tokens=max_tokens)
        parsed = extract_json(raw)
        if parsed is not None:
            return parsed, provider

        self.log("Self-healing JSON formatting...")
        repair_raw, provider = await self.generate(
            "You repair broken JSON into strict valid JSON. Return ONLY raw JSON with no markdown.",
            f"Repair this JSON while preserving all data:\n\n{raw}",
            temperature=0.1,
            max_tokens=max_tokens,
        )
        parsed = extract_json(repair_raw)
        if parsed is not None:
            return parsed, provider

        raise LLMError(f"JSON parse failed from {provider}: {raw[:220]}")

    async def test_provider(self, provider: str) -> Dict[str, Any]:
        try:
            reply = await self._call_provider(
                provider,
                "Reply with ONLY the word READY.",
                "Ping",
                temperature=0.0,
                max_tokens=160,
            )
            return {"ok": True, "provider": provider, "message": f"Connected ({reply[:24]})"}
        except Exception as exc:
            return {"ok": False, "provider": provider, "message": str(exc)[:180]}


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()

    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except Exception:
            # Strip trailing commas common in LLM JSON
            cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
            try:
                obj = json.loads(cleaned)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
    return None
