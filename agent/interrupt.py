"""中断：进程级标志 + 「阻塞调用要放到 worker 线程里发」。

Ctrl+C 在 Windows 上有两件事同时成立，缺一不可：

1. **只有带控制台的终端才投递得到信号**。PyCharm 的 Run 窗口给进程的是管道、
   git-bash 的 mintty 窗口没有 Windows 控制台，这两处按 Ctrl+C 不会有任何反应
   ——代码层面修不了。
2. **信号送达了也未必立刻生效**：Python 的待处理 `KeyboardInterrupt` 只有回到
   字节码循环才会抛出，而 Windows 上 Ctrl+C 只中止**控制台句柄**上的阻塞读，
   **socket 读取不在其列**（Unix 的 `recv` 会被 EINTR 打断，Windows 不会）。所以在
   主线程里直接发阻塞请求（LLM 调用、联网搜索、上下文压缩），中断会被一直压到那次
   请求结束——真终端实测：一次长回答请求中按 Ctrl+C，界面上 70~80 秒后才出现
   「已中断」，而那正是请求自己的耗时。

`run_interruptibly` 解决第 2 条。第 1 条无解，只能换终端。

另外，子 Agent 跑在 worker 线程里、**收不到 KeyboardInterrupt**（信号只投递给主
线程），所以除了抛异常之外还要一个进程级标志，让它们能在自己的下一个轮边界停下来。
"""

import threading

_interrupted = False


def request_interrupt():
    global _interrupted
    _interrupted = True


def clear_interrupt():
    """每轮用户提问开始前复位，否则上一轮的中断会立刻掐掉这一轮。"""
    global _interrupted
    _interrupted = False


def is_interrupted():
    return _interrupted


def run_interruptibly(call, *args, **kwargs):
    """在 worker 线程里执行一个阻塞调用，主线程用带超时的 Event.wait 轮询等结果。

    直接在主线程里发阻塞请求（LLM、联网搜索）会让 Ctrl+C 压到请求结束才生效，原因
    见模块开头的第 2 条。这里的关键是主线程**只**做 `Event.wait(timeout=...)`：它走的
    是带超时的锁获取，会在等待中检查待处理信号，所以中断能在 0.2 秒内抛到主线程。

    被打断的请求在后台自然结束、结果丢弃，代价是浪费一次请求。
    """
    outcome = {}
    done = threading.Event()

    def worker():
        try:
            outcome["value"] = call(*args, **kwargs)
        except BaseException as error:  # 调用自身的异常也要带回主线程，保持原有的抛出行为
            outcome["error"] = error
        finally:
            done.set()

    threading.Thread(target=worker, daemon=True).start()

    while not done.wait(0.2):
        pass

    if "error" in outcome:
        raise outcome["error"]

    return outcome["value"]
