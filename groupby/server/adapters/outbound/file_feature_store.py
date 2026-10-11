"""뽑은 특징을 파일로 저장하는 어댑터."""
import json
from dataclasses import asdict
from pathlib import Path

from groupby.server.extraction.domain import Item, PostingFeatures, Section


class FileFeatureStore:
    def __init__(self, root: Path):
        self._root = root

    def _path(self, posting_id: str) -> Path:
        return self._root / f"{posting_id}.json"

    def load(self, posting_id: str) -> PostingFeatures | None:
        path = self._path(posting_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        data["sections"] = [Section(**s) for s in data["sections"]]
        data["items"] = [Item(**i) for i in data["items"]]
        return PostingFeatures(**data)

    def save(self, features: PostingFeatures) -> None:
        path = self._path(features.posting_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(features), ensure_ascii=False, indent=2), encoding="utf-8")
