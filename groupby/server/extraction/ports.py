"""조건 추출이 바깥에 기대는 것."""
from typing import Protocol

from groupby.shared.submission import Submission

from .domain import PostingFeatures


class SubmissionSource(Protocol):
    def load(self, posting_id: str) -> Submission:
        """고객사가 넘긴 것(제목과 읽은 내용)을 돌려준다."""


class FeatureExtractor(Protocol):
    model: str

    def extract(self, submission: Submission) -> PostingFeatures:
        """제목과 읽은 내용 전체에서 직무와 그 직무의 특징을 뽑는다. 공고 하나에 한 번 부른다."""


class FeatureStore(Protocol):
    def load(self, posting_id: str) -> PostingFeatures | None: ...

    def save(self, features: PostingFeatures) -> None: ...
