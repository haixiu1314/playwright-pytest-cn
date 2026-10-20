"""逆序清理，每个回调失败后仍继续执行剩余回调。"""


class CleanupRegistry:
    def __init__(self):
        self.callbacks = []

    def register(self, callback, *args, **kwargs):
        self.callbacks.append((callback, args, kwargs))

    def close(self):
        errors = []
        while self.callbacks:
            callback, args, kwargs = self.callbacks.pop()
            try:
                callback(*args, **kwargs)
            except Exception as exc:
                errors.append(f"{getattr(callback, '__name__', '清理回调')}：{exc}")
        if errors:
            raise RuntimeError("资源清理失败：" + "；".join(errors))
