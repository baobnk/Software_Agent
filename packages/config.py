"""Agent model configuration loader.

Resolution order for model string:
  1. Env var MODEL_<AGENT_UPPER>  (e.g. MODEL_BRD_DRAFTER)
  2. config/agent_models.yaml per-agent "model" key
  3. config/agent_models.yaml onprem.default_model (if onprem.enabled)
  4. Fallback default ("openai:gpt-4.1-mini")

On-premise OpenAI-compatible endpoint support:
  Set onprem.enabled = true in config/agent_models.yaml, then fill
  onprem.base_url, onprem.api_key, onprem.default_model.
  Env vars OPENAI_BASE_URL and OPENAI_API_KEY always take precedence.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Union

import yaml

_DEFAULT_MODEL = "openai:gpt-4.1-mini"
_YAML_PATH = Path(__file__).parent.parent / "config" / "agent_models.yaml"

_ENV_KEY = {
    "orchestrator":              "MODEL_ORCHESTRATOR",
    "intake_agent":              "MODEL_INTAKE",
    "solution_finder_agent":     "MODEL_SOLUTION_FINDER",
    "brd_drafter_agent":         "MODEL_BRD_DRAFTER",
    "wbs_estimator_agent":       "MODEL_WBS_ESTIMATOR",
    "critic_agent":              "MODEL_CRITIC",
    "exporter_agent":            "MODEL_EXPORTER",
    "technical_design_diagram":  "MODEL_TECHNICAL_DESIGN_DIAGRAM",
}


@lru_cache(maxsize=1)
def load_agent_models_yaml() -> dict[str, Any]:
    if not _YAML_PATH.exists():
        return {}
    with _YAML_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def apply_onprem_config() -> None:
    """Apply on-premise endpoint settings from agent_models.yaml to the environment.

    Called once at startup (e.g. from orchestrator.py or main.py).
    When onprem.enabled is true, FORCES base_url and api_key into env vars,
    overriding any previously set OPENAI_BASE_URL / OPENAI_API_KEY (e.g.
    from a .env file pointing to the OpenAI cloud).
    Does nothing if onprem.enabled is false or missing.
    """
    cfg = load_agent_models_yaml()
    onprem = cfg.get("onprem", {})
    if not onprem.get("enabled"):
        return

    if base_url := onprem.get("base_url"):
        os.environ["OPENAI_BASE_URL"] = base_url

    if api_key := onprem.get("api_key"):
        os.environ["OPENAI_API_KEY"] = api_key


def get_agent_model(agent_name: str) -> str:
    """Return the model string for `agent_name`.

    Resolution order:
      1. Per-agent env var (MODEL_BRD_DRAFTER, etc.)  — highest priority
      2. onprem.default_model, if onprem.enabled       — forces all agents to proxy model
      3. Per-agent "model" key in YAML                 — cloud fallback per-agent
      4. Global default
    """
    env_key = _ENV_KEY.get(agent_name)
    if env_key and (val := os.environ.get(env_key)):
        return val

    cfg = load_agent_models_yaml()

    # When on-prem is enabled, use the proxy model for ALL agents
    # (takes precedence over per-agent YAML so you only configure one place)
    onprem = cfg.get("onprem", {})
    if onprem.get("enabled") and (onprem_model := onprem.get("default_model")):
        return onprem_model

    agent_cfg = cfg.get(agent_name, {})
    if model := agent_cfg.get("model"):
        return model

    return _DEFAULT_MODEL


def get_llm(agent_name: str):
    """Return a configured chat model for `agent_name`.

    When onprem.enabled is true, returns a ChatOpenAI instance with
    use_responses_api=False so requests go to /v1/chat/completions (the
    endpoint supported by LiteLLM / Ollama / vLLM proxies) instead of the
    newer /v1/responses endpoint that DeepAgents' OpenAI profile enables by
    default.  Passing a BaseChatModel directly to create_deep_agent / create_agent
    bypasses DeepAgents' provider profile injection entirely.

    When onprem is disabled, returns the plain model string so the caller /
    DeepAgents can resolve it normally (cloud routing, caching middleware, etc.).
    """
    model_str = get_agent_model(agent_name)
    cfg = load_agent_models_yaml()
    onprem = cfg.get("onprem", {})

    if not onprem.get("enabled"):
        return model_str

    from langchain_openai import ChatOpenAI

    # model_str is "openai:<model_name>" — strip the provider prefix
    _, _, model_name = model_str.partition(":")
    if not model_name:
        model_name = model_str

    agent_cfg = cfg.get(agent_name, {})
    temperature = float(agent_cfg.get("temperature", 0.0))

    return ChatOpenAI(
        model=model_name,
        base_url=onprem.get("base_url"),
        api_key=onprem.get("api_key"),
        temperature=temperature,
        use_responses_api=False,
    )
