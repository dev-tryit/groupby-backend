"""LLM이 낸 것을 원문과 대조하는 규칙, 그리고 수집과 읽기의 규칙에 대한 테스트. LLM을 부르지 않는다."""
import unittest

import numpy as np

from groupby.client.collecting.domain import clean_title, is_body_image, posting_id_of
from groupby.client.reading.domain import plan_slices
from groupby.server.extraction.domain import Item, mark_in_reading, settle_group
from groupby.server.matching.domain import DIFFERENT, MATCH, Judgment, mark_quotes

RESUME = "## 경력 (총 2년 6개월)\n\n### 모아리빙 · 브랜드마케팅팀 사원 · 2024.04 ~ 현재\n- 매출, 광고비, ROAS 지표를 주 단위로 보았습니다."


class EvidenceInResume(unittest.TestCase):
    """지어낸 근거를 잡는가. 과제에서 가장 걱정한 것이 LLM이 지어내는 것이다."""

    def check(self, quotes, verdict=MATCH):
        judgment = Judgment("C1", "", quotes, verdict)
        mark_quotes([judgment], RESUME)
        return judgment

    def test_exact_quote_is_accepted(self):
        self.assertFalse(self.check(["경력 (총 2년 6개월)"]).unverified)

    def test_spacing_and_bullet_marks_do_not_matter(self):
        self.assertFalse(self.check(["- 매출, 광고비,  ROAS 지표를 주 단위로 보았습니다."]).unverified)

    def test_same_looking_character_in_another_code_is_accepted(self):
        """읽을 때마다 'ㄴ'이 U+3134로도 U+1102로도 나온다. 눈으로 같은 글자는 같다고 본다."""
        judgment = Judgment("C1", "", ["운영 \u1102 메타"], MATCH)
        mark_quotes([judgment], "매체별 운영 \u3134 메타, 네이버")
        self.assertTrue(judgment.quotes_in_resume)

    def test_one_changed_character_is_rejected(self):
        """'보았습니다'를 '봤습니다'로 바꿔 옮기면 믿지 않는다."""
        judgment = self.check(["매출, 광고비, ROAS 지표를 주 단위로 봤습니다."])
        self.assertTrue(judgment.unverified)
        self.assertEqual(judgment.trusted_verdict, DIFFERENT)

    def test_distant_phrases_glued_together_are_rejected(self):
        """떨어져 있는 구절을 이어 붙인 근거는 믿지 않는다. 이력서에 그렇게 이어진 글이 없기 때문이다."""
        self.assertTrue(self.check(["경력 (총 2년 6개월) 매출, 광고비"]).unverified)

    def test_neighbouring_lines_are_accepted(self):
        """바로 이어진 두 줄을 한 근거로 옮긴 것은 받아들인다. 줄바꿈과 글머리 기호의 차이는 보지 않는다."""
        self.assertFalse(self.check(["경력 (총 2년 6개월) 모아리빙 · 브랜드마케팅팀 사원"]).unverified)

    def test_every_quote_must_be_in_the_resume(self):
        self.assertTrue(self.check(["경력 (총 2년 6개월)", "팀장으로 일했습니다"]).unverified)

    def test_different_without_quote_means_not_written(self):
        """이력서에 적혀 있지 않은 것은 없는 것과 구별해서 보여 준다."""
        self.assertTrue(self.check([], DIFFERENT).not_written)
        self.assertFalse(self.check(["경력 (총 2년 6개월)"], DIFFERENT).not_written)


class ConditionsInReading(unittest.TestCase):
    def test_condition_not_in_the_posting_is_marked(self):
        items = [Item("C1", "", "자격요건", "관련 업무 경력 3년 이상이신 분", ""), Item("C2", "", "자격요건", "석사 이상", "")]
        mark_in_reading(items, "자격요건 (필수)  · 관련 업무 경력 3년\n이상이신 분")
        self.assertEqual([i.in_reading for i in items], [True, False])

    def test_personal_circumstance_is_always_reference(self):
        """개인 사정은 공고가 필수 칸에 적었어도 점수에 넣지 않는다."""
        self.assertEqual(settle_group("개인 사정", "자격요건"), "참고사항")
        self.assertEqual(settle_group("일과 배움으로 갖춘 것", "자격요건"), "자격요건")


class Collecting(unittest.TestCase):
    def test_posting_id_from_address(self):
        self.assertEqual(posting_id_of("https://www.saramin.co.kr/zf_user/jobs/relay/view?view_type=search&rec_idx=54762507&x=1"), "54762507")
        self.assertEqual(posting_id_of("55240017"), "55240017")
        with self.assertRaises(ValueError):
            posting_id_of("https://www.saramin.co.kr/")

    def test_decoration_images_are_skipped(self):
        self.assertTrue(is_body_image("https://pds.saramin.co.kr/recruit/recruit/202610/08/a_recruit.png"))
        self.assertFalse(is_body_image("//static.saraminimage.co.kr/static/hiring/images/template/toptype/1.webp"))
        self.assertFalse(is_body_image("https://www.saraminimage.co.kr/recruit/bbs/watermark.png"))

    def test_site_name_is_removed_from_title(self):
        self.assertEqual(clean_title("[(주)삼천리] 회계부문 경력사원 모집 - 사람인"), "[(주)삼천리] 회계부문 경력사원 모집")


class Slicing(unittest.TestCase):
    def test_cuts_avoid_rows_with_text(self):
        """세로로 긴 이미지를 자를 때 글자가 있는 줄을 가로지르지 않는다."""
        gray = np.full((4000, 100), 255.0, dtype=np.float32)
        gray[:, ::2] = 0  # 모든 줄에 글자가 있다고 본다
        blank_rows = [1310, 2650]
        for row in blank_rows:
            gray[row] = 255  # 글자가 없는 줄
        boxes = plan_slices(gray)
        self.assertEqual([b.bottom for b in boxes[:-1]], blank_rows)
        self.assertEqual((boxes[0].top, boxes[-1].bottom), (0, 4000))
        self.assertTrue(all(a.bottom == b.top for a, b in zip(boxes, boxes[1:])))

    def test_short_image_is_not_cut(self):
        self.assertEqual(len(plan_slices(np.zeros((750, 660), dtype=np.float32))), 1)


if __name__ == "__main__":
    unittest.main()
