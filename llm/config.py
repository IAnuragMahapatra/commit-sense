import os
import re
import yaml
from dotenv import load_dotenv

load_dotenv()  # loads .env if present, no-op if missing

_config = None


def _resolve_env(value: str) -> str:
    """Replace ${VAR} references. Throws if the variable is not set."""
    def replacer(match):
        name = match.group(1)
        resolved = os.environ.get(name)
        if not resolved:
            raise EnvironmentError(f"Missing environment variable: {name}")
        return resolved

    return re.sub(r"\$\{([^}]+)\}", replacer, value)


def _resolve_env_optional(value: str) -> str:
    """Replace ${VAR} references. Returns empty string if the variable is not set."""
    return re.sub(
        r"\$\{([^}]+)\}",
        lambda m: os.environ.get(m.group(1), ""),
        value,
    )


def load_config(path: str = "commitsense.yml") -> dict:
    """Load and validate commitsense.yml. Cached after first call."""
    global _config
    if _config is not None:
        return _config

    try:
        with open(path, "r") as f:
            raw = yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found: {path}")

    llm = raw.get("llm")
    if not llm:
        raise ValueError("commitsense.yml: missing 'llm' section")

    for field in ("base_url", "model", "provider_type"):
        if not llm.get(field):
            raise ValueError(f"commitsense.yml: missing llm.{field}")

    provider_type = llm["provider_type"]
    if provider_type not in ("openai", "anthropic"):
        raise ValueError(
            f"commitsense.yml: llm.provider_type must be 'openai' or 'anthropic', got '{provider_type}'"
        )

    api_key = llm.get("api_key", "")
    if api_key:
        api_key = _resolve_env(api_key)

    dashboard = raw.get("dashboard", {})
    dashboard_token = dashboard.get("token", "")
    if dashboard_token:
        dashboard_token = _resolve_env_optional(dashboard_token)

    _config = {
        "llm": {
            "base_url": llm["base_url"].rstrip("/"),
            "model": llm["model"],
            "provider_type": provider_type,
            "api_key": api_key,
        },
        "rules": raw.get("rules", {}),
        "rewrite": raw.get("rewrite", {}),
        "dashboard": {
            "url": dashboard.get("url", ""),
            "token": dashboard_token,
        },
    }

    return _config


def reset_config():
    """Reset cached config (useful for testing)."""
    global _config
    _config = None
