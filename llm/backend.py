"""
Hybrid LLM backend.

Design goal (per project decision): **best quality with keyless reproducibility**.

- If an OpenAI key is available, use **GPT-4o** — the high-quality demo/dev path.
- Otherwise fall back to a local **CodeLlama-7B-Instruct (4-bit)** model so the
  pipeline still runs end-to-end on a Colab T4 GPU with no API key and no crash.

Every agent calls `call_llm(prompt, system=...)` and is completely agnostic to
which backend is active. Selection happens once, lazily, and is cached.

Override with the environment variable ``LLM_BACKEND`` = ``auto`` | ``openai`` |
``codellama`` (default ``auto``).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

# Loaded lazily so this module imports cleanly even without the deps present.
try:  # local dev convenience; absent on Colab is fine
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - optional dependency
    pass


DEFAULT_OPENAI_MODEL = "gpt-4o"
DEFAULT_CODELLAMA_MODEL = "codellama/CodeLlama-7b-Instruct-hf"
DEFAULT_TEMPERATURE = 0.2
MAX_RETRIES = 3


@dataclass
class LLMBackend:
    """Resolved backend description. `kind` is 'openai' or 'codellama'."""

    kind: str
    model: str
    detail: str = ""


# Module-level singletons, initialized on first use.
_backend: Optional[LLMBackend] = None
_openai_client = None
_hf_model = None
_hf_tokenizer = None


def _resolve_openai_key() -> Optional[str]:
    """Find an OpenAI key from env or, when on Colab, from Colab Secrets."""
    key = os.getenv("OPENAI_API_KEY")
    if key:
        return key
    # Colab Secrets path — only available inside a Colab runtime.
    try:  # pragma: no cover - Colab-only
        from google.colab import userdata  # type: ignore

        return userdata.get("OPENAI_API_KEY")
    except Exception:
        return None


def get_backend() -> LLMBackend:
    """
    Decide which backend to use (cached after first call).

    `auto`      -> openai if a key exists, else codellama
    `openai`    -> force OpenAI (warns if no key)
    `codellama` -> force the local model
    """
    global _backend
    if _backend is not None:
        return _backend

    choice = os.getenv("LLM_BACKEND", "auto").lower().strip()
    key = _resolve_openai_key()

    if choice == "openai" or (choice == "auto" and key):
        if not key:
            print(
                "[llm] LLM_BACKEND=openai but no OPENAI_API_KEY found; "
                "calls will fail until a key is set."
            )
        _backend = LLMBackend(
            kind="openai",
            model=os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
            detail="OpenAI API (best quality)",
        )
    else:
        _backend = LLMBackend(
            kind="codellama",
            model=os.getenv("CODELLAMA_MODEL", DEFAULT_CODELLAMA_MODEL),
            detail="local 4-bit CodeLlama (keyless fallback)",
        )

    print(f"[llm] backend selected: {_backend.kind} — {_backend.detail}")
    return _backend


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI

        _openai_client = OpenAI(api_key=_resolve_openai_key())
    return _openai_client


def _load_codellama():
    """Lazily load the quantized CodeLlama model + tokenizer (Colab GPU)."""
    global _hf_model, _hf_tokenizer
    if _hf_model is not None:
        return _hf_model, _hf_tokenizer

    import torch  # noqa: F401  (imported for side-effect / availability check)
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
    )

    model_id = get_backend().model
    print(f"[llm] loading {model_id} (4-bit). First run downloads weights…")
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype="float16",
        bnb_4bit_quant_type="nf4",
    )
    _hf_tokenizer = AutoTokenizer.from_pretrained(model_id)
    _hf_model = AutoModelForCausalLM.from_pretrained(
        model_id,
        quantization_config=bnb,
        device_map="auto",
    )
    print("[llm] CodeLlama ready.")
    return _hf_model, _hf_tokenizer


def _call_openai(prompt: str, system: str, temperature: float) -> str:
    client = _get_openai_client()
    backend = get_backend()
    resp = client.chat.completions.create(
        model=backend.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""


def _call_codellama(prompt: str, system: str, temperature: float) -> str:
    model, tokenizer = _load_codellama()
    # CodeLlama-Instruct chat format.
    full = f"<s>[INST] <<SYS>>\n{system}\n<</SYS>>\n\n{prompt} [/INST]"
    inputs = tokenizer(full, return_tensors="pt").to(model.device)
    output = model.generate(
        **inputs,
        max_new_tokens=2048,
        temperature=max(temperature, 0.01),
        do_sample=temperature > 0,
        pad_token_id=tokenizer.eos_token_id,
    )
    # Decode only the newly generated tokens (strip the prompt echo).
    generated = output[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(generated, skip_special_tokens=True).strip()


def call_llm(
    prompt: str,
    system: str = "You are a senior Python engineer.",
    temperature: float = DEFAULT_TEMPERATURE,
) -> str:
    """
    Send a prompt to the active backend and return the text response.

    Retries with exponential backoff on transient failures (network, rate
    limits). Raises the last exception if all retries are exhausted.
    """
    backend = get_backend()
    last_exc: Optional[Exception] = None

    for attempt in range(MAX_RETRIES):
        try:
            if backend.kind == "openai":
                return _call_openai(prompt, system, temperature)
            return _call_codellama(prompt, system, temperature)
        except Exception as exc:  # noqa: BLE001 - we re-raise after retries
            last_exc = exc
            wait = 2 ** attempt
            print(
                f"[llm] call failed (attempt {attempt + 1}/{MAX_RETRIES}): "
                f"{exc}. Retrying in {wait}s…"
            )
            time.sleep(wait)

    raise RuntimeError(f"LLM call failed after {MAX_RETRIES} attempts") from last_exc
