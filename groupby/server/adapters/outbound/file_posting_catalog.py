"""보여 줄 공고의 목록을 파일에서 얻는 어댑터. 특징이 저장된 공고가 목록이고, 제목은 고객사가 넘긴 것에서 얻는다."""
import json
from pathlib import Path


class FilePostingCatalog:
    def __init__(self, features_root: Path, inbox: Path):
        self._features_root = features_root
        self._inbox = inbox

    def posting_ids(self) -> list[str]:
        return sorted(p.stem for p in self._features_root.glob("*.json"))

    def title_of(self, posting_id: str) -> str | None:
        path = self._inbox / f"{posting_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8")).get("title")
