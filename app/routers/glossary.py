import asyncio
from typing import AsyncGenerator, Annotated
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
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


@router.get("/upload")
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
    filesMeta: list[FileMeta] = []


@router.post("/chat")
async def glossary(request: GlossaryRequest) -> StreamingResponse:

    logger.info(
        f"wikipedia request: {len(request.prompt) > 20 and request.prompt[:20] + '...' or request.prompt}, file: {request.filesMeta}"
    )

    client = get_chat_client(_CLIENT_NAME)
    files = {}
    for fileMeta in request.filesMeta:
        fileType = FileType.from_meta(fileMeta)
        if not fileType:
            raise HTTPException(status_code=400, detail=f"Invalid file type: {fileMeta.name}")
        files[fileType.value[0]] = fileMeta.id

    response = await client.create_chat_message(query=request.prompt,
                                                inputs={"thinking": "true" if request.thinking else "false"},
                                                user=_USERNAME,
                                                files=[{
                                                    "type": fileType.value[0],
                                                    "transfer_method": "local_file",
                                                    "upload_file_id": fileMeta.id,
                                                } for fileType, fileMeta in files.items()])
    return StreamingResponse(parse_response(response), media_type="text/event-stream")


async def parse_response(response: Response) -> AsyncGenerator[str, None]:
    async for chunk in response.aiter_lines():
        if chunk.startswith("data:"):
            event = BaseEvent.from_raw(chunk)
            if event.event == DifyEventType.MESSAGE or event.event == DifyEventType.MESSAGE_END:
                yield f"{json.dumps(event.model_dump())}\n\n"
                await asyncio.sleep(0.1)
    logger.info(f"close response")
    await response.aclose()
