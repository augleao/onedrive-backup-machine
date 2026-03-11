import os
import threading
from msal import SerializableTokenCache
from cryptography.fernet import Fernet, InvalidToken


class TokenCacheStorage:
    def __init__(self, path='token_cache.bin', key=None):
        self.path = path
        self._lock = threading.Lock()
        self.key = key or os.environ.get('SECURE_KEY')
        self._fernet = Fernet(self.key) if self.key else None

    def load(self):
        cache = SerializableTokenCache()
        if not os.path.exists(self.path):
            return cache
        with self._lock:
            with open(self.path, 'rb') as f:
                data = f.read()
            if not data:
                return cache
            try:
                if self._fernet:
                    data = self._fernet.decrypt(data)
                cache.deserialize(data.decode('utf-8'))
            except InvalidToken:
                # cannot decrypt — return empty cache
                return SerializableTokenCache()
        return cache

    def save(self, cache: SerializableTokenCache):
        data = cache.serialize().encode('utf-8')
        if self._fernet:
            data = self._fernet.encrypt(data)
        with self._lock:
            with open(self.path, 'wb') as f:
                f.write(data)
            try:
                os.chmod(self.path, 0o600)
            except Exception:
                pass
