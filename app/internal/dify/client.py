import json
import httpx
from typing import Literal
import threading
from app.internal import logger, get_config

lock = threading.Lock()

_client: httpx.AsyncClient | None = None


def _global_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        with lock:
            if _client is None:
                proxy_url = get_config().proxy.url
                if proxy_url:
                    logger.info(f"using proxy: {proxy_url}")
                    _client = httpx.AsyncClient(timeout=httpx.Timeout(timeout=300),
                                                transport=httpx.AsyncHTTPTransport(retries=3,
                                                                                   proxy=httpx.Proxy(url=proxy_url)))
    return _client


_dify_clients = {}


def get_chat_client(name: str) -> "ChatClient":
    return _get_client(name)


def _get_client(name: str) -> "DifyClient":
    if name not in _dify_clients:
        config = get_config()
        if not hasattr(config, name):
            raise ValueError(f"{name} is not configured")
        _dify_clients[name] = ChatClient(api_key=getattr(config, name)._api_key_plaintext)
    return _dify_clients[name]


class DifyClient:

    def __init__(self, api_key: str, base_url: str = "https://api.dify.ai/v1"):
        self.api_key = api_key
        self.base_url = base_url

    async def _send_request(self,
                            method: str,
                            endpoint: str,
                            data: dict | None = None,
                            params: dict | None = None,
                            stream: bool = False) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}{endpoint}"

        return await _global_client().send(_global_client().build_request(method,
                                                                          url,
                                                                          json=data,
                                                                          headers=headers,
                                                                          params=params),
                                           stream=stream)

    async def _send_request_with_files(self, method: str, endpoint: str, data: dict, files: dict) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.api_key}"}

        url = f"{self.base_url}{endpoint}"
        return await _global_client().request(method, url, data=data, headers=headers, files=files)

    async def file_upload(self, user: str, files: dict) -> httpx.Response:
        data = {"user": user}
        return await self._send_request_with_files("POST", "/files/upload", data=data, files=files)

    async def text_to_audio(self, text: str, user: str, streaming: bool = False):
        data = {"text": text, "user": user, "streaming": streaming}
        return await self._send_request("POST", "/text-to-audio", data=data)

    async def get_meta(self, user):
        params = {"user": user}
        return await self._send_request("GET", "/meta", params=params)

    async def create_feedbacks(self, message_id: str, rating: str, user: str, content: str):
        data = {"rating": rating, "user": user, "content": content}
        return await self._send_request("POST", f"/messages/{message_id}/feedbacks", data=data)


class CompletionClient(DifyClient):

    async def create_completion_message(self,
                                        query: str,
                                        inputs: dict,
                                        user: str,
                                        files=None,
                                        response_mode: str = "streaming") -> httpx.Response:
        data = {
            "query": query,
            "inputs": inputs,
            "response_mode": response_mode,
            "user": user,
        }

        if files:
            data["files"] = files

        return await self._send_request(
            "POST",
            "/completion-messages",
            data=data,
            stream=True if response_mode == "streaming" else False,
        )


class ChatClient(DifyClient):

    async def create_chat_message(
        self,
        inputs: dict,
        query: str,
        user: str,
        response_mode: Literal["blocking", "streaming"] = "streaming",
        conversation_id: str | None = None,
        files: list[dict] | None = None,
    ):
        data = {
            "inputs": inputs,
            "query": query,
            "user": user,
            "response_mode": response_mode,
            "files": files,
        }
        if conversation_id:
            data["conversation_id"] = conversation_id

        return await self._send_request(
            "POST",
            "/chat-messages",
            data,
            stream=True if response_mode == "streaming" else False,
        )

    async def get_suggested(self, message_id, user: str):
        params = {"user": user}
        return await self._send_request("GET", f"/messages/{message_id}/suggested", params=params)

    async def stop_message(self, task_id, user):
        data = {"user": user}
        return await self._send_request("POST", f"/chat-messages/{task_id}/stop", data)

    async def get_conversations(self,
                                user: str,
                                last_id: str | None = None,
                                limit: int | None = None,
                                pinned: bool | None = None) -> httpx.Response:
        params = {"user": user, "last_id": last_id, "limit": limit, "pinned": pinned}
        return await self._send_request("GET", "/conversations", params=params)

    async def get_conversation_messages(self,
                                        user: str,
                                        conversation_id: str | None = None,
                                        first_id: str | None = None,
                                        limit: int | None = None) -> httpx.Response:
        params = {"user": user}

        if conversation_id:
            params["conversation_id"] = conversation_id
        if first_id:
            params["first_id"] = first_id
        if limit:
            params["limit"] = limit

        return await self._send_request("GET", "/messages", params=params)

    async def rename_conversation(self, conversation_id, name, auto_generate: bool, user: str):
        data = {"name": name, "auto_generate": auto_generate, "user": user}
        return await self._send_request("POST", f"/conversations/{conversation_id}/name", data)

    async def delete_conversation(self, conversation_id, user):
        data = {"user": user}
        return await self._send_request("DELETE", f"/conversations/{conversation_id}", data)

    async def audio_to_text(self, audio_file, user):
        data = {"user": user}
        files = {"audio_file": audio_file}
        return await self._send_request_with_files("POST", "/audio-to-text", data, files)


class WorkflowClient(DifyClient):

    async def run(self, inputs: dict, response_mode: str = "streaming", user: str = "abc-123"):
        data = {"inputs": inputs, "response_mode": response_mode, "user": user}
        return await self._send_request("POST", "/workflows/run", data)

    async def stop(self, task_id, user):
        data = {"user": user}
        return await self._send_request("POST", f"/workflows/tasks/{task_id}/stop", data)

    async def get_result(self, workflow_run_id):
        return await self._send_request("GET", f"/workflows/run/{workflow_run_id}")


class KnowledgeBaseClient(DifyClient):

    def __init__(
        self,
        api_key,
        base_url: str = "https://api.dify.ai/v1",
        dataset_id: str | None = None,
    ):
        """
        Construct a KnowledgeBaseClient object.

        Args:
            api_key (str): API key of Dify.
            base_url (str, optional): Base URL of Dify API. Defaults to 'https://api.dify.ai/v1'.
            dataset_id (str, optional): ID of the dataset. Defaults to None. You don't need this if you just want to
                create a new dataset. or list datasets. otherwise you need to set this.
        """
        super().__init__(api_key=api_key, base_url=base_url)
        self.dataset_id = dataset_id

    async def _get_dataset_id(self):
        if self.dataset_id is None:
            raise ValueError("dataset_id is not set")
        return self.dataset_id

    async def create_dataset(self, name: str, **kwargs):
        return await self._send_request("POST", "/datasets", {"name": name}, **kwargs)

    async def list_datasets(self, page: int = 1, page_size: int = 20, **kwargs):
        return await self._send_request("GET", f"/datasets?page={page}&limit={page_size}", **kwargs)

    async def create_document_by_text(self,
                                      name: str,
                                      text: str,
                                      extra_params: dict | None = None,
                                      **kwargs) -> httpx.Response:
        """
        Create a document by text.

        :param name: Name of the document
        :param text: Text content of the document
        :param extra_params: extra parameters pass to the API, such as indexing_technique, process_rule. (optional)
            e.g.
            {
            'indexing_technique': 'high_quality',
            'process_rule': {
                'rules': {
                    'pre_processing_rules': [
                        {'id': 'remove_extra_spaces', 'enabled': True},
                        {'id': 'remove_urls_emails', 'enabled': True}
                    ],
                    'segmentation': {
                        'separator': '\n',
                        'max_tokens': 500
                    }
                },
                'mode': 'custom'
            }
        }
        :return: Response from the API
        """
        data = {
            "indexing_technique": "high_quality",
            "process_rule": {
                "mode": "automatic"
            },
            "name": name,
            "text": text,
        }
        if extra_params is not None and isinstance(extra_params, dict):
            data.update(extra_params)
        url = f"/datasets/{self._get_dataset_id()}/document/create_by_text"
        return await self._send_request("POST", url, json=data, **kwargs)

    async def update_document_by_text(self, document_id, name, text, extra_params: dict | None = None, **kwargs):
        """
        Update a document by text.

        :param document_id: ID of the document
        :param name: Name of the document
        :param text: Text content of the document
        :param extra_params: extra parameters pass to the API, such as indexing_technique, process_rule. (optional)
            e.g.
            {
            'indexing_technique': 'high_quality',
            'process_rule': {
                'rules': {
                    'pre_processing_rules': [
                        {'id': 'remove_extra_spaces', 'enabled': True},
                        {'id': 'remove_urls_emails', 'enabled': True}
                    ],
                    'segmentation': {
                        'separator': '\n',
                        'max_tokens': 500
                    }
                },
                'mode': 'custom'
            }
        }
        :return: Response from the API
        """
        data = {"name": name, "text": text}
        if extra_params is not None and isinstance(extra_params, dict):
            data.update(extra_params)
        url = (f"/datasets/{self._get_dataset_id()}/documents/{document_id}/update_by_text")
        return await self._send_request("POST", url, json=data, **kwargs)

    async def create_document_by_file(self, file_path, original_document_id=None, extra_params: dict | None = None):
        """
        Create a document by file.

        :param file_path: Path to the file
        :param original_document_id: pass this ID if you want to replace the original document (optional)
        :param extra_params: extra parameters pass to the API, such as indexing_technique, process_rule. (optional)
            e.g.
            {
            'indexing_technique': 'high_quality',
            'process_rule': {
                'rules': {
                    'pre_processing_rules': [
                        {'id': 'remove_extra_spaces', 'enabled': True},
                        {'id': 'remove_urls_emails', 'enabled': True}
                    ],
                    'segmentation': {
                        'separator': '\n',
                        'max_tokens': 500
                    }
                },
                'mode': 'custom'
            }
        }
        :return: Response from the API
        """
        files = {"file": open(file_path, "rb")}
        data = {
            "process_rule": {
                "mode": "automatic"
            },
            "indexing_technique": "high_quality",
        }
        if extra_params is not None and isinstance(extra_params, dict):
            data.update(extra_params)
        if original_document_id is not None:
            data["original_document_id"] = original_document_id
        url = f"/datasets/{self._get_dataset_id()}/document/create_by_file"
        return await self._send_request_with_files("POST", url, {"data": json.dumps(data)}, files)

    async def update_document_by_file(self, document_id, file_path, extra_params: dict | None = None):
        """
        Update a document by file.

        :param document_id: ID of the document
        :param file_path: Path to the file
        :param extra_params: extra parameters pass to the API, such as indexing_technique, process_rule. (optional)
            e.g.
            {
            'indexing_technique': 'high_quality',
            'process_rule': {
                'rules': {
                    'pre_processing_rules': [
                        {'id': 'remove_extra_spaces', 'enabled': True},
                        {'id': 'remove_urls_emails', 'enabled': True}
                    ],
                    'segmentation': {
                        'separator': '\n',
                        'max_tokens': 500
                    }
                },
                'mode': 'custom'
            }
        }
        :return:
        """
        files = {"file": open(file_path, "rb")}
        data = {}
        if extra_params is not None and isinstance(extra_params, dict):
            data.update(extra_params)
        url = (f"/datasets/{self._get_dataset_id()}/documents/{document_id}/update_by_file")
        return await self._send_request_with_files("POST", url, {"data": json.dumps(data)}, files)

    async def batch_indexing_status(self, batch_id: str, **kwargs):
        """
        Get the status of the batch indexing.

        :param batch_id: ID of the batch uploading
        :return: Response from the API
        """
        url = f"/datasets/{self._get_dataset_id()}/documents/{batch_id}/indexing-status"
        return await self._send_request("GET", url, **kwargs)

    async def delete_dataset(self):
        """
        Delete this dataset.

        :return: Response from the API
        """
        url = f"/datasets/{self._get_dataset_id()}"
        return await self._send_request("DELETE", url)

    async def delete_document(self, document_id):
        """
        Delete a document.

        :param document_id: ID of the document
        :return: Response from the API
        """
        url = f"/datasets/{self._get_dataset_id()}/documents/{document_id}"
        return await self._send_request("DELETE", url)

    async def list_documents(
        self,
        page: int | None = None,
        page_size: int | None = None,
        keyword: str | None = None,
        **kwargs,
    ) -> httpx.Response:
        """
        Get a list of documents in this dataset.

        :return: Response from the API
        """
        params = {}
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["limit"] = page_size
        if keyword is not None:
            params["keyword"] = keyword
        url = f"/datasets/{self._get_dataset_id()}/documents"
        return await self._send_request("GET", url, params=params, **kwargs)

    async def add_segments(self, document_id: str, segments: list[dict], **kwargs) -> httpx.Response:
        """
        Add segments to a document.

        :param document_id: ID of the document
        :param segments: List of segments to add, example: [{"content": "1", "answer": "1", "keyword": ["a"]}]
        :return: Response from the API
        """
        data = {"segments": segments}
        url = f"/datasets/{self._get_dataset_id()}/documents/{document_id}/segments"
        return await self._send_request("POST", url, json=data, **kwargs)

    async def query_segments(
        self,
        document_id,
        keyword: str | None = None,
        status: str | None = None,
        **kwargs,
    ):
        """
        Query segments in this document.

        :param document_id: ID of the document
        :param keyword: query keyword, optional
        :param status: status of the segment, optional, e.g. completed
        """
        url = f"/datasets/{self._get_dataset_id()}/documents/{document_id}/segments"
        params = {}
        if keyword is not None:
            params["keyword"] = keyword
        if status is not None:
            params["status"] = status
        if "params" in kwargs:
            params.update(kwargs["params"])
        return await self._send_request("GET", url, params=params, **kwargs)

    async def delete_document_segment(self, document_id, segment_id):
        """
        Delete a segment from a document.

        :param document_id: ID of the document
        :param segment_id: ID of the segment
        :return: Response from the API
        """
        url = f"/datasets/{self._get_dataset_id()}/documents/{document_id}/segments/{segment_id}"
        return await self._send_request("DELETE", url)

    async def update_document_segment(self, document_id, segment_id, segment_data, **kwargs):
        """
        Update a segment in a document.

        :param document_id: ID of the document
        :param segment_id: ID of the segment
        :param segment_data: Data of the segment, example: {"content": "1", "answer": "1", "keyword": ["a"], "enabled": True}
        :return: Response from the API
        """
        data = {"segment": segment_data}
        url = f"/datasets/{self._get_dataset_id()}/documents/{document_id}/segments/{segment_id}"
        return await self._send_request("POST", url, json=data, **kwargs)
