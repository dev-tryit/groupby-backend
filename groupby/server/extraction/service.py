"""특징 추출의 흐름. 고객사가 넘긴 제목과 읽은 내용에서 직무와 그 직무의 특징을 뽑고, 읽은 내용과 대조하고, 저장한다."""
from .domain import PostingFeatures, mark_in_reading
from .ports import FeatureExtractor, FeatureStore, SubmissionSource


class ExtractFeatures:
    def __init__(self, submissions: SubmissionSource, extractor: FeatureExtractor, store: FeatureStore):
        self._submissions = submissions
        self._extractor = extractor
        self._store = store

    def __call__(self, posting_id: str) -> PostingFeatures:
        """특징은 공고마다 한 번만 뽑는다. 지원자마다 조건이 달라지면 랭킹이 공정하지 않다."""
        saved = self._store.load(posting_id)
        if saved is not None:
            return saved

        submission = self._submissions.load(posting_id)
        result = self._extractor.extract(submission)
        mark_in_reading(result.items, submission.text)
        self._store.save(result)
        return result
