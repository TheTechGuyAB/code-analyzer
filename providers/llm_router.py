"""
LLM Provider abstraction — unified interface for multiple AI providers.

Supports: Anthropic, OpenAI, Groq, Google Gemini, Ollama (local).
Each provider normalizes to the same request/response format.
"""

import json
import os
import time
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMResponse:
    """Normalized response from any provider."""
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    provider: str = ""
    latency_ms: int = 0
    cost_usd: float = 0.0


@dataclass
class ModelConfig:
    """Configuration for a specific model."""
    provider: str          # anthropic, openai, groq, google, ollama
    model: str             # model identifier
    display_name: str      # human-readable name
    max_tokens: int = 4096
    temperature: float = 0.2
    # Cost per 1M tokens (input/output) — for estimation
    cost_input_per_m: float = 0.0
    cost_output_per_m: float = 0.0


# ── Pre-defined model profiles ──────────────────────────────────────

MODELS = {
    # ── Fast & cheap — scanning, classification, simple extraction ──
    "scout-fast": ModelConfig(
        provider="groq", model="llama-3.3-70b-versatile",
        display_name="Llama 3.3 70B (Groq)",
        max_tokens=2048, temperature=0.1,
        cost_input_per_m=0.59, cost_output_per_m=0.79,
    ),
    "scout-fast-google": ModelConfig(
        provider="google", model="gemini-2.0-flash",
        display_name="Gemini 2.0 Flash",
        max_tokens=2048, temperature=0.1,
        cost_input_per_m=0.10, cost_output_per_m=0.40,
    ),
    "scout-fast-openai": ModelConfig(
        provider="openai", model="gpt-4o-mini",
        display_name="GPT-4o Mini",
        max_tokens=2048, temperature=0.1,
        cost_input_per_m=0.15, cost_output_per_m=0.60,
    ),

    # ── Mid-tier — analysis, pattern detection ──
    "analyst-mid": ModelConfig(
        provider="anthropic", model="claude-sonnet-4-20250514",
        display_name="Claude Sonnet 4",
        max_tokens=8192, temperature=0.2,
        cost_input_per_m=3.0, cost_output_per_m=15.0,
    ),
    "analyst-mid-openai": ModelConfig(
        provider="openai", model="gpt-4o",
        display_name="GPT-4o",
        max_tokens=8192, temperature=0.2,
        cost_input_per_m=2.50, cost_output_per_m=10.0,
    ),
    "analyst-mid-google": ModelConfig(
        provider="google", model="gemini-2.5-pro",
        display_name="Gemini 2.5 Pro",
        max_tokens=8192, temperature=0.2,
        cost_input_per_m=1.25, cost_output_per_m=10.0,
    ),

    # ── Heavy — deep reasoning, architecture review ──
    "deep-heavy": ModelConfig(
        provider="anthropic", model="claude-opus-4-20250514",
        display_name="Claude Opus 4",
        max_tokens=16384, temperature=0.3,
        cost_input_per_m=15.0, cost_output_per_m=75.0,
    ),
    "deep-heavy-openai": ModelConfig(
        provider="openai", model="o3",
        display_name="OpenAI o3",
        max_tokens=16384, temperature=1.0,  # o3 ignores temperature
        cost_input_per_m=10.0, cost_output_per_m=40.0,
    ),

    # ── Local — no cost, private, slower ──
    "local-fast": ModelConfig(
        provider="ollama", model="llama3.2:3b",
        display_name="Llama 3.2 3B (local)",
        max_tokens=2048, temperature=0.1,
    ),
    "local-mid": ModelConfig(
        provider="ollama", model="qwen2.5-coder:14b",
        display_name="Qwen 2.5 Coder 14B (local)",
        max_tokens=4096, temperature=0.2,
    ),
    "local-heavy": ModelConfig(
        provider="ollama", model="qwen2.5-coder:32b",
        display_name="Qwen 2.5 Coder 32B (local)",
        max_tokens=8192, temperature=0.3,
    ),
}

# ── Phase → model mapping (default recommendation) ──

DEFAULT_PHASE_MODELS = {
    "scan":       "scout-fast",         # Quick file scanning, stack detection
    "analyze":    "analyst-mid",        # Architecture & code quality analysis
    "specialist": "analyst-mid",        # Focused specialist analysis
    "deep":       "deep-heavy",         # Deep reasoning for critical findings
    "report":     "scout-fast",         # Report structure/formatting
    "validate":   "scout-fast",         # Schema validation pass
}

# Budget-friendly alternative
BUDGET_PHASE_MODELS = {
    "scan":       "scout-fast",
    "analyze":    "scout-fast",          # Use Groq for everything
    "specialist": "scout-fast",
    "deep":       "analyst-mid",         # Only use Sonnet for deep
    "report":     "scout-fast",
    "validate":   "scout-fast",
}

# All-local alternative
LOCAL_PHASE_MODELS = {
    "scan":       "local-fast",
    "analyze":    "local-mid",
    "specialist": "local-mid",
    "deep":       "local-heavy",
    "report":     "local-fast",
    "validate":   "local-fast",
}

PROFILES = {
    "default": DEFAULT_PHASE_MODELS,
    "budget": BUDGET_PHASE_MODELS,
    "local": LOCAL_PHASE_MODELS,
}


class BaseProvider(ABC):
    """Abstract base for LLM providers."""

    @abstractmethod
    def chat(self, system: str, user: str, config: ModelConfig) -> LLMResponse:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...


class AnthropicProvider(BaseProvider):
    def __init__(self):
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def chat(self, system: str, user: str, config: ModelConfig) -> LLMResponse:
        import anthropic
        client = anthropic.Anthropic(api_key=self.api_key)
        start = time.time()

        resp = client.messages.create(
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )

        text = "\n".join(b.text for b in resp.content if b.type == "text")
        latency = int((time.time() - start) * 1000)
        cost = (
            resp.usage.input_tokens * config.cost_input_per_m / 1_000_000
            + resp.usage.output_tokens * config.cost_output_per_m / 1_000_000
        )

        return LLMResponse(
            text=text,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            model=config.model,
            provider="anthropic",
            latency_ms=latency,
            cost_usd=cost,
        )


class OpenAIProvider(BaseProvider):
    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def chat(self, system: str, user: str, config: ModelConfig) -> LLMResponse:
        from openai import OpenAI
        client = OpenAI(api_key=self.api_key)
        start = time.time()

        resp = client.chat.completions.create(
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )

        text = resp.choices[0].message.content or ""
        latency = int((time.time() - start) * 1000)
        in_tok = resp.usage.prompt_tokens if resp.usage else 0
        out_tok = resp.usage.completion_tokens if resp.usage else 0
        cost = (
            in_tok * config.cost_input_per_m / 1_000_000
            + out_tok * config.cost_output_per_m / 1_000_000
        )

        return LLMResponse(
            text=text, input_tokens=in_tok, output_tokens=out_tok,
            model=config.model, provider="openai",
            latency_ms=latency, cost_usd=cost,
        )


class GroqProvider(BaseProvider):
    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def chat(self, system: str, user: str, config: ModelConfig) -> LLMResponse:
        from groq import Groq
        client = Groq(api_key=self.api_key)
        start = time.time()

        resp = client.chat.completions.create(
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )

        text = resp.choices[0].message.content or ""
        latency = int((time.time() - start) * 1000)
        in_tok = resp.usage.prompt_tokens if resp.usage else 0
        out_tok = resp.usage.completion_tokens if resp.usage else 0
        cost = (
            in_tok * config.cost_input_per_m / 1_000_000
            + out_tok * config.cost_output_per_m / 1_000_000
        )

        return LLMResponse(
            text=text, input_tokens=in_tok, output_tokens=out_tok,
            model=config.model, provider="groq",
            latency_ms=latency, cost_usd=cost,
        )


class GoogleProvider(BaseProvider):
    def __init__(self):
        self.api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def chat(self, system: str, user: str, config: ModelConfig) -> LLMResponse:
        import google.generativeai as genai
        genai.configure(api_key=self.api_key)
        start = time.time()

        model = genai.GenerativeModel(
            config.model,
            system_instruction=system,
        )
        resp = model.generate_content(
            user,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=config.max_tokens,
                temperature=config.temperature,
            ),
        )

        text = resp.text or ""
        latency = int((time.time() - start) * 1000)
        # Gemini usage metadata
        in_tok = getattr(resp.usage_metadata, 'prompt_token_count', 0) if hasattr(resp, 'usage_metadata') else 0
        out_tok = getattr(resp.usage_metadata, 'candidates_token_count', 0) if hasattr(resp, 'usage_metadata') else 0
        cost = (
            in_tok * config.cost_input_per_m / 1_000_000
            + out_tok * config.cost_output_per_m / 1_000_000
        )

        return LLMResponse(
            text=text, input_tokens=in_tok, output_tokens=out_tok,
            model=config.model, provider="google",
            latency_ms=latency, cost_usd=cost,
        )


class OllamaProvider(BaseProvider):
    def __init__(self):
        self.base_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

    def is_available(self) -> bool:
        try:
            import urllib.request
            urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=2)
            return True
        except Exception:
            return False

    def chat(self, system: str, user: str, config: ModelConfig) -> LLMResponse:
        import urllib.request
        start = time.time()

        payload = json.dumps({
            "model": config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {
                "num_predict": config.max_tokens,
                "temperature": config.temperature,
            },
        }).encode()

        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read())

        text = data.get("message", {}).get("content", "")
        latency = int((time.time() - start) * 1000)
        in_tok = data.get("prompt_eval_count", 0)
        out_tok = data.get("eval_count", 0)

        return LLMResponse(
            text=text, input_tokens=in_tok, output_tokens=out_tok,
            model=config.model, provider="ollama",
            latency_ms=latency, cost_usd=0.0,  # Local = free
        )


# ── Provider registry ──

PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "groq": GroqProvider,
    "google": GoogleProvider,
    "ollama": OllamaProvider,
}


class LLMRouter:
    """
    Routes LLM calls to the right provider based on phase configuration.
    Handles fallbacks if a provider is unavailable.
    """

    def __init__(self, phase_models: dict[str, str], verbose: bool = False):
        self.phase_models = phase_models
        self.verbose = verbose
        self._providers: dict[str, BaseProvider] = {}
        self._total_cost = 0.0
        self._total_tokens = {"input": 0, "output": 0}
        self._call_log: list[dict] = []

    def _get_provider(self, name: str) -> BaseProvider:
        if name not in self._providers:
            cls = PROVIDERS.get(name)
            if not cls:
                raise ValueError(f"Unknown provider: {name}")
            self._providers[name] = cls()
        return self._providers[name]

    def check_availability(self) -> dict[str, bool]:
        """Check which providers are available."""
        result = {}
        needed = set()
        for phase, model_key in self.phase_models.items():
            cfg = MODELS.get(model_key)
            if cfg:
                needed.add(cfg.provider)

        for provider_name in needed:
            try:
                p = self._get_provider(provider_name)
                result[provider_name] = p.is_available()
            except Exception:
                result[provider_name] = False

        return result

    def chat(self, phase: str, system: str, user: str,
             override_model: str = None) -> LLMResponse:
        """
        Send a chat request routed by phase.

        Args:
            phase: Pipeline phase (scan, analyze, specialist, deep, report, validate)
            system: System prompt
            user: User prompt
            override_model: Override the phase model with a specific model key
        """
        model_key = override_model or self.phase_models.get(phase, "analyst-mid")
        config = MODELS.get(model_key)
        if not config:
            raise ValueError(f"Unknown model key: {model_key}")

        provider = self._get_provider(config.provider)

        if not provider.is_available():
            # Try fallback
            config, provider = self._find_fallback(phase, config)

        if self.verbose:
            print(f"    [{phase}] → {config.display_name} ({config.provider})",
                  file=sys.stderr)

        resp = provider.chat(system, user, config)

        # Track costs
        self._total_cost += resp.cost_usd
        self._total_tokens["input"] += resp.input_tokens
        self._total_tokens["output"] += resp.output_tokens
        self._call_log.append({
            "phase": phase,
            "model": resp.model,
            "provider": resp.provider,
            "input_tokens": resp.input_tokens,
            "output_tokens": resp.output_tokens,
            "latency_ms": resp.latency_ms,
            "cost_usd": resp.cost_usd,
        })

        return resp

    def chat_json(self, phase: str, system: str, user: str,
                  override_model: str = None) -> dict:
        """Send a chat request and parse the response as JSON."""
        full_system = (
            system + "\n\n"
            "CRITICAL: Respond ONLY with valid JSON. No markdown backticks, "
            "no preamble, no explanation outside JSON. Just the JSON object/array."
        )
        resp = self.chat(phase, full_system, user, override_model)
        return self._parse_json(resp.text)

    def _parse_json(self, text: str) -> dict:
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON in the response
            for start_char, end_char in [("{", "}"), ("[", "]")]:
                start = text.find(start_char)
                end = text.rfind(end_char) + 1
                if start >= 0 and end > start:
                    try:
                        return json.loads(text[start:end])
                    except json.JSONDecodeError:
                        continue
            raise ValueError(f"Could not parse JSON from response: {text[:300]}...")

    def _find_fallback(self, phase: str, original: ModelConfig) -> tuple:
        """Find an available fallback provider for a phase."""
        # Fallback order based on tier
        fallback_chains = {
            "scout-fast": ["scout-fast-openai", "scout-fast-google", "local-fast"],
            "scout-fast-google": ["scout-fast", "scout-fast-openai", "local-fast"],
            "scout-fast-openai": ["scout-fast", "scout-fast-google", "local-fast"],
            "analyst-mid": ["analyst-mid-openai", "analyst-mid-google", "local-mid"],
            "analyst-mid-openai": ["analyst-mid", "analyst-mid-google", "local-mid"],
            "analyst-mid-google": ["analyst-mid", "analyst-mid-openai", "local-mid"],
            "deep-heavy": ["deep-heavy-openai", "analyst-mid", "local-heavy"],
            "deep-heavy-openai": ["deep-heavy", "analyst-mid", "local-heavy"],
            "local-fast": ["scout-fast", "scout-fast-openai"],
            "local-mid": ["analyst-mid", "analyst-mid-openai"],
            "local-heavy": ["deep-heavy", "analyst-mid"],
        }

        model_key = self.phase_models.get(phase, "analyst-mid")
        chain = fallback_chains.get(model_key, [])

        for fallback_key in chain:
            fb_config = MODELS.get(fallback_key)
            if not fb_config:
                continue
            try:
                fb_provider = self._get_provider(fb_config.provider)
                if fb_provider.is_available():
                    if self.verbose:
                        print(f"    ⚠️  {original.provider} unavailable, "
                              f"falling back to {fb_config.display_name}",
                              file=sys.stderr)
                    return fb_config, fb_provider
            except Exception:
                continue

        raise RuntimeError(
            f"No available provider for phase '{phase}'. "
            f"Tried: {original.provider} + {[MODELS[k].provider for k in chain if k in MODELS]}"
        )

    def get_cost_summary(self) -> dict:
        return {
            "total_cost_usd": round(self._total_cost, 6),
            "total_input_tokens": self._total_tokens["input"],
            "total_output_tokens": self._total_tokens["output"],
            "calls": self._call_log,
        }
