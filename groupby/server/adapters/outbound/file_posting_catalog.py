"""보여 줄 공고의 목록을 파일에서 얻는 어댑터. 특징이 저장된 공고가 목록이고, 제목은 고객사가 넘긴 것에서 얻는다."""
import json
from pathlib import Path


class FilePostingCatalog:
    def __init__(self, features_root: Path, inbox: Path):
        self._features_root = features_root
        self._inbox = inbox

    def posting_ids(self) -> list[str]:
        # 공고 번호가 큰 것(최근에 올라온 공고)이 먼저다.
        return sorted((p.stem for p in self._features_root.glob("*.json")), key=int, reverse=True)

    def title_of(self, posting_id: str) -> str | None:
        return self._submitted(posting_id).get("title")

    def text_of(self, posting_id: str) -> str | None:
        return self._submitted(posting_id).get("text")

    def _submitted(self, posting_id: str) -> dict:
        path = self._inbox / f"{posting_id}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
