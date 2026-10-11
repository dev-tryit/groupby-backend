"""폴더의 이력서 파일을 읽어 오는 어댑터. 공고 번호를 이름으로 하는 폴더 아래의 글자 파일이다."""
from pathlib import Path

from groupby.server.matching.ports import Resume


class FileResumeSource:
    def __init__(self, root: Path):
        self._root = root

    def of_posting(self, posting_id: str) -> list[Resume]:
        folder = self._root / posting_id
        return [Resume(path.stem, path.read_text(encoding="utf-8")) for path in sorted(folder.glob("*.md"))]
