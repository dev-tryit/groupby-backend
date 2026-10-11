"""수집이 바깥에 기대는 것."""
from typing import Protocol

from .domain import CollectedPosting


class PostingSite(Protocol):
    def fetch(self, posting_id: str) -> CollectedPosting:
        """채용 사이트에서 공고의 제목과 본문 이미지를 가져온다."""


class CollectedStore(Protocol):
    def load(self, posting_id: str) -> CollectedPosting | None: ...

    def save(self, posting: CollectedPosting) -> None: ...
