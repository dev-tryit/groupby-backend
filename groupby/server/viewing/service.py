"""보여 주기의 흐름. 저장된 특징과 비교에서 화면이 묻는 것을 만든다 (07_api/request-response).

LLM을 부르지 않는다. 점수와 순위는 저장하지 않고 물을 때마다 계산한다.
"""
import re

from groupby.server.extraction.domain import CONDITION_GROUPS, DUTY, SCORED_GROUPS, Item, PostingFeatures, mark_in_reading
from groupby.server.matching.domain import ResumeMatch
from groupby.server.matching.ports import Resume
from groupby.server.scoring.domain import GroupScore, Score, rank, score_resume

from .ports import FeatureReader, MatchReader, PostingCatalog, ResumeReader

NOT_WRITTEN = "이력서에 적혀 있지 않음"
UNVERIFIED = "근거를 확인하지 못함"


TITLE_NAME = re.compile(r"^#[^\n]*[—–-]\s*(\S[^\n]*?)\s*$")


def masked_name(resume_text: str) -> str | None:
    """이력서 첫 줄의 제목에서 이름을 얻어 가운데를 가린다. 화면의 목록에는 이름 전체를 내보내지 않는다.

    제목이 `# 이력서 — 이름`의 모양이 아니면 None이다. 그때 화면은 이력서 번호를 보여 준다.
    """
    lines = resume_text.strip().splitlines()
    found = TITLE_NAME.match(lines[0]) if lines else None
    if not found:
        return None
    name = found.group(1)
    if len(name) <= 1:
        return name
    if len(name) == 2:
        return name[0] + "*"
    return name[0] + "*" * (len(name) - 2) + name[-1]


class NotFound(Exception):
    pass


def item_key(posting_id: str, item: Item) -> str:
    return f"{posting_id}-{item.id}"


def resume_key(posting_id: str, resume_id: str) -> str:
    return f"{posting_id}-{resume_id}"


def mark_of(match: ResumeMatch, item: Item) -> str:
    judgment = match.of(item.id)
    if judgment is None or judgment.unverified:
        return UNVERIFIED
    if judgment.not_written:
        return NOT_WRITTEN
    return judgment.verdict


def group_view(group: GroupScore) -> dict | None:
    if not group.count:
        return None
    return {"points": group.points, "full": group.full, "matched": group.matched, "count": group.count}


class ViewResults:
    def __init__(self, catalog: PostingCatalog, features: FeatureReader, matches: MatchReader, resumes: ResumeReader):
        self._catalog = catalog
        self._features = features
        self._matches = matches
        self._resumes = resumes

    def postings(self) -> dict:
        summaries = []
        for posting_id in self._catalog.posting_ids():
            features = self._features.load(posting_id)
            if features is not None:
                summaries.append({"posting_id": posting_id, "title": self._title(features), "job": features.job})
        return {"postings": summaries}

    def posting(self, posting_id: str) -> dict:
        features = self._load_features(posting_id)
        text = self._catalog.text_of(posting_id)
        if text:
            # 넘겨받은 읽은 내용이 있으면 조건이 그 안에 있는지를 지금 다시 계산한다.
            mark_in_reading(features.items, text)
        matched = self._matched(features)
        scores = {m.resume_id: score_resume(features, m) for _, m in matched}
        names = {r.resume_id: masked_name(r.text) for r, _ in matched}
        by_id = {m.resume_id: m for _, m in matched}
        conditions = [item for group in CONDITION_GROUPS for item in features.of(group)]
        return {
            "posting_id": posting_id,
            "title": self._title(features),
            "job": features.job,
            "text": text,
            "duties": [
                {"item_id": item_key(posting_id, item), "no": item.id, "text": item.text}
                for item in features.of(DUTY)
            ],
            "conditions": {
                group: [
                    {"item_id": item_key(posting_id, item), "no": item.id, "text": item.text, "in_reading": item.in_reading}
                    for item in features.of(group)
                ]
                for group in CONDITION_GROUPS
            },
            "ranking": [
                {
                    "rank": entry.rank,
                    "resume_id": resume_key(posting_id, entry.score.resume_id),
                    "name": names[entry.score.resume_id],
                    **self._score_view(entry.score),
                    "verdicts": [
                        {"item_id": item_key(posting_id, item), "mark": mark_of(by_id[entry.score.resume_id], item)}
                        for item in conditions
                    ],
                }
                for entry in rank(list(scores.values()))
            ],
        }

    def resume_match(self, resume_id: str) -> dict:
        for posting_id in self._catalog.posting_ids():
            features = self._features.load(posting_id)
            if features is None:
                continue
            for resume, match in self._matched(features):
                if resume_key(posting_id, resume.resume_id) == resume_id:
                    return self._match_view(features, resume, match)
        raise NotFound(resume_id)

    def _match_view(self, features: PostingFeatures, resume: Resume, match: ResumeMatch) -> dict:
        score = score_resume(features, match)
        judgments = []
        for group in CONDITION_GROUPS:
            for item in features.of(group):
                judgment = match.of(item.id)
                judgments.append(
                    {
                        "item_id": item_key(features.posting_id, item),
                        "group": group,
                        "mark": mark_of(match, item),
                        "points": score.points_by_condition[item.id] if group in SCORED_GROUPS else None,
                        "quotes": judgment.quotes if judgment else [],
                        "quotes_in_resume": judgment.quotes_in_resume if judgment else False,
                        "thinking": judgment.thinking if judgment else "",
                    }
                )
        return {
            "posting_id": features.posting_id,
            "resume_id": resume_key(features.posting_id, resume.resume_id),
            "name": masked_name(resume.text),
            **self._score_view(score),
            "judgments": judgments,
            "resume_text": resume.text,
        }

    @staticmethod
    def _score_view(score: Score) -> dict:
        return {"score": score.rounded, "required": group_view(score.required), "preferred": group_view(score.preferred)}

    def _title(self, features: PostingFeatures) -> str:
        return self._catalog.title_of(features.posting_id) or features.job

    def _load_features(self, posting_id: str) -> PostingFeatures:
        features = self._features.load(posting_id) if posting_id in self._catalog.posting_ids() else None
        if features is None:
            raise NotFound(posting_id)
        return features

    def _matched(self, features: PostingFeatures) -> list[tuple[Resume, ResumeMatch]]:
        """비교가 저장된 이력서만 보여 준다."""
        pairs = []
        for resume in self._resumes.of_posting(features.posting_id):
            match = self._matches.load(features.posting_id, resume.resume_id)
            if match is not None:
                pairs.append((resume, match))
        return pairs
