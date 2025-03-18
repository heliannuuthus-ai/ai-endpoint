from pydantic import BaseModel
from enum import Enum
from httpx import Response


class FileMeta(BaseModel):
    id: str
    name: str
    size: int
    extension: str
    mime_type: str
    created_by: str
    created_at: str

    @classmethod
    def from_response(cls, response: Response):
        return cls(**response.json())


class FileTransferMethod(Enum):
    LOCAL_FILE = "local_file"
    URL = "remote_url"


class FileType(Enum):
    DOCUMENT = ("document", [
        'TXT', 'MD', 'MARKDOWN', 'PDF', 'HTML', 'XLSX', 'XLS', 'DOCX', 'CSV', 'EML', 'MSG', 'PPTX', 'PPT', 'XML', 'EPUB'
    ])
    IMAGE = ("image", ['JPG', 'JPEG', 'PNG', 'GIF', 'WEBP', 'SVG'])
    AUDIO = ("audio", ['MP3', 'M4A', 'WAV', 'WEBM', 'AMR'])
    VIDEO = ("video", ['MP4', 'MOV', 'MPEG', 'MPGA'])

    @staticmethod
    def from_meta(meta: FileMeta):
        for file_type in FileType:
            if meta.extension in file_type.value[1]:
                return file_type(meta)
        return None
