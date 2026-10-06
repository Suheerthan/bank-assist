"""Saves approved interactions and feedback. Uses MongoDB when reachable, else a local JSON file."""
import json
import threading

from . import config

_lock = threading.Lock()


class Store:
    def __init__(self):
        self.backend = "json"
        self.db = None
        try:
            from pymongo import MongoClient
            client = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=1500)
            client.admin.command("ping")
            self.db = client[config.MONGO_DB]
            self.backend = "mongodb"
        except Exception as exc:
            print(f"[storage] MongoDB not reachable ({exc.__class__.__name__}); using {config.LOCAL_STORE.name}")

    # ---- json helpers ----
    def _read(self) -> dict:
        if config.LOCAL_STORE.exists():
            return json.loads(config.LOCAL_STORE.read_text(encoding="utf-8"))
        return {"interactions": [], "feedback": []}

    def _write(self, data: dict) -> None:
        config.LOCAL_STORE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- api ----
    def insert(self, collection: str, doc: dict) -> None:
        if self.db is not None:
            self.db[collection].insert_one(dict(doc))
            return
        with _lock:
            data = self._read()
            data.setdefault(collection, []).append(doc)
            self._write(data)

    def all(self, collection: str, limit: int = 200) -> list[dict]:
        if self.db is not None:
            return list(self.db[collection].find({}, {"_id": 0}).sort("saved_at", -1).limit(limit))
        with _lock:
            rows = self._read().get(collection, [])
        return list(reversed(rows))[:limit]

    def clear(self) -> None:
        if self.db is not None:
            self.db.interactions.delete_many({})
            self.db.feedback.delete_many({})
        elif config.LOCAL_STORE.exists():
            config.LOCAL_STORE.unlink()
