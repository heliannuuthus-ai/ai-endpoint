from app.internal.exception import http_exception_handler, exception_handler
from dotenv import load_dotenv
load_dotenv()
import os
from tomllib import load as toml_load
from app.internal.logging import logger

for configfile in os.getenv("CONFIG_REFERENCE").split(","):
    with open(configfile, "rb") as f:
        config = toml_load(f)
    for key, value in config.items():
        for k, v in value.items():
            config_key = f"{key.upper()}_{k.upper()}"
            logger.info(f"set up environment variable {config_key} = {v}")
            os.environ[config_key] = v

import fastapi
from fastapi import HTTPException
from app.routers import wikipedia
from fastapi.middleware.cors import CORSMiddleware
from app.internal import ALLOWED_ORIGINS
os.makedirs('logs', exist_ok=True)

app = fastapi.FastAPI()

app.include_router(wikipedia.router)

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, exception_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],       
)

def start():
    import uvicorn
    logger.info("Starting server...")
    
    uvicorn.run("app.main:app", host="0.0.0.0", port=11160, log_config=None, reload=True)