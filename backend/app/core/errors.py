"""业务异常层次 — 业务层统一抛出自定义异常，由 main.py 全局处理器转换为 HTTP 响应。

约定:
    - 服务层（services/）禁止抛 HTTPException，改抛 AppError 子类，
      使非 web 调用方（调度器、forward 等）也能得到业务语义的异常。
    - routers 层的依赖注入（如 require_nf_service）仍可直接用 HTTPException。
"""


class AppError(Exception):
    """项目业务异常基类。

    Attributes:
        message: 中文错误消息，由全局处理器直接返回给调用方
        status_code: 异常对应的 HTTP 状态码
    """

    status_code: int = 500

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class UpstreamError(AppError):
    """外部平台调用失败（对应 HTTP 502）。"""

    status_code = 502


class ServiceNotConfiguredError(AppError):
    """所需平台未配置或未启用（对应 HTTP 503）。"""

    status_code = 503
