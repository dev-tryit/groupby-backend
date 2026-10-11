"""고객사가 넘긴 것을 읽어 오는 어댑터. 이 과제에서는 두 프로그램이 함께 보는 폴더의 파일이다."""
import json
from pathlib import Path

from groupby.shared.submission import Submission


class FileSubmissionSource:
    def __init__(self, root: Path):
        self._root = root

    def load(self, posting_id: str) -> Submission:
        path = self._root / f"{posting_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"공고 {posting_id}를 고객사가 넘긴 것이 없다. 먼저 고객사 프로그램을 실행한다.")
        return Submission(**json.loads(path.read_text(encoding="utf-8")))

    def posting_ids(self) -> list[str]:
        return sorted(p.stem for p in self._root.glob("*.json"))
