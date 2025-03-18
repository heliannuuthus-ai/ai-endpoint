from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import json


# 定义事件类型枚举
class DifyEventType(str, Enum):
    MESSAGE = "message"
    AGENT_MESSAGE = "agent_message"
    AGENT_THOUGHT = "agent_thought"
    MESSAGE_FILE = "message_file"
    MESSAGE_END = "message_end"
    TTS_MESSAGE = "tts_message"
    TTS_MESSAGE_END = "tts_message_end"
    MESSAGE_REPLACE = "message_replace"
    ERROR = "error"
    PING = "ping"


# 公共参数基类
class BaseEvent(BaseModel):
    event: DifyEventType
    task_id: Optional[str] = None
    message_id: Optional[str] = None
    conversation_id: Optional[str] = None
    created_at: Optional[int] = None

    class Config:
        use_enum_values = True  # 允许直接使用枚举值作为字符串

    @classmethod
    def form_raw(cls, data: str) -> "BaseEvent":
        """从原始数据解析事件"""
        try:
            if data.startswith("data: "):
                data = data[6:]
            event_dict = json.loads(data)
            event_type = event_dict.get("event")

            # 根据事件类型选择对应的模型
            event_map = {
                DifyEventType.MESSAGE.value: MessageEvent,
                DifyEventType.AGENT_MESSAGE.value: AgentMessageEvent,
                DifyEventType.AGENT_THOUGHT.value: AgentThoughtEvent,
                DifyEventType.MESSAGE_FILE.value: MessageFileEvent,
                DifyEventType.MESSAGE_END.value: MessageEndEvent,
                DifyEventType.TTS_MESSAGE.value: TTSMessageEvent,
                DifyEventType.TTS_MESSAGE_END.value: TTSMessageEndEvent,
                DifyEventType.MESSAGE_REPLACE.value: MessageReplaceEvent,
                DifyEventType.ERROR.value: ErrorEvent,
                DifyEventType.PING.value: PingEvent,
            }

            model_class = event_map.get(event_type)
            if not model_class:
                raise ValueError(f"Unknown event type: {event_type}")

            return model_class(**event_dict)
        except Exception as e:
            raise ValueError(f"Failed to parse event: {e}")


# 具体事件模型
class MessageEvent(BaseEvent):
    answer: str


class AgentMessageEvent(BaseEvent):
    answer: str


class AgentThoughtEvent(BaseEvent):
    id: str
    position: int
    thought: str
    observation: Optional[str] = None
    tool: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    message_files: Optional[List[Dict[str, str]]] = None


class MessageFileEvent(BaseEvent):
    id: str
    type: str
    belongs_to: str
    url: str


class Usage(BaseModel):
    prompt_tokens: int
    prompt_unit_price: str
    prompt_price_unit: str
    prompt_price: str
    completion_tokens: int
    completion_unit_price: str
    completion_price_unit: str
    completion_price: str
    total_tokens: int
    total_price: str
    currency: str
    latency: float


class RetrieverResource(BaseModel):
    position: int
    dataset_id: str
    dataset_name: str
    document_id: str
    document_name: str
    segment_id: str
    score: float
    content: str


class MessageEndEvent(BaseEvent):
    metadata: Dict[str, Any] = Field(default_factory=dict)  # 包含 usage 和 retriever_resources


class TTSMessageEvent(BaseEvent):
    audio: str


class TTSMessageEndEvent(BaseEvent):
    audio: str


class MessageReplaceEvent(BaseEvent):
    answer: str


class ErrorEvent(BaseEvent):
    status: int
    code: str
    message: str


class PingEvent(BaseEvent):
    pass
