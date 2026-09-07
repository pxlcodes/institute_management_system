from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


class ExternalAIAgent:
    """External AI Agent client for falling back when local SQL/regex rules cannot answer.

    Supports OpenAI, Gemini, Anthropic, DeepSeek, Groq, and local Ollama without external dependencies.
    """

    def __init__(
        self,
        api_key: str = "",
        provider: str = "auto",
        model: str = "",
        endpoint: str = "",
        timeout: int = 25,
    ):
        if not api_key and not any(os.environ.get(k) for k in ("GEMINI_API_KEY", "ELH_GEMINI_API_KEY", "AI_API_KEY", "OPENAI_API_KEY")):
            try:
                from elh.config import DEFAULT_ENV_FILE, _read_env_file
                env_vals = _read_env_file(DEFAULT_ENV_FILE)
                if not os.environ.get("GEMINI_API_KEY"):
                    k = env_vals.get("ELH_GEMINI_API_KEY") or env_vals.get("GEMINI_API_KEY")
                    if k:
                        os.environ["GEMINI_API_KEY"] = k
                if not os.environ.get("AI_PROVIDER") and env_vals.get("ELH_AI_PROVIDER"):
                    os.environ["AI_PROVIDER"] = env_vals["ELH_AI_PROVIDER"]
                if not os.environ.get("AI_MODEL") and env_vals.get("ELH_AI_MODEL"):
                    os.environ["AI_MODEL"] = env_vals["ELH_AI_MODEL"]
            except Exception:
                pass

        self.api_key = (
            api_key
            or os.environ.get("GEMINI_API_KEY", "")
            or os.environ.get("ELH_GEMINI_API_KEY", "")
            or os.environ.get("AI_API_KEY", "")
            or os.environ.get("OPENAI_API_KEY", "")
            or os.environ.get("DEEPSEEK_API_KEY", "")
            or os.environ.get("GROQ_API_KEY", "")
            or os.environ.get("ANTHROPIC_API_KEY", "")
        )
        self.provider = (provider or os.environ.get("AI_PROVIDER") or os.environ.get("ELH_AI_PROVIDER") or "auto").lower()
        self.model = model or os.environ.get("AI_MODEL") or os.environ.get("ELH_AI_MODEL") or ""
        self.endpoint = endpoint or os.environ.get("AI_ENDPOINT", "")
        self.timeout = int(os.environ.get("AI_TIMEOUT") or timeout or 25)

    def is_configured(self) -> bool:
        """Check if an external AI key or local Ollama is available."""
        if self.api_key:
            return True
        if os.environ.get("GEMINI_API_KEY") or os.environ.get("ELH_GEMINI_API_KEY"):
            return True
        if self.provider in {"ollama", "local"}:
            return True
        if os.environ.get("OLLAMA_HOST") or os.environ.get("OLLAMA_ENDPOINT"):
            return True
        return False

    def query(self, prompt: str, system_context: str | None = None) -> tuple[bool, str]:
        """Query external AI provider with the user prompt and return (success, response_text)."""
        default_system = (
            "You are the AI Assistant for the Expert Learning Hub (ELH) Management System in Kathmandu, Nepal. "
            "Provide clear, professional, concise, and helpful answers for educational, institute management, "
            "academic, accounting, or technical queries."
        )
        sys_prompt = f"{default_system}\n\n{system_context}" if system_context else default_system

        # 1. Google Gemini API
        gemini_key = (
            (self.api_key if self.provider in {"gemini", "auto"} else "")
            or os.environ.get("GEMINI_API_KEY", "")
            or os.environ.get("ELH_GEMINI_API_KEY", "")
            or self.api_key
        )
        if self.provider == "gemini" or os.environ.get("GEMINI_API_KEY") or os.environ.get("ELH_GEMINI_API_KEY") or (gemini_key and self.provider == "auto"):
            model = self.model or "gemini-3.6-flash"
            return self._call_gemini(gemini_key, model, prompt, sys_prompt)

        # 2. Anthropic API
        if os.environ.get("ANTHROPIC_API_KEY") or (self.provider == "anthropic" and self.api_key):
            key = os.environ.get("ANTHROPIC_API_KEY") or self.api_key
            model = self.model or "claude-3-5-sonnet-20241022"
            return self._call_anthropic(key, model, prompt, sys_prompt)

        # 3. Local Ollama (if configured or provider is ollama or running locally)
        if self.provider in {"ollama", "local"} or (not self.api_key and self._is_ollama_alive()):
            return self._call_ollama(prompt, sys_prompt)

        # 4. OpenAI / DeepSeek / Groq / Compatible Endpoint
        if self.api_key or self.endpoint:
            key = self.api_key
            model = self.model or "gpt-4o-mini"
            endpoint = self.endpoint or "https://api.openai.com/v1/chat/completions"
            if os.environ.get("DEEPSEEK_API_KEY") and not self.endpoint:
                endpoint = "https://api.deepseek.com/chat/completions"
                model = self.model or "deepseek-chat"
            elif os.environ.get("GROQ_API_KEY") and not self.endpoint:
                endpoint = "https://api.groq.com/openai/v1/chat/completions"
                model = self.model or "llama-3.3-70b-versatile"

            return self._call_openai_compatible(endpoint, key, model, prompt, sys_prompt)

        # 5. Not configured
        return (
            False,
            "No external AI provider configured.\n\n"
            "To enable external AI agent reasoning when internal queries don't match, set one of the following:\n"
            "  • set OPENAI_API_KEY=sk-...\n"
            "  • set GEMINI_API_KEY=AIza...\n"
            "  • set DEEPSEEK_API_KEY=sk-...\n"
            "  • set GROQ_API_KEY=gsk_...\n"
            "  • Or run a local Ollama server (http://localhost:11434)",
        )

    def _call_openai_compatible(
        self, endpoint: str, key: str, model: str, prompt: str, system_prompt: str
    ) -> tuple[bool, str]:
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 800,
        }

        try:
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = data["choices"][0]["message"]["content"].strip()
                return True, text
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", errors="ignore")
            return False, f"External AI API Error (HTTP {err.code}): {body[:200]}"
        except Exception as err:
            return False, f"External AI Connection Error: {str(err)}"

    def _call_gemini(
        self, key: str, model: str, prompt: str, system_prompt: str
    ) -> tuple[bool, str]:
        models_to_try = [model] if model else []
        for candidate in ["gemini-3.6-flash", "gemini-flash-latest"]:
            if candidate not in models_to_try:
                models_to_try.append(candidate)

        last_error = ""
        for m in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
            payload = {
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 800, "temperature": 0.3},
            }
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "x-goog-api-key": key,
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts and "text" in parts[0]:
                            return True, parts[0]["text"].strip()
                    return False, "Gemini returned an empty or unparseable response."
            except urllib.error.HTTPError as err:
                body = err.read().decode("utf-8", errors="ignore")
                last_error = f"Gemini API Error (HTTP {err.code}): {body[:200]}"
                if err.code in {404, 400} and ("not found" in body.lower() or "no longer available" in body.lower()):
                    continue
                return False, last_error
            except Exception as err:
                return False, f"Gemini Connection Error: {str(err)}"

        return False, last_error or "Unable to complete request with Gemini."

    def _call_anthropic(
        self, key: str, model: str, prompt: str, system_prompt: str
    ) -> tuple[bool, str]:
        url = "https://api.anthropic.com/v1/messages"
        payload = {
            "model": model,
            "max_tokens": 800,
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = data["content"][0]["text"].strip()
                return True, text
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", errors="ignore")
            return False, f"Anthropic API Error (HTTP {err.code}): {body[:200]}"
        except Exception as err:
            return False, f"Anthropic Connection Error: {str(err)}"

    def _call_ollama(self, prompt: str, system_prompt: str) -> tuple[bool, str]:
        base = os.environ.get(
            "OLLAMA_HOST", os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")
        ).rstrip("/")
        url = f"{base}/api/generate"
        model = self.model or "llama3.2"
        payload = {
            "model": model,
            "system": system_prompt,
            "prompt": prompt,
            "stream": False,
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return True, data.get("response", "").strip()
        except Exception as err:
            return False, f"Local Ollama Error: {str(err)}"

    def _is_ollama_alive(self) -> bool:
        base = os.environ.get(
            "OLLAMA_HOST", os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")
        ).rstrip("/")
        try:
            req = urllib.request.Request(f"{base}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=1.5):
                return True
        except Exception:
            return False
