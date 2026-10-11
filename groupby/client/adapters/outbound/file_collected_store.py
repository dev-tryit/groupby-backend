"""수집한 공고(제목과 이미지)를 폴더에 저장하는 어댑터."""
import json
from pathlib import Path

from groupby.client.collecting.domain import CollectedImage, CollectedPosting

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


class FileCollectedStore:
    def __init__(self, root: Path):
        self._root = root

    def load(self, posting_id: str) -> CollectedPosting | None:
        folder = self._root / posting_id
        meta = folder / "posting.json"
        if not meta.exists():
            return None
        title = json.loads(meta.read_text(encoding="utf-8"))["title"]
        paths = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
        return CollectedPosting(posting_id, title, [CollectedImage(p.name, p.read_bytes()) for p in paths])

    def save(self, posting: CollectedPosting) -> None:
        folder = self._root / posting.posting_id
        folder.mkdir(parents=True, exist_ok=True)
        for image in posting.images:
            (folder / image.name).write_bytes(image.content)
        meta = {"posting_id": posting.posting_id, "title": posting.title}
        (folder / "posting.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
