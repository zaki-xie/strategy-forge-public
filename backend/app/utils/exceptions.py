# app/utils/exceptions.py
class BusinessError(Exception):
    """业务逻辑异常，携带前端可展示的消息"""
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)