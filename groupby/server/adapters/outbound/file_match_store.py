"""비교의 결과를 파일로 저장하는 어댑터."""
import json
from dataclasses import asdict
from pathlib import Path

from groupby.server.matching.domain import Judgment, ResumeMatch


class FileMatchStore:
    def __init__(self, root: Path):
        self._root = root

    def _path(self, posting_id: str, resume_id: str) -> Path:
        return self._root / posting_id / f"{resume_id}.json"

    def load(self, posting_id: str, resume_id: str) -> ResumeMatch | None:
        path = self._path(posting_id, resume_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        data["judgments"] = [Judgment(**j) for j in data["judgments"]]
        return ResumeMatch(**data)

    def save(self, match: ResumeMatch) -> None:
        path = self._path(match.posting_id, match.resume_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(match), ensure_ascii=False, indent=2), encoding="utf-8")
