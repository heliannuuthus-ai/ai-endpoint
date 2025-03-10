import threading
from pydantic import BaseModel
from toml import dump, TomlPreserveInlineDictEncoder
from tomllib import load
import os
from dotenv import set_key
from app.internal.logging import logger
from cryptography.hazmat.primitives.ciphers.aead import AESGCMSIV
import base64
from typing import Optional


class ModelConfig(BaseModel):
    _api_key_plaintext: Optional[str] = None
    api_key: str
    api_endpoint: str
    chat_model: str
    image_to_text_model: str
    reasoner_model: str


class WikipediaConfig(BaseModel):
    models: dict[str, ModelConfig]


class ConfigInner(BaseModel):
    wikipedia: WikipediaConfig


class Config:
    API_KEY_DEK: bytes
    API_KEY_NONCE: bytes
    existed_dek: bool = True
    config: ConfigInner
    path: str

    def __init__(self, path: str):
        self.path = path
        with open(path, 'rb') as f:
            data = load(f)
            self.config = ConfigInner(**data)

        API_KEY_DEK = os.getenv("API_KEY_DEK", None)
        API_KEY_NONCE = os.getenv("API_KEY_NONCE", None)
        if API_KEY_DEK is None or API_KEY_NONCE is None:
            self.existed_dek = False
            logger.info(f"API_KEY_DEK and API_KEY_NONCE not found, generating new ones")
            self.API_KEY_DEK, self.API_KEY_NONCE = self._generate_dek_and_nonce()
        else:
            logger.info(f"API_KEY_DEK and API_KEY_NONCE already exists")
            self.API_KEY_DEK = base64.b64decode(API_KEY_DEK)
            self.API_KEY_NONCE = base64.b64decode(API_KEY_NONCE)

    def load_config(self):
        for _, model_config in self.config.wikipedia.models.items():
            model_config._api_key_plaintext = self.wrap_api_key(model_config)

        self.dump_config()
        if not self.existed_dek:
            set_key(".env", "API_KEY_DEK", base64.b64encode(self.API_KEY_DEK).decode('utf-8'), quote_mode="always")
            set_key(".env", "API_KEY_NONCE", base64.b64encode(self.API_KEY_NONCE).decode('utf-8'), quote_mode="always")

    def dump_config(self):
        data = self.config.model_dump()
        with open(self.path, 'w') as f:
            dump(data, f)

    def wrap_api_key(self, model_config: ModelConfig) -> str:
        api_key = model_config.api_key
        if api_key is None:
            return None
        cipher = AESGCMSIV(self.API_KEY_DEK)
        if self.existed_dek and not api_key.startswith("plaintext("):
            model_config.api_key = api_key
            return cipher.decrypt(self.API_KEY_NONCE, base64.b64decode(api_key.encode('utf-8')), None).decode('utf-8')
        elif self.existed_dek and api_key.startswith("plaintext("):
            model_config.api_key = base64.b64encode(cipher.encrypt(self.API_KEY_NONCE, api_key.encode('utf-8'),
                                                                   None)).decode('utf-8')
            return api_key.split("plaintext(")[1].split(")")[0]
        else:
            encrypted_api_key = base64.b64encode(cipher.encrypt(self.API_KEY_NONCE, api_key.encode('utf-8'),
                                                                None)).decode('utf-8')
            model_config.api_key = encrypted_api_key
            return api_key

    def _generate_dek_and_nonce(self) -> tuple[bytes, bytes]:
        key = AESGCMSIV.generate_key(256)
        nonce = os.urandom(12)
        return key, nonce


config = None

lock = threading.Lock()


def get_config() -> ConfigInner:
    global config
    if config is None:
        with lock:
            if config is None:
                config_file = os.path.join(os.getcwd(), os.getenv("CONFIG", "config.toml"))
                config = Config(config_file)
                config.load_config()
    return config.config
