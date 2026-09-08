import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
# TODO:我觉得这里写的太死了切换模型太麻烦了，而且也没有各个模型的配置比如上下文窗口
client = OpenAI(
    api_key=os.environ["TP_API_KEY"],
    base_url=os.environ["TP_BASE_URL"],
)
def call_llm(messages, tools=None):
    kwargs = {
        "model": os.environ["TP_MODEL"],
        "messages": messages,
        "temperature": 1,
    }

    if tools:
        kwargs["tools"] = tools
    return client.chat.completions.create(**kwargs)