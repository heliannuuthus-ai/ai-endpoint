from dotenv import load_dotenv

load_dotenv()
import app.internal as internel

import fastapi
from fastapi import HTTPException
from app.routers import glossary
from fastapi.middleware.cors import CORSMiddleware

app = fastapi.FastAPI()

app.include_router(glossary.router)

app.add_exception_handler(HTTPException, internel.http_exception_handler)
app.add_exception_handler(Exception, internel.exception_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=internel.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


def start():
    import uvicorn
    internel.logger.info("Starting ai endpoint...")
    internel.get_config()
    uvicorn.run("app.main:app", host="0.0.0.0", port=11160, log_config=None, reload=True)
