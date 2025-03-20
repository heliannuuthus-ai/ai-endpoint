import asyncio
from typing import AsyncGenerator, Annotated, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Path, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.internal.dify import get_chat_client
from app.internal.dify.models.workflow import DifyEventType, BaseEvent
from app.internal import logger
from httpx import Response
from app.internal.dify.models import FileMeta, FileType
import json

router = APIRouter(prefix="/glossary", tags=["glossary"])

_CLIENT_NAME = "glossary"

_USERNAME = "heliannuuthus"


class FeedbackRequest(BaseModel):
    rating: Optional[str] = None
    user: str = "heliannuuthus"
    content: Optional[str] = None


@router.post("/{message_id}/feedback")
async def feedback(message_id: Annotated[str, Path()], request: Annotated[FeedbackRequest, Body()]):
    logger.info(f"feedback request: {request}")

    client = get_chat_client(_CLIENT_NAME)
    response = await client.create_feedbacks(message_id, request.rating, request.user, request.content)
    response.raise_for_status()
    return response.json()


async def upload(files: Annotated[list[UploadFile], Form()], user: Annotated[str, Form()] = None):
    logger.info(f"upload file: {files.filename}, user: {user}")

    if not files:
        raise HTTPException(status_code=400, detail="No file uploaded")

    for item in range(len(files)):
        if files[item].filename is None:
            raise HTTPException(status_code=400, detail="No file uploaded")

    client = get_chat_client(_CLIENT_NAME)

    response = await client.file_upload(_USERNAME, files)

    return FileMeta.from_response(response)


class GlossaryRequest(BaseModel):
    prompt: str
    thinking: bool = False
    deep_search: bool = False
    files_meta: list[FileMeta] = []


@router.post("/chat")
async def glossary(request: GlossaryRequest) -> StreamingResponse:

    logger.info(
        f"glossary request: {len(request.prompt) > 20 and request.prompt[:20] + '...' or request.prompt}, file: {request.files_meta}, thinking: {request.thinking}, deepsearch: {request.deep_search}"
    )

    client = get_chat_client(_CLIENT_NAME)
    files = {}
    for file_meta in request.files_meta:
        file_type = FileType.from_meta(file_meta)
        if not file_type:
            raise HTTPException(status_code=400, detail=f"Invalid file type: {file_meta.name}")
        files[file_type.value[0]] = file_meta.id

    response = await client.create_chat_message(query=request.prompt,
                                                inputs={
                                                    "thinking": "true" if request.thinking else "false",
                                                    "deep_search": "true" if request.deep_search else "false"
                                                },
                                                user=_USERNAME,
                                                files=[{
                                                    "type": file_type.value[0],
                                                    "transfer_method": "local_file",
                                                    "upload_file_id": file_meta.id,
                                                } for file_type, file_meta in files.items()])
    return StreamingResponse(parse_response(response), media_type="text/event-stream")


async def parse_response(response: Response) -> AsyncGenerator[str, None]:
    async for chunk in response.aiter_lines():
        if chunk.startswith("data:"):
            logger.info(f"chunk: {chunk}")
            event = BaseEvent.from_raw(chunk)
            if event.event == DifyEventType.MESSAGE or event.event == DifyEventType.MESSAGE_END:
                logger.info(f"event: {event}")
                yield f"{json.dumps(event.model_dump())}\n\n"
                await asyncio.sleep(0.1)
        else:
            logger.info(f"chunk: {chunk}")
    logger.info(f"close response")
    await response.aclose()
