import os
from openai import OpenAI
from dotenv import load_dotenv

from llm.model import MODELS, ModelConfig

load_dotenv()

def call_llm(
        config:ModelConfig,
        messages,
        tools=None
):
    client = OpenAI(
        api_key=os.environ[config.api_key_env],
        base_url=os.environ[config.base_url_env],
    )
    kwargs = {
        "model": config.name,
        "messages": messages,
        "temperature": 1,
    }

    if tools:
        kwargs["tools"] = tools
    return client.chat.completions.create(**kwargs)