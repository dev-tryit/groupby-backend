"""화면이 묻는 API의 테스트. LLM도 파일도 쓰지 않는다.

저장된 판정에서 점수, 순위, 화면의 표시가 07_api/request-response에 적은 대로 나오는지를 본다.
"""
import unittest

from groupby.server.adapters.inbound.http import BadRequest, answer
from groupby.server.extraction.domain import Item, PostingFeatures
from groupby.server.matching.domain import DIFFERENT, MATCH, SIMILAR, Judgment, ResumeMatch
from groupby.server.matching.ports import Resume
from groupby.server.viewing.service import NOT_WRITTEN, UNVERIFIED, NotFound, ViewResults, masked_name

FEATURES = PostingFeatures(
    "100",
    "m",
    "회계",
    "",
    items=[
        Item("D1", "", "담당업무", "결산", ""),
        Item("C1", "", "자격요건", "경력 3년", "", in_reading=True),
        Item("C2", "", "우대사항", "SAP", "", in_reading=True),
        Item("C3", "", "참고사항", "군필", "", in_reading=False),
    ],
)


def judged(resume_id: str, c1: Judgment, c2: Judgment) -> ResumeMatch:
    return ResumeMatch("100", resume_id, "m", [c1, c2])


MATCHES = {
    "a": judged("a", Judgment("C1", "", ["경력 4년"], MATCH, True), Judgment("C2", "", ["SAP 사용"], MATCH, True)),
    "b": judged("b", Judgment("C1", "", ["경력 2년"], SIMILAR, True), Judgment("C2", "", [], DIFFERENT, False)),
    "c": judged("c", Judgment("C1", "", ["없는 구절"], MATCH, False), Judgment("C2", "", ["SAP 사용"], MATCH, True)),
}


class Stored:
    text = "회계 경력사원 모집\n경력 3년"

    def posting_ids(self):
        return ["100"]

    def title_of(self, posting_id):
        return "회계 경력사원 모집"

    def text_of(self, posting_id):
        return self.text

    def load(self, posting_id, resume_id=None):
        return FEATURES if resume_id is None else MATCHES.get(resume_id)

    def of_posting(self, posting_id):
        return [Resume(r, f"{r}의 이력서") for r in ("a", "b", "c", "not-matched-yet")]


def view() -> ViewResults:
    stored = Stored()
    return ViewResults(stored, stored, stored, stored)


class Posting(unittest.TestCase):
    def setUp(self):
        self.posting = answer(view(), "/api/postings/100")

    def test_ranking_is_ordered_by_score(self):
        ranking = [(r["rank"], r["resume_id"], r["score"]) for r in self.posting["ranking"]]
        self.assertEqual(ranking, [(1, "100-a", 100), (2, "100-b", 35), (3, "100-c", 30)])

    def test_resume_without_stored_match_is_not_ranked(self):
        self.assertNotIn("100-not-matched-yet", [r["resume_id"] for r in self.posting["ranking"]])

    def test_posting_carries_the_submitted_text(self):
        self.assertEqual(self.posting["text"], "회계 경력사원 모집\n경력 3년")

    def test_in_reading_is_computed_from_the_submitted_text(self):
        """저장해 둔 값이 아니라 지금 넘겨받은 읽은 내용으로 본다. C3은 저장된 값이 거짓이지만 읽은 내용에 있다."""
        stored = Stored()
        stored.text = "경력 3년\n군필"
        conditions = ViewResults(stored, stored, stored, stored).posting("100")["conditions"]
        found = {c["no"]: c["in_reading"] for cs in conditions.values() for c in cs}
        self.assertEqual(found, {"C1": True, "C2": False, "C3": True})

    def test_posting_without_a_submission_has_no_text(self):
        """수집이 실패한 실행이다. 조건과 랭킹은 나오고 공고 원문은 없다."""
        stored = Stored()
        stored.text = None
        posting = ViewResults(stored, stored, stored, stored).posting("100")
        self.assertIsNone(posting["text"])
        self.assertEqual(len(posting["ranking"]), 3)

    def test_conditions_are_grouped_and_duties_are_separate(self):
        self.assertEqual([d["no"] for d in self.posting["duties"]], ["D1"])
        self.assertEqual({g: [c["no"] for c in cs] for g, cs in self.posting["conditions"].items()},
                         {"자격요건": ["C1"], "우대사항": ["C2"], "참고사항": ["C3"]})


class ResumeMatchView(unittest.TestCase):
    def marks(self, resume_id):
        return {j["item_id"]: (j["mark"], j["points"]) for j in answer(view(), f"/api/resumes/{resume_id}")["judgments"]}

    def test_quote_not_in_resume_is_not_trusted(self):
        """LLM이 일치라고 해도 근거가 이력서에 없으면 0점이다."""
        self.assertEqual(self.marks("100-c")["100-C1"], (UNVERIFIED, 0))

    def test_no_quote_is_shown_as_not_written(self):
        self.assertEqual(self.marks("100-b")["100-C2"], (NOT_WRITTEN, 0))

    def test_reference_condition_has_no_points(self):
        self.assertIsNone(self.marks("100-a")["100-C3"][1])

    def test_resume_text_comes_with_the_evidence(self):
        self.assertEqual(answer(view(), "/api/resumes/100-a")["resume_text"], "a의 이력서")


class ApplicantName(unittest.TestCase):
    """목록에는 이름 전체를 내보내지 않는다. 가운데를 가린다."""

    def test_name_is_masked(self):
        self.assertEqual(masked_name("# 이력서 — 강민재\n\n## 경력"), "강*재")
        self.assertEqual(masked_name("# 성과 중심 이력서 — 남궁민수"), "남**수")
        self.assertEqual(masked_name("# 이력서 - 이산"), "이*")

    def test_resume_without_a_name_in_its_title_has_no_name(self):
        """그때 화면은 이력서 번호를 보여 준다."""
        self.assertIsNone(masked_name("경력 5년의 마케터입니다."))
        self.assertIsNone(masked_name(""))

    def test_ranking_carries_the_masked_name(self):
        self.assertIsNone(answer(view(), "/api/postings/100")["ranking"][0]["name"])


class Errors(unittest.TestCase):
    def test_unknown_posting_and_resume_are_not_found(self):
        for path in ("/api/postings/999", "/api/resumes/100-zzz", "/api/unknown"):
            with self.assertRaises(NotFound):
                answer(view(), path)

    def test_malformed_ids_are_rejected(self):
        for path in ("/api/postings/abc", "/api/resumes/a.b"):
            with self.assertRaises(BadRequest):
                answer(view(), path)


if __name__ == "__main__":
    unittest.main()
