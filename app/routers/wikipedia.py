import asyncio
from typing import AsyncGenerator, Any, Coroutine, Annotated
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.internal import get_config
from app.prompts import get_prompt
from openai import AsyncOpenAI
from openai.resources.chat.completions.completions import AsyncStream, ChatCompletionChunk
from app.internal import logger
import base64
from threading import Lock

router = APIRouter(prefix="/wikipedia", tags=["wikipedia"])

lock = Lock()

clients = {}


def get_client(model: str):
    global clients
    if model not in clients:
        lock.acquire()
        if model not in clients:
            config = get_config()
            clients[model] = AsyncOpenAI(api_key=config.wikipedia.models[model]._api_key_plaintext,
                                         base_url=config.wikipedia.models[model].api_endpoint,
                                         max_retries=3,
                                         timeout=300)
        lock.release()
    return clients[model]


@router.get("/models")
async def models():
    config = get_config()

    return {
        k: {
            **({} if not v.chat_model else {
                   "chat_model": v.chat_model
               }),
            **({} if not v.image_to_text_model else {
                   "image_to_text_model": v.image_to_text_model
               }),
            **({} if not v.reasoner_model else {
                   "reasoner_model": v.reasoner_model
               })
        }
        for k, v in config.wikipedia.models.items()
    }


@router.post("/glossary")
async def wikipedia(name: Annotated[str, Form(...)],
                    model: Annotated[str, Form(...)],
                    prompt: Annotated[str, Form(...)],
                    image: UploadFile = File(None)) -> StreamingResponse:

    logger.info(f"wikipedia request: {model}, {name}, {prompt[:20]}..., image: {image.filename if image else None}")

    system_prompt = get_prompt("wikipedia", "glossary")
    if not system_prompt:
        raise HTTPException(status_code=404, detail="prompt not found")

    user_content = prompt
    if image:
        image_content = await _process_image(image)
        user_content = f"{user_content}\n图片内容：{image_content}" if user_content else f"图片内容：{image_content}"

    response = await get_client(name).chat.completions.create(
        model=model,
        messages=[{
            "role": "system",
            "content": system_prompt
        }, {
            "role": "user",
            "content": user_content
        }],
        temperature=0.7,
        max_tokens=4096,
        stream=True,
    )

    return StreamingResponse(parse_response(response), media_type="text/event-stream")


async def parse_response(response: AsyncStream[ChatCompletionChunk]) -> AsyncGenerator[str, None]:
    is_answer = True
    async for chunk in response:
        content = ""
        if chunk.choices:
            delta = chunk.choices[0].delta
            if hasattr(delta, "reasoning_content") and delta.reasoning_content is not None:
                is_answer = False
                content = delta.reasoning_content
            else:
                if delta.content is not None and len(delta.content) > 0 and not is_answer:
                    yield f"</think>"
                    is_answer = True
                content = delta.content
            yield f"{content}"
            await asyncio.sleep(0.01)


async def _process_image(image: UploadFile, model: str) -> str:
    """处理图片并返回描述文本"""
    image_bytes = await image.read()
    config = get_config()
    vision_response = await get_client(model).chat.completions.create(
        model=config.wikipedia.models[model].image_to_text_model,
        messages=[{
            "role":
            "user",
            "content": [{
                "type": "text",
                "text": "请描述这张图片的内容"
            }, {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64.b64encode(image_bytes).decode()}"
                }
            }]
        }],
        max_tokens=500)
    return vision_response.choices[0].message.content
