"""제목과 읽은 내용을 서비스 제공사에 넘기는 어댑터.

실제 서비스라면 서버로 보내는 요청이다. 이 과제에서는 두 프로그램이 함께 보는 폴더에 파일로 둔다.
"""
import json
from dataclasses import asdict
from pathlib import Path

from groupby.shared.submission import Submission


class FileSubmitter:
    def __init__(self, root: Path):
        self._root = root

    def submit(self, submission: Submission) -> Path:
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / f"{submission.posting_id}.json"
        path.write_text(json.dumps(asdict(submission), ensure_ascii=False, indent=2), encoding="utf-8")
        return path
