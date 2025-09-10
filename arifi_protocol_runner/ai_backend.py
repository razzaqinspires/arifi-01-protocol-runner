"""
ai_backend.py

Abstraksi backend LLM untuk Arifi-01 Protocol Runner.

Current implementations:
- OpenAI (via openai Python package) if OPENAI_API_KEY set
- Local/Stub fallback

Usage:
    backend = AIBackend()
    code = backend.generate_code(prompt, language="python")
    repaired = backend.repair_code(code, analysis_report)
"""

import os
import time
import json
from typing import Optional, Dict

# Try import openai if available
try:
    import openai  # type: ignore
    OPENAI_PKG = True
except Exception:
    OPENAI_PKG = False

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # must be set by user if using OpenAI

class AIBackend:
    def __init__(self, provider: Optional[str] = None, max_retry: int = 2, model: str = "gpt-4o-mini"):
        """
        provider: 'openai' or None (auto)
        model: default model name (change as desired)
        """
        self.provider = provider or ("openai" if OPENAI_PKG and OPENAI_API_KEY else "local")
        self.max_retry = max_retry
        self.model = model
        if self.provider == "openai" and OPENAI_PKG:
            openai.api_key = OPENAI_API_KEY

    def generate_code(self, prompt: str, language: str = "python", instructions: Optional[str] = None, max_tokens: int = 2000) -> Dict:
        """
        Ask the LLM to generate an implementation for the prompt.
        Returns dict with keys: { 'success': bool, 'code': str, 'meta': {...} }
        """
        system_msg = (
            "You are an assistant that writes correct, well-documented, and testable code."
            " If asked for JavaScript produce idiomatic Node.js-compatible JS (CommonJS or ESM as requested)."
            " If asked for Python produce Python 3.8+ code with functions/classes and minimal external deps."
            " Always return only the code block in triple backticks if possible, and include a short JSON metadata block if requested."
        )
        user_msg = f"{prompt}\n\nTarget language: {language}\nRequirements: produce a full, runnable implementation, and include comments and example usage."

        if self.provider == "openai" and OPENAI_PKG:
            try:
                for attempt in range(self.max_retry + 1):
                    resp = openai.ChatCompletion.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": system_msg},
                            {"role": "user", "content": user_msg},
                        ],
                        max_tokens=max_tokens,
                        temperature=0.2,
                    )
                    text = resp["choices"][0]["message"]["content"].strip()
                    code = self._extract_code(text)
                    if code:
                        return {"success": True, "code": code, "raw": text, "meta": {"provider": "openai", "model": self.model}}
                    # fallback: return raw text if no triple-backtick code
                    if attempt < self.max_retry:
                        time.sleep(1 + attempt * 1)
                        continue
                    return {"success": True, "code": text, "raw": text, "meta": {"provider": "openai", "model": self.model}}
            except Exception as e:
                return {"success": False, "error": str(e)}
        else:
            # Local / stub behaviour: generate simple templates
            template = ""
            if language.lower().startswith("js"):
                template = f"""// Generated (stub) JavaScript code for prompt:
// {prompt}

function tambah(a, b) {{
  return a + b;
}}

// Example usage:
console.log("2 + 3 =", tambah(2, 3));
"""
            else:
                template = f'''# Generated (stub) Python code for prompt:
# {prompt}

def tambah(a, b):
    return a + b

if __name__ == "__main__":
    print("2 + 3 =", tambah(2, 3))
'''
            return {"success": True, "code": template, "meta": {"provider": "local", "model": "stub"}}

    def repair_code(self, code: str, analysis_report: Dict, language: str = "python", max_tokens: int = 1500) -> Dict:
        """
        Provide the LLM with code and analysis report, ask it to repair/fix.
        Returns same structure as generate_code.
        """
        if self.provider == "openai" and OPENAI_PKG:
            system_msg = "You are a code repair assistant. Read the code and the analysis report and return a corrected, runnable version."
            user_msg = (
                "Code:\n```\n" + code + "\n```\n\n"
                "Analysis report (lint/errors):\n" + json.dumps(analysis_report, indent=2) + "\n\n"
                "Please return only the repaired code inside triple backticks, and nothing else."
            )
            try:
                resp = openai.ChatCompletion.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    max_tokens=max_tokens,
                    temperature=0.0,
                )
                text = resp["choices"][0]["message"]["content"].strip()
                code_out = self._extract_code(text) or text
                return {"success": True, "code": code_out, "raw": text, "meta": {"provider": "openai", "model": self.model}}
            except Exception as e:
                return {"success": False, "error": str(e)}
        else:
            # Local fallback: no changes
            return {"success": True, "code": code, "meta": {"provider": "local", "note": "no-op repair"}}

    @staticmethod
    def _extract_code(text: str) -> Optional[str]:
        """
        If the model returns fenced code, extract it. Otherwise return None.
        """
        import re
        m = re.search(r"```(?:\w+)?\\n([\\s\\S]*?)\\n```", text)
        if m:
            return m.group(1)
        # try triple backtick without language
        m2 = re.search(r"```\\n([\\s\\S]*?)\\n```", text)
        if m2:
            return m2.group(1)
        return None