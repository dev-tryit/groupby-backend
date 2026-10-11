"""비교가 바깥에 기대는 것."""
from dataclasses import dataclass
from typing import Protocol

from groupby.server.extraction.domain import PostingFeatures

from .domain import ResumeMatch


@dataclass(frozen=True)
class Resume:
    resume_id: str
    text: str


class ResumeSource(Protocol):
    def of_posting(self, posting_id: str) -> list[Resume]:
        """공고에 지원한 이력서들을 돌려준다."""


class Matcher(Protocol):
    model: str

    def match(self, features: PostingFeatures, resume: Resume) -> ResumeMatch:
        """조건마다 이력서를 보고 판정과 근거를 낸다. 이력서 하나에 한 번 부른다."""


class MatchStore(Protocol):
    def load(self, posting_id: str, resume_id: str) -> ResumeMatch | None: ...

    def save(self, match: ResumeMatch) -> None: ...
