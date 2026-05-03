#!/usr/bin/env python3
"""Standalone test script for on-premise OpenAI-compatible proxy.

Tests the proxy directly with the openai SDK (no LangChain overhead) and
then via the langchain_openai ChatOpenAI with use_responses_api=False.

Usage:
    python scripts/test_onprem_proxy.py

Reads config from config/agent_models.yaml. Override with env vars:
    OPENAI_BASE_URL=https://... OPENAI_API_KEY=sk-... python scripts/test_onprem_proxy.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml

_YAML_PATH = ROOT / "config" / "agent_models.yaml"


def _load_cfg() -> dict:
    if not _YAML_PATH.exists():
        return {}
    with _YAML_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _resolve(cfg: dict) -> tuple[str, str, str]:
    """Return (base_url, api_key, model_name)."""
    onprem = cfg.get("onprem", {})
    base_url  = os.environ.get("OPENAI_BASE_URL") or onprem.get("base_url", "")
    api_key   = os.environ.get("OPENAI_API_KEY")  or onprem.get("api_key", "sk-1234")
    model_str = onprem.get("default_model", "openai:openai36")
    _, _, model_name = model_str.partition(":")
    model_name = model_name or model_str
    return base_url, api_key, model_name


# ── Test 1: raw openai SDK ────────────────────────────────────────────────────

def test_raw_openai(base_url: str, api_key: str, model: str) -> bool:
    print(f"\n[1] Raw openai SDK  →  {base_url}  model={model}")
    try:
        import openai
        client = openai.OpenAI(base_url=base_url, api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Say 'proxy OK' and nothing else."}],
            max_tokens=20,
        )
        reply = resp.choices[0].message.content or ""
        print(f"    ✓  Response: {reply.strip()!r}")
        return True
    except Exception as e:
        print(f"    ✗  {type(e).__name__}: {e}")
        return False


# ── Test 2: langchain ChatOpenAI with use_responses_api=False ─────────────────

def test_langchain_chat(base_url: str, api_key: str, model: str) -> bool:
    print(f"\n[2] ChatOpenAI(use_responses_api=False)  →  model={model}")
    try:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=0.0,
            use_responses_api=False,
        )
        msg = llm.invoke("Say 'langchain OK' and nothing else.")
        print(f"    ✓  Response: {str(msg.content).strip()!r}")
        return True
    except Exception as e:
        print(f"    ✗  {type(e).__name__}: {e}")
        return False


# ── Test 3: packages.config.get_llm (production path) ────────────────────────

def test_get_llm(model: str) -> bool:
    print(f"\n[3] packages.config.get_llm('orchestrator')  →  model={model}")
    try:
        from packages.config import apply_onprem_config, get_llm
        apply_onprem_config()
        llm = get_llm("orchestrator")
        if isinstance(llm, str):
            print(f"    ⚠  get_llm returned string (onprem disabled?): {llm!r}")
            return False
        msg = llm.invoke("Say 'get_llm OK' and nothing else.")
        print(f"    ✓  Response: {str(msg.content).strip()!r}")
        return True
    except Exception as e:
        print(f"    ✗  {type(e).__name__}: {e}")
        return False


def main() -> int:
    cfg = _load_cfg()
    onprem = cfg.get("onprem", {})
    if not onprem.get("enabled"):
        print("WARNING: onprem.enabled is false in agent_models.yaml — tests will still run using env vars.")

    base_url, api_key, model = _resolve(cfg)
    print(f"Config:  base_url={base_url!r}  model={model!r}  api_key={'***' if api_key else '(none)'}")

    results = [
        test_raw_openai(base_url, api_key, model),
        test_langchain_chat(base_url, api_key, model),
        test_get_llm(model),
    ]

    passed = sum(results)
    print(f"\n{'='*50}")
    print(f"Results: {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
