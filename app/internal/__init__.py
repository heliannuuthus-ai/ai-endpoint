import logging
import os
from app.internal.exception import exception_handler, http_exception_handler

ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000")

logger = logging.getLogger(__name__)

for logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"]:
    logging.getLogger(logger_name).handlers = logger.handlers
