"""Settings loader.

Reads config/settings.<APP_ENV>.yaml. No secrets live in these files — MT5
credentials and any API keys come from environment variables only (see
.env.example and adapters/mt5/mt5_data_adapter.py).
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


class Settings:
    def __init__(self, raw: dict):
        self.raw = raw
        self.environment: str = raw["environment"]
        self.data_source: dict = raw["data_source"]
        self.data_source_provider: str = raw["data_source"]["provider"]
        self.risk: dict = raw["risk"]
        self.lots: dict = raw["lots"]
        self.confidence: dict = raw["confidence"]
        self.timeframes: dict = raw["timeframes"]
        self.tp_rules: dict = raw["tp_rules"]
        self.sl_rules: dict = raw["sl_rules"]
        self.symbols: list = raw["symbols"]
        self.session: dict = raw["session"]
        self.data: dict = raw["data"]
        self.analysis: dict = raw["analysis"]


@lru_cache
def get_settings() -> Settings:
    env = os.environ.get("APP_ENV", "dev")
    path = CONFIG_DIR / f"settings.{env}.yaml"
    with path.open() as f:
        raw = yaml.safe_load(f)
    return Settings(raw)
