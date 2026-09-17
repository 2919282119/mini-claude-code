from dataclasses import dataclass


@dataclass
class ModelConfig:
    name: str
    api_key_env: str
    base_url_env: str
    context_window: int
MODELS = {
    "kimi": ModelConfig(
        name="kimi-k2.6",
        api_key_env="KIMI_API_KEY",
        base_url_env="KIMI_BASE_URL",
        context_window=262144
    ),
    "deepseek": ModelConfig(
        name="deepseek-flash",
        api_key_env="DEEPSEEK_API_KEY",
        base_url_env="DEEPSEEK_BASE_URL",
        context_window=1000000
    ),
}
DEFAULT_MODEL = "deepseek"