"""보여 주기가 바깥에 기대는 것. 저장된 것을 읽기만 한다."""
from typing import Protocol

from groupby.server.extraction.domain import PostingFeatures
from groupby.server.matching.domain import ResumeMatch
from groupby.server.matching.ports import Resume


class PostingCatalog(Protocol):
    def posting_ids(self) -> list[str]:
        """특징이 저장된 공고의 번호들."""

    def title_of(self, posting_id: str) -> str | None:
        """고객사가 넘긴 제목. 넘긴 것이 없으면 None."""


class FeatureReader(Protocol):
    def load(self, posting_id: str) -> PostingFeatures | None: ...


class MatchReader(Protocol):
    def load(self, posting_id: str, resume_id: str) -> ResumeMatch | None: ...


class ResumeReader(Protocol):
    def of_posting(self, posting_id: str) -> list[Resume]: ...
