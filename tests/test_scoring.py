"""점수 계산의 테스트. LLM을 부르지 않는다.

점수의 식이 03_prd/prd.md 10.2에 적은 대로 움직이는지를 본다.
정확한 점수 몇 개와, 식이 지켜야 하는 성질을 확인한다.
"""
import itertools
import unittest

from groupby.server.extraction.domain import Item, PostingFeatures
from groupby.server.matching.domain import DIFFERENT, MATCH, SIMILAR, VERDICTS, Judgment, ResumeMatch
from groupby.server.scoring.domain import rank, score_resume


def posting(required: int, preferred: int, reference: int = 0) -> PostingFeatures:
    items = [Item(f"R{i}", "", "자격요건", f"자격 {i}", "") for i in range(required)]
    items += [Item(f"P{i}", "", "우대사항", f"우대 {i}", "") for i in range(preferred)]
    items += [Item(f"N{i}", "", "참고사항", f"참고 {i}", "") for i in range(reference)]
    return PostingFeatures("p", "m", "직무", "", items=items)


def match(resume_id: str = "r", **verdicts: str) -> ResumeMatch:
    judgments = [Judgment(cid, "", ["근거"], verdict, quotes_in_resume=True) for cid, verdict in verdicts.items()]
    return ResumeMatch("p", resume_id, "m", judgments)


class ExactScores(unittest.TestCase):
    """문서의 예와 같은 값이 나오는가. 회계 공고의 모양(자격요건 3, 우대사항 2)이다."""

    def setUp(self):
        self.posting = posting(3, 2)

    def score(self, **verdicts):
        return score_resume(self.posting, match(**verdicts)).rounded

    def test_everything_matched_is_100(self):
        self.assertEqual(self.score(R0=MATCH, R1=MATCH, R2=MATCH, P0=MATCH, P1=MATCH), 100)

    def test_nothing_matched_is_0(self):
        self.assertEqual(self.score(R0=DIFFERENT, R1=DIFFERENT, R2=DIFFERENT, P0=DIFFERENT, P1=DIFFERENT), 0)

    def test_requirements_only_is_70(self):
        self.assertEqual(self.score(R0=MATCH, R1=MATCH, R2=MATCH, P0=DIFFERENT, P1=DIFFERENT), 70)

    def test_one_requirement_similar_is_88(self):
        self.assertEqual(self.score(R0=MATCH, R1=SIMILAR, R2=MATCH, P0=MATCH, P1=MATCH), 88)

    def test_one_requirement_missing_is_77(self):
        self.assertEqual(self.score(R0=DIFFERENT, R1=MATCH, R2=MATCH, P0=MATCH, P1=MATCH), 77)


class Rules(unittest.TestCase):
    def test_posting_without_preferences_gives_requirements_all_100(self):
        """우대사항이 없는 공고. 공고가 적지 않은 것으로 점수를 깎지 않는다."""
        p = posting(5, 0)
        self.assertEqual(score_resume(p, match(**{f"R{i}": MATCH for i in range(5)})).rounded, 100)
        four = {f"R{i}": MATCH for i in range(4)} | {"R4": DIFFERENT}
        self.assertEqual(score_resume(p, match(**four)).rounded, 80)

    def test_reference_items_never_change_the_score(self):
        """참고사항은 참고만 한다."""
        p = posting(2, 1, reference=2)
        base = dict(R0=MATCH, R1=SIMILAR, P0=MATCH)
        scores = {
            score_resume(p, match(**base, N0=a, N1=b)).value for a, b in itertools.product(VERDICTS, repeat=2)
        }
        self.assertEqual(len(scores), 1)

    def test_unverified_evidence_counts_as_different(self):
        """근거가 이력서 안에 없으면 모델이 일치라고 해도 점수를 주지 않는다."""
        p = posting(1, 0)
        made_up = ResumeMatch("p", "r", "m", [Judgment("R0", "", ["지어낸 근거"], MATCH, quotes_in_resume=False)])
        self.assertEqual(score_resume(p, made_up).rounded, 0)

    def test_missing_judgment_counts_as_different(self):
        """모델이 빠뜨린 조건에 점수를 주지 않는다."""
        self.assertEqual(score_resume(posting(2, 0), match(R0=MATCH)).rounded, 50)


class Properties(unittest.TestCase):
    """판정의 모든 조합에서 지켜져야 하는 성질."""

    def setUp(self):
        self.posting = posting(3, 2)
        self.ids = [item.id for item in self.posting.items]
        self.all = [dict(zip(self.ids, combo)) for combo in itertools.product(VERDICTS, repeat=len(self.ids))]

    def test_score_stays_between_0_and_100(self):
        for verdicts in self.all:
            self.assertTrue(0 <= score_resume(self.posting, match(**verdicts)).value <= 100)

    def test_better_verdict_never_lowers_the_score(self):
        """조건 하나의 판정이 좋아지면 점수가 내려가지 않는다."""
        better = {DIFFERENT: SIMILAR, SIMILAR: MATCH}
        for verdicts in self.all:
            before = score_resume(self.posting, match(**verdicts)).value
            for cid, verdict in verdicts.items():
                if verdict in better:
                    after = score_resume(self.posting, match(**(verdicts | {cid: better[verdict]}))).value
                    self.assertGreater(after, before)

    def test_score_does_not_depend_on_other_applicants(self):
        """한 사람의 점수는 함께 지원한 사람에 따라 달라지지 않는다."""
        mine = match("me", R0=MATCH, R1=SIMILAR, R2=DIFFERENT, P0=MATCH, P1=DIFFERENT)
        alone = score_resume(self.posting, mine).value
        other = match("other", **{cid: MATCH for cid in self.ids})
        ranked = rank([score_resume(self.posting, m) for m in (mine, other)])
        self.assertEqual(next(e.score.value for e in ranked if e.score.resume_id == "me"), alone)


class Ranking(unittest.TestCase):
    def test_same_score_shares_the_same_rank(self):
        p = posting(2, 0)
        scores = [
            score_resume(p, match("a", R0=MATCH, R1=MATCH)),
            score_resume(p, match("b", R0=MATCH, R1=MATCH)),
            score_resume(p, match("c", R0=MATCH, R1=DIFFERENT)),
        ]
        self.assertEqual([(e.rank, e.score.resume_id) for e in rank(scores)], [(1, "a"), (1, "b"), (3, "c")])

    def test_rank_does_not_depend_on_input_order(self):
        p = posting(2, 0)
        scores = [score_resume(p, match(n, R0=v, R1=MATCH)) for n, v in (("a", DIFFERENT), ("b", MATCH), ("c", SIMILAR))]
        first = [(e.rank, e.score.resume_id) for e in rank(scores)]
        self.assertEqual([(e.rank, e.score.resume_id) for e in rank(scores[::-1])], first)


if __name__ == "__main__":
    unittest.main()
