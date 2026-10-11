"""비교의 흐름. 이력서마다 조건과 맞대어 판정을 받고, 근거를 이력서와 대조하고, 저장한다."""
from groupby.server.extraction.domain import PostingFeatures

from .domain import ResumeMatch, mark_quotes
from .ports import Matcher, MatchStore, Resume


class MatchResume:
    def __init__(self, matcher: Matcher, store: MatchStore):
        self._matcher = matcher
        self._store = store

    def __call__(self, features: PostingFeatures, resume: Resume) -> ResumeMatch:
        saved = self._store.load(features.posting_id, resume.resume_id)
        if saved is not None:
            return saved
        match = self._matcher.match(features, resume)
        mark_quotes(match.judgments, resume.text)
        self._store.save(match)
        return match
