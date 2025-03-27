import asyncio
from typing import AsyncGenerator, Annotated, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Path, Body, Query
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from enum import Enum
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


@router.get("/file-types")
async def file_types():
    return JSONResponse(
        content={
            file_type.value[0]: [suffix.lower() for suffix in file_type.value[1]]
            for file_type in FileType._member_map_.values()
        })


@router.get("/conversations")
async def conversations(limit: Annotated[int, Query()] = 20):
    client = get_chat_client(_CLIENT_NAME)
    response = await client.get_conversations(_USERNAME, limit=limit)
    return response.json()


@router.get("/conversations/{conversation_id}/messages")
async def conversation_messages(conversation_id: Annotated[str, Path()],
                                limit: Annotated[int, Query()] = 20,
                                first_id: Annotated[str, Query()] = None):
    client = get_chat_client(_CLIENT_NAME)
    response = await client.get_conversation_messages(_USERNAME, conversation_id, limit=limit, first_id=first_id)
    response.raise_for_status()
    return response.json()


@router.post("/feedback")
async def feedback(message_id: Annotated[str, Path()], request: Annotated[FeedbackRequest, Body()]):
    logger.info(f"feedback request: {request}")

    client = get_chat_client(_CLIENT_NAME)
    response = await client.create_feedbacks(message_id, request.rating, request.user, request.content)
    response.raise_for_status()
    return response.json()


@router.get("/suggested/{message_id}/")
async def suggested(message_id: Annotated[str, Path()]):
    client = get_chat_client(_CLIENT_NAME)
    response = await client.get_suggested(message_id, _USERNAME)
    response.raise_for_status()
    return response.json()


@router.post("/upload")
async def upload(file: Annotated[UploadFile, Form()], user: Annotated[str, Form()] = None):

    logger.info(f"upload file: {file.filename}, user: {user}")

    if file.filename is None:
        raise HTTPException(status_code=400, detail="No file uploaded")

    client = get_chat_client(_CLIENT_NAME)

    response = await client.file_upload(_USERNAME,
                                        files={"file": (file.filename, await file.read(), file.content_type)})
    if response.status_code // 100 != 2:
        logger.error(f"Failed to upload file, code: {response.status_code}, message: {response.text}")
        raise HTTPException(status_code=400, detail="Failed to upload file")
    return FileMeta.from_response(**response.json())


@router.post("/audio-to-text")
async def audio_to_text(file: Annotated[UploadFile, Form()]):
    client = get_chat_client(_CLIENT_NAME)
    response = await client.audio_to_text(_USERNAME,
                                          files={"file": (file.filename, await file.read(), file.content_type)})
    response.raise_for_status()
    return response.json()


class TextToAudioRequest(BaseModel):
    text: Optional[str] = None
    id: Optional[str] = None


@router.post("/text-to-audio")
async def text_to_audio(request: Annotated[TextToAudioRequest, Body()]):
    client = get_chat_client(_CLIENT_NAME)
    response = await client.text_to_audio(
        request.text,
        request.id,
        _USERNAME,
    )
    response.raise_for_status()
    logger.info(f"text to audio response: {response.json()}")
    return response.json()


@router.post("chat/{task_id}/stop")
async def stop_conversation(task_id: Annotated[str, Path()]):
    client = get_chat_client(_CLIENT_NAME)
    response = await client.stop_message(task_id, _USERNAME)
    response.raise_for_status()
    return response.json()


class Mode(Enum):
    THINK = "think"
    DEEPSEARCH = "deepsearch"


class GlossaryRequest(BaseModel):
    query: str
    mode: Optional[Mode] = None
    conversation_id: Optional[str] = None
    files_meta: list[FileMeta] = []


@router.post("/chat")
async def glossary(request: GlossaryRequest) -> StreamingResponse:

    logger.info(
        f"glossary request: {len(request.query) > 20 and request.query[:20] + '...' or request.query}, file: {request.files_meta}, mode: {request.mode}"
    )

    client = get_chat_client(_CLIENT_NAME)
    files: dict[FileType, FileMeta] = {}
    for file_meta in request.files_meta:
        file_type = FileType.from_meta(file_meta)
        if not file_type:
            raise HTTPException(status_code=400, detail=f"Invalid file type: {file_meta.name}")
        files[file_type] = file_meta

    response = await client.create_chat_message(query=request.query,
                                                inputs={
                                                    "mode": request.mode.value if request.mode else None,
                                                },
                                                conversation_id=request.conversation_id,
                                                user=_USERNAME,
                                                files=[{
                                                    "type": file_type.value[0].lower(),
                                                    "transfer_method": "local_file",
                                                    "upload_file_id": file_meta.id,
                                                } for file_type, file_meta in files.items()])
    return StreamingResponse(parse_response(response), media_type="text/event-stream")


async def parse_response(response: Response) -> AsyncGenerator[str, None]:
    async for chunk in response.aiter_lines():
        logger.info(f"chunk: {chunk}")
        if chunk.startswith("data:"):
            yield f"{chunk}\n\n"
            await asyncio.sleep(0.1)
        else:
            logger.error(f"unknown chunk: {chunk}")
    logger.info(f"close response")
    await response.aclose()
