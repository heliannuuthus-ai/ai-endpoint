import asyncio
from typing import AsyncGenerator, Any, Coroutine, Annotated
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.prompts import get_prompt
from openai import AsyncOpenAI
from openai.resources.chat.completions.completions import AsyncStream, ChatCompletionChunk
from app.routers import API_KEY, API_ENDPOINT, MODEL
from app.internal import logger
import os
import base64
from urllib.parse import urljoin

router = APIRouter(prefix="/wikipedia", tags=["wikipedia"])

client = AsyncOpenAI(api_key=API_KEY, base_url=urljoin(API_ENDPOINT, "ai/v1"), max_retries=3, timeout=300)


@router.get("/models")
async def models():
    return  {
        "reasoner": os.getenv("WIKIPEDIA_REASONER_MODEL"),
        "image_to_text": os.getenv("WIKIPEDIA_IMAGE_TO_TEXT_MODEL"),
        "chat": os.getenv("WIKIPEDIA_CHAT_MODEL")
    }

class WikipediaGlossaryRequest(BaseModel):
    model: str
    prompt: str

    def __str__(self) -> str:
        return f"prompt: {self.prompt[:20]}..."
    


@router.post("/glossary")
async def wikipedia(
    model: Annotated[str, Form(...)],
    prompt: Annotated[str, Form(...)],
    image: UploadFile = File(None)
) -> StreamingResponse:
    
    logger.info(f"wikipedia request: {model}, {prompt[:20]}..., image: {image.filename if image else None}")

    prompt = get_prompt("wikipedia", "glossary")
    if not prompt:
        raise HTTPException(status_code=404, detail="prompt not found")

    user_content = prompt
    if image:
        image_content = await _process_image(image)
        user_content = f"{user_content}\n图片内容：{image_content}" if user_content else f"图片内容：{image_content}"

    response = await client.chat.completions.create(
        model=model,
        messages=[{
            "role": "system",
            "content": prompt
        }, {
            "role": "user",
            "content": user_content
        }],
        temperature=0.7,
        max_tokens=2048,
        stream=True,
    )

    return StreamingResponse(parse_response(response), media_type="text/event-stream")


async def parse_response(response: AsyncStream[ChatCompletionChunk]) -> AsyncGenerator[str, None]:
    thinking = True
    async for chunk in response:
        if chunk.choices:
            if "reasoning_content" in chunk.choices[0].delta:
                content = chunk.choices[0].delta.reasoning_content
            else:
                content = chunk.choices[0].delta.content
            yield f"{content}"
            await asyncio.sleep(0.01)


async def _process_image(image: UploadFile) -> str:
    """处理图片并返回描述文本"""
    image_bytes = await image.read()
    vision_response = await client.chat.completions.create(
        model=os.getenv("WIKIPEDIA_IMAGE_TO_TEXT_MODEL"),
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "请描述这张图片的内容"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64.b64encode(image_bytes).decode()}"
                    }
                }
            ]
        }],
        max_tokens=500
    )
    return vision_response.choices[0].message.content
