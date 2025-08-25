from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from .config import settings
import certifi   # <--- add this
import os
_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None

# def get_db() -> AsyncIOMotorDatabase:
#     global _client, _db
#     if _db is None:
#         _client = AsyncIOMotorClient(settings.MONGO_URI)
#         _db = _client[settings.MONGO_DB]
#     return _db

# Try certifi first, fall back to system CA bundle (works on Render images)
ca_file = None
try:
    import certifi  # installed via requirements.txt
    ca_file = certifi.where()
except Exception:
    p = "/etc/ssl/certs/ca-certificates.crt"
    ca_file = p if os.path.exists(p) else None

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None

def get_db() -> AsyncIOMotorDatabase:
    global _client, _db
    if _db is None:
        kwargs = dict(tls=True, serverSelectionTimeoutMS=20000)
        if ca_file:
            kwargs["tlsCAFile"] = ca_file
        _client = AsyncIOMotorClient(settings.MONGO_URI, **kwargs)
        _db = _client[settings.MONGO_DB]
    return _db