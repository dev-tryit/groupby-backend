"""로그의 테스트. LLM도 사람인도 부르지 않는다. 호출을 흉내 낸 것으로 본다.

11_log/log.md가 정한 것을 본다. 한 줄에 JSON 하나, 넘겨받은 trace id를 이어 쓰는 것,
LLM을 부른 것과 저장된 결과를 쓴 것의 구별, 대조에 실패한 것은 번호만 남기는 것.
"""
import contextlib
import io
import json
import unittest

from PIL import Image

from groupby.client.adapters.inbound.cli import submit_posting
from groupby.client.collecting.domain import CollectedImage, CollectedPosting
from groupby.server.adapters.inbound.cli import match_postings
from groupby.server.extraction.domain import Item, PostingFeatures
from groupby.server.matching.domain import MATCH, Judgment, ResumeMatch
from groupby.server.matching.ports import Resume
from groupby.shared.submission import Submission

SECRET_QUOTE = "이력서에 없는 지어낸 구절"
RESUME_TEXT = "감사부문 경력 4년"
READING_TEXT = "회계 경력사원 모집 경력 3년"


def captured(run) -> list[dict]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        run()
    return [json.loads(line) for line in out.getvalue().splitlines()]


def events(records, name):
    return [r for r in records if r["event"] == name]


class Memory:
    """파일 대신 메모리에 두는 저장소."""

    def __init__(self, **items):
        self.items = dict(items)

    def load(self, *key):
        return self.items.get("/".join(key))

    def posting_ids(self):
        return list(self.items)


def features(in_reading=True) -> PostingFeatures:
    return PostingFeatures("100", "gpt-test", "회계", "", items=[Item("C1", "", "자격요건", "경력 3년", "", in_reading=in_reading)], input_tokens=1000, output_tokens=500)


def matched(quote=RESUME_TEXT, in_resume=True) -> ResumeMatch:
    return ResumeMatch("100", "r1", "gpt-test", [Judgment("C1", "", [quote], MATCH, in_resume)], input_tokens=2000, output_tokens=1000)


class Resumes:
    def of_posting(self, posting_id):
        return [Resume("r1", RESUME_TEXT)]


class Adapter:
    last_request_id = "req_test"


def run_server(feature_store, match_store, submission=Submission("100", "제목", READING_TEXT, "abcd1234"), fail=False):
    def extract(posting_id):
        return feature_store.load(posting_id) or features()

    def match(f, resume):
        if fail:
            raise TimeoutError("본문은 로그에 남기지 않는다")
        return match_store.load(f.posting_id, resume.resume_id) or matched()

    submissions = Memory(**{"100": submission} if submission else {})
    return captured(lambda: match_postings(["100"], submissions, feature_store, match_store, extract, match, Resumes(), Adapter(), Adapter()))


class ServerLogs(unittest.TestCase):
    def test_every_line_has_the_common_fields(self):
        for record in run_server(Memory(), Memory()):
            self.assertLessEqual({"ts", "level", "service", "trace_id", "event"}, set(record))
            self.assertEqual(record["service"], "server")

    def test_llm_call_leaves_tokens_and_cost(self):
        records = run_server(Memory(), Memory())
        calls = {r["purpose"]: r for r in events(records, "llm.called")}
        self.assertEqual(calls["extract"]["input_tokens"], 1000)
        self.assertEqual(calls["match"]["cost_usd"], 0.0024)
        self.assertEqual(calls["match"]["openai_request_id"], "req_test")
        self.assertEqual(events(records, "run.finished")[0]["llm_calls"], 2)

    def test_stored_result_is_skipped_and_costs_nothing(self):
        records = run_server(Memory(**{"100": features()}), Memory(**{"100/r1": matched()}))
        self.assertEqual([r["stage"] for r in events(records, "stage.skipped")], ["extract", "match"])
        self.assertEqual(events(records, "llm.called"), [])
        self.assertEqual(events(records, "run.finished")[0]["cost_usd"], 0)

    def test_submitted_trace_id_is_carried_through(self):
        records = run_server(Memory(), Memory())
        self.assertEqual({r["trace_id"] for r in records if "posting_id" in r}, {"abcd1234"})

    def test_missing_trace_id_gets_a_new_one(self):
        records = run_server(Memory(), Memory(), submission=Submission("100", "제목", READING_TEXT))
        self.assertRegex(events(records, "resume.matched")[0]["trace_id"], r"^[0-9a-f]{8}$")

    def test_failed_checks_leave_numbers_not_text(self):
        """지어낸 근거와 읽은 내용에 없는 조건은 번호로 남긴다. 구절과 이력서의 글자는 남기지 않는다."""
        records = run_server(Memory(**{"100": features()}), Memory(**{"100/r1": matched(SECRET_QUOTE, False)}),
                             submission=Submission("100", "제목", "조건이 없는 읽은 내용", "abcd1234"))
        self.assertEqual(events(records, "quote.not_in_resume")[0]["item_id"], "100-C1")
        self.assertEqual(events(records, "quote.not_in_resume")[0]["verdict"], MATCH)
        self.assertEqual(events(records, "item.not_in_reading")[0]["item_id"], "100-C1")
        self.assertEqual(events(records, "resume.matched")[0]["verdicts"], {"일치": 0, "비슷": 0, "다름": 1})
        whole = json.dumps(records, ensure_ascii=False)
        for text in (SECRET_QUOTE, RESUME_TEXT, "조건이 없는 읽은 내용"):
            self.assertNotIn(text, whole)

    def test_failure_leaves_the_kind_of_error_only(self):
        records = run_server(Memory(), Memory(), fail=True)
        self.assertEqual(events(records, "llm.failed")[0]["error"], "TimeoutError")
        self.assertNotIn("본문은", json.dumps(records, ensure_ascii=False))
        self.assertEqual(events(records, "run.finished")[0]["failed"], 1)


class Site:
    def __init__(self, on_request=None):
        self._on_request = on_request

    def fetch(self, posting_id):
        self._on_request(host="example.test", purpose="page", status=200, content_type="text/html", ms=1)
        return CollectedPosting(posting_id, "제목", [CollectedImage("01.png", b"")])


class Store(Memory):
    def save(self, item):
        self.items[item.posting_id] = item


class Images:
    def load(self, posting_id):
        return [("01.png", Image.new("RGB", (10, 10), "white"))]


class Reader:
    model = "gpt-test"
    last_request_id = "req_read"

    def read(self, image):
        return READING_TEXT, 800, 100


class Outbox:
    def submit(self, submission):
        self.submitted = submission


class ClientLogs(unittest.TestCase):
    def run_client(self, collected, readings, posting="100"):
        self.outbox, self.totals = Outbox(), {"calls": 0, "cost": 0.0}
        return captured(lambda: submit_posting(posting, "abcd1234", collected, readings, Images(), Reader(), self.outbox, self.totals, site_of=Site))

    def test_first_run_leaves_the_whole_trail(self):
        records = self.run_client(Store(), Store())
        self.assertEqual([r["event"] for r in records], ["http.requested", "posting.collected", "llm.called", "posting.read", "posting.submitted"])
        self.assertEqual({r["trace_id"] for r in records}, {"abcd1234"})
        self.assertEqual(self.outbox.submitted.trace_id, "abcd1234")
        self.assertEqual(self.totals["calls"], 1)
        self.assertNotIn(READING_TEXT, json.dumps(records, ensure_ascii=False))

    def test_second_run_skips_and_calls_nothing(self):
        collected, readings = Store(), Store()
        self.run_client(collected, readings)
        records = self.run_client(collected, readings)
        self.assertEqual([r["event"] for r in records], ["stage.skipped", "stage.skipped", "posting.submitted"])
        self.assertEqual(self.totals["calls"], 0)

    def test_bad_address_is_a_collect_failure(self):
        records = self.run_client(Store(), Store(), posting="https://example.test/no-number")
        self.assertEqual([(r["event"], r["level"]) for r in records], [("posting.collect_failed", "ERROR")])


if __name__ == "__main__":
    unittest.main()
