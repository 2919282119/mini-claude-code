from agent.session import AgentState
from llm.call_llm import call_llm
from llm.model import MODELS


class ContextManager:

    def __init__(self, context_window: int):
        self.context_window = context_window
        self.used_tokens = 0

    def update(self, response):
        if response.usage:
            # 注意，state.messages 越长（token越多） → prompt_tokens 越大
            # response.usage.prompt_tokens 已经包含了这次请求中所有输入 token（messages->动态，system_prompt,工具列表等->静态），不只是 state.messages
            self.used_tokens = response.usage.prompt_tokens

    # @property可以让一个方法可以像属性一样被访问，而不需要加 ()
    @property
    def remaining_tokens(self):
        return self.context_window - self.used_tokens

    @property
    def usage_ratio(self):
        return self.used_tokens / self.context_window

    def compact(self,state:AgentState):
        # 保留最近 10 条消息，测试：先改成保留最近3条
        recent_messages = state.messages[-10:]
        old_messages = state.messages[:-10]

        if not old_messages:
            return False

        # 让 LLM 总结旧消息
        summary_messages = [
            {
                "role": "system",
                "content": """
        请总结下面的 Coding Agent 对话历史。

        保留：
        - 用户的目标和要求
        - 已经完成的工作
        - 重要的文件路径和代码修改
        - 遇到的错误及解决方案
        - 当前进度
        - 尚未完成的任务
        - 后续工作需要知道的重要信息

        删除无关的闲聊和重复内容。
        不要编造信息。
        请输出简洁但完整的总结。
        """
            },
            *old_messages
        ]
        model_config=MODELS[state.model]
        response = call_llm(model_config,summary_messages)

        # 更新最近一次 LLM 请求的 token 使用量
        self.update(response)

        summary = response.choices[0].message.content

        # 用 summary + 最近消息替换旧上下文
        state.messages = [
            {
                "role": "user",
                "content": f"[Conversation Summary]\n\n{summary}"
            },
            *recent_messages
        ]

        return True

    def auto_compact(self,state:AgentState):
        usage_ratio = self.usage_ratio
        if usage_ratio >= 0.8:
            self.compact(state)