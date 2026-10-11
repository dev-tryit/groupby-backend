"""점수의 도메인. 판정을 0~100점으로 계산한다. LLM을 쓰지 않는다.

    판정값       일치 2, 비슷 1, 다름 0
    점수         = 70 × 자격 충족률 + 30 × 우대 충족률
                   우대사항이 없는 공고는 100 × 자격 충족률

이유는 03_prd/prd.md 10.2에 있다.
"""
from dataclasses import dataclass, field
from fractions import Fraction

from groupby.server.extraction.domain import PostingFeatures
from groupby.server.matching.domain import DIFFERENT, MATCH, SIMILAR, ResumeMatch

POINTS = {MATCH: 2, SIMILAR: 1, DIFFERENT: 0}
FULL = POINTS[MATCH]
REQUIRED, PREFERRED = "자격요건", "우대사항"
# 자격요건은 중요한 조건이고 우대사항은 "있으면 좋다"는 뜻이다. 그래서 7 대 3이다.
REQUIRED_SHARE, PREFERRED_SHARE = 70, 30


@dataclass
class GroupScore:
    group: str
    points: int = 0
    full: int = 0
    matched: int = 0  # 일치한 조건의 수
    count: int = 0  # 조건의 수

    @property
    def rate(self) -> Fraction:
        return Fraction(self.points, self.full) if self.full else Fraction(0)


@dataclass
class Score:
    resume_id: str
    value: Fraction  # 0 ~ 100. 순서를 정할 때는 반올림하지 않은 이 값을 쓴다
    required: GroupScore
    preferred: GroupScore
    points_by_condition: dict[str, int] = field(default_factory=dict)

    @property
    def rounded(self) -> int:
        return int(self.value + Fraction(1, 2))


def score_resume(features: PostingFeatures, match: ResumeMatch) -> Score:
    groups = {REQUIRED: GroupScore(REQUIRED), PREFERRED: GroupScore(PREFERRED)}
    points_by_condition: dict[str, int] = {}
    for group in groups.values():
        for item in features.of(group.group):
            judgment = match.of(item.id)
            # 판정이 빠진 조건은 다름으로 친다. 확인하지 못한 것에 점수를 주지 않는다.
            points = POINTS[judgment.trusted_verdict] if judgment else 0
            points_by_condition[item.id] = points
            group.points += points
            group.full += FULL
            group.count += 1
            group.matched += points == FULL

    required, preferred = groups[REQUIRED], groups[PREFERRED]
    if required.count and preferred.count:
        value = REQUIRED_SHARE * required.rate + PREFERRED_SHARE * preferred.rate
    else:
        # 한 그룹이 없는 공고는 있는 그룹이 100점 전부를 갖는다. 공고가 적지 않은 것으로 점수를 깎지 않는다.
        value = 100 * (required.rate if required.count else preferred.rate)
    return Score(match.resume_id, value, required, preferred, points_by_condition)


@dataclass
class Ranked:
    rank: int
    score: Score


def rank(scores: list[Score]) -> list[Ranked]:
    """점수가 높은 순서로 세운다. 점수가 같으면 같은 순위다. 같은 순위 안에서는 이름 순서로 보여 준다."""
    ordered = sorted(scores, key=lambda s: (-s.value, s.resume_id))
    ranked: list[Ranked] = []
    for position, score in enumerate(ordered, start=1):
        same = ranked and ranked[-1].score.value == score.value
        ranked.append(Ranked(ranked[-1].rank if same else position, score))
    return ranked
