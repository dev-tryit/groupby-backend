"""읽은 결과를 파일로 저장하는 어댑터."""
import json
from dataclasses import asdict
from pathlib import Path

from groupby.client.reading.domain import PostingReading, SliceReading


class FileReadingStore:
    def __init__(self, root: Path):
        self._root = root

    def _path(self, posting_id: str) -> Path:
        return self._root / posting_id / "reading.json"

    def load(self, posting_id: str) -> PostingReading | None:
        path = self._path(posting_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return PostingReading(data["posting_id"], data["model"], [SliceReading(**s) for s in data["slices"]])

    def save(self, reading: PostingReading) -> None:
        path = self._path(reading.posting_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(reading), ensure_ascii=False, indent=2), encoding="utf-8")
        (path.parent / "reading.txt").write_text(reading.text, encoding="utf-8")
