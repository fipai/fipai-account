"""
统一错误响应格式
"""
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


class APIException(Exception):
    """统一 API 异常"""
    def __init__(self, message, code=None, details=None, status_code=None):
        self.message = message
        self.code = code or 'ERROR'
        self.details = details or {}
        self.status_code = status_code or status.HTTP_400_BAD_REQUEST
        super().__init__(message)


def custom_exception_handler(exc, context):
    """
    统一错误响应格式:
    {
        "error": "错误描述",
        "code": "ERROR_CODE",
        "details": {}
    }
    """
    # 处理自定义 APIException
    if isinstance(exc, APIException):
        return Response({
            'error': exc.message,
            'code': exc.code,
            'details': exc.details,
        }, status=exc.status_code)

    # 调用 DRF 默认异常处理器
    response = exception_handler(exc, context)

    if response is not None:
        # 将 DRF 的错误格式转换为统一格式
        if isinstance(response.data, dict):
            # 提取错误信息
            error_message = response.data.get('detail', str(response.data))
            if isinstance(error_message, list):
                error_message = '; '.join(str(e) for e in error_message)
            elif isinstance(error_message, dict):
                # 处理验证错误
                errors = []
                for field, msgs in error_message.items():
                    if isinstance(msgs, list):
                        errors.append(f"{field}: {', '.join(str(m) for m in msgs)}")
                    else:
                        errors.append(f"{field}: {msgs}")
                error_message = '; '.join(errors)

            response.data = {
                'error': error_message,
                'code': 'VALIDATION_ERROR' if response.status_code == 400 else 'ERROR',
                'details': {},
            }
        elif isinstance(response.data, list):
            response.data = {
                'error': '; '.join(str(e) for e in response.data),
                'code': 'ERROR',
                'details': {},
            }

    return response
