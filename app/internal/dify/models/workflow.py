from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
import json


# 定义事件类型枚举
class DifyEventType(str, Enum):
    WORKFLOW_STARTED = "workflow_started"
    NODE_STARTED = "node_started"
    NODE_FINISHED = "node_finished"
    WORKFLOW_FINISHED = "workflow_finished"
    TTS_MESSAGE = "tts_message"
    TTS_MESSAGE_END = "tts_message_end"
    PING = "ping"
    MESSAGE = "message"
    MESSAGE_FILE = "message_file"
    MESSAGE_END = "message_end"


# 公共参数基类
class BaseEvent(BaseModel):
    event: DifyEventType
    task_id: Optional[str] = None
    workflow_run_id: Optional[str] = None
    message_id: Optional[str] = None
    conversation_id: Optional[str] = None
    created_at: Optional[int] = None

    class Config:
        use_enum_values = True  # 允许直接使用枚举值作为字符串

    @classmethod
    def from_raw(cls, data: str) -> "BaseEvent":
        """从原始数据解析事件"""
        try:
            # 假设数据以 "data: " 开头，去掉前缀并解析 JSON
            if data.startswith("data: "):
                data = data[6:]
            event_dict = json.loads(data)
            event_type = event_dict.get("event")

            # 根据事件类型选择对应的模型
            event_map = {
                DifyEventType.WORKFLOW_STARTED.value: WorkflowStartedEvent,
                DifyEventType.NODE_STARTED.value: NodeStartedEvent,
                DifyEventType.NODE_FINISHED.value: NodeFinishedEvent,
                DifyEventType.WORKFLOW_FINISHED.value: WorkflowFinishedEvent,
                DifyEventType.TTS_MESSAGE.value: TTSMessageEvent,
                DifyEventType.TTS_MESSAGE_END.value: TTSMessageEndEvent,
                DifyEventType.PING.value: PingEvent,
                DifyEventType.MESSAGE.value: MessageEvent,
                DifyEventType.MESSAGE_FILE.value: MessageFileEvent,
                DifyEventType.MESSAGE_END.value: MessageEndEvent,
            }

            model_class = event_map.get(event_type)
            if not model_class:
                raise ValueError(f"Unknown event type: {event_type}")

            return model_class(**event_dict)
        except Exception as e:
            raise ValueError(f"Failed to parse event: {e}")


# Workflow 开始事件
class WorkflowStartedData(BaseModel):
    id: str
    workflow_id: str
    sequence_number: int
    created_at: int


class WorkflowStartedEvent(BaseEvent):
    data: WorkflowStartedData


# Node 开始事件
class NodeStartedData(BaseModel):
    id: str
    node_id: str
    node_type: str
    title: str
    index: int
    predecessor_node_id: Optional[str] = None
    inputs: Optional[Dict[str, Any]] = None
    created_at: int


class NodeStartedEvent(BaseEvent):
    data: NodeStartedData


# Node 结束事件
class ExecutionMetadata(BaseModel):
    total_tokens: Optional[int] = None
    total_price: Optional[float] = None
    currency: Optional[str] = None


class NodeFinishedData(BaseModel):
    id: str
    node_id: str
    index: int
    predecessor_node_id: Optional[str] = None
    inputs: Optional[Dict[str, Any]] = None
    process_data: Optional[Dict[str, Any]] = None
    outputs: Optional[Dict[str, Any]] = None
    status: str  # running / succeeded / failed / stopped
    error: Optional[str] = None
    elapsed_time: Optional[float] = None
    execution_metadata: Optional[ExecutionMetadata] = None
    created_at: int


class NodeFinishedEvent(BaseEvent):
    data: NodeFinishedData


# Workflow 结束事件
class WorkflowFinishedData(BaseModel):
    id: str
    workflow_id: str
    status: str  # running / succeeded / failed / stopped
    outputs: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    elapsed_time: Optional[float] = None
    total_tokens: Optional[int] = None
    total_steps: int = 0
    created_at: int
    finished_at: int


class WorkflowFinishedEvent(BaseEvent):
    data: WorkflowFinishedData


# TTS 消息事件
class TTSMessageEvent(BaseEvent):
    message_id: str
    audio: str


# TTS 消息结束事件
class TTSMessageEndEvent(BaseEvent):
    message_id: str
    audio: str


# Ping 事件
class PingEvent(BaseEvent):
    pass


# Message 事件
class MessageEvent(BaseEvent):
    answer: str


# Message File 事件
class MessageFileEvent(BaseEvent):
    id: str
    type: str
    belongs_to: str
    url: str


# Message End 事件
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
