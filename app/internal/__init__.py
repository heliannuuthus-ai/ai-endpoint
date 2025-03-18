import os

from app.internal.exception import exception_handler, http_exception_handler
from app.internal.config import get_config
from app.internal.logging import logger
from app.internal.dify import DifyClient, CompletionClient, ChatClient

ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000")

__all__ = ["get_config", "logger", "ALLOWED_ORIGINS", "exception_handler", "http_exception_handler"]
