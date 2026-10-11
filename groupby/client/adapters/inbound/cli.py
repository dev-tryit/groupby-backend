"""고객사 프로그램의 명령줄 진입점. 공고 주소 → 수집 → 읽기 → 넘기기.

표준 출력에는 로그만 낸다. 한 줄에 JSON 하나다 (11_log/log.md).
"""
import argparse
import os
import time
from pathlib import Path

from groupby.client.adapters.outbound.file_collected_store import FileCollectedStore
from groupby.client.adapters.outbound.file_image_source import FilePostingImageSource
from groupby.client.adapters.outbound.file_reading_store import FileReadingStore
from groupby.client.adapters.outbound.file_submitter import FileSubmitter
from groupby.client.adapters.outbound.openai_vision import OpenAIVisionReader
from groupby.client.adapters.outbound.saramin_http import SaraminHttpSite
from groupby.client.collecting.domain import posting_id_of
from groupby.client.collecting.service import CollectPosting
from groupby.client.reading.service import ReadPosting
from groupby.shared.env import load_env
from groupby.shared.log import cost_usd, log, new_trace_id
from groupby.shared.submission import Submission

SERVICE = "client"


class LoggedReader:
    """읽기를 부를 때마다 모델, 토큰 수, 비용, 걸린 시간을 로그로 남긴다. 읽은 글자는 남기지 않는다."""

    def __init__(self, reader, emit, totals: dict):
        self._reader = reader
        self._emit = emit
        self._totals = totals
        self.model = reader.model

    def read(self, image):
        started = time.monotonic()
        text, input_tokens, output_tokens = self._reader.read(image)
        cost = cost_usd(input_tokens, output_tokens)
        self._totals["calls"] += 1
        self._totals["cost"] += cost
        self._emit(
            "llm.called",
            purpose="read",
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=round(cost, 4),
            ms=int((time.monotonic() - started) * 1000),
            openai_request_id=getattr(self._reader, "last_request_id", None),
        )
        return text, input_tokens, output_tokens


def submit_posting(url_or_id: str, trace_id: str, collected, readings, images, reader, submitter, totals: dict, site_of=SaraminHttpSite) -> bool:
    """공고 하나를 수집하고 읽어서 넘긴다. 실패하면 이유를 로그에 남기고 False를 돌려준다."""

    def emit(event: str, level: str = "INFO", **fields) -> None:
        log(SERVICE, trace_id, event, level, **fields)

    try:
        posting_id = posting_id_of(url_or_id)
    except ValueError as e:
        emit("posting.collect_failed", "ERROR", error=type(e).__name__)
        return False

    def emit_posting(event: str, level: str = "INFO", **fields) -> None:
        emit(event, level, posting_id=posting_id, **fields)

    try:
        stored = collected.load(posting_id) is not None
        posting = CollectPosting(site_of(on_request=lambda **f: emit_posting("http.requested", **f)), collected)(posting_id)
        if stored:
            emit_posting("stage.skipped", stage="collect")
        else:
            emit_posting("posting.collected", images=len(posting.images))
    except Exception as e:
        emit_posting("posting.collect_failed", "ERROR", error=type(e).__name__)
        return False

    try:
        stored = readings.load(posting_id) is not None
        reading = ReadPosting(images, LoggedReader(reader, emit_posting, totals), readings)(posting_id)
        if stored:
            emit_posting("stage.skipped", stage="read")
        else:
            emit_posting("posting.read", slices=len(reading.slices), chars=len(reading.text))
    except Exception as e:
        emit_posting("llm.failed", "ERROR", purpose="read", error=type(e).__name__)
        return False

    submitter.submit(Submission(posting_id, posting.title, reading.text, trace_id))
    emit_posting("posting.submitted")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(prog="groupby-client", description="고객사의 컴퓨터에서 실행하는 프로그램")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--data", type=Path, default=Path("data/client"), help="고객사 쪽에 남는 데이터(이미지, 읽은 결과)")
    parser.add_argument("--outbox", type=Path, default=Path("data/submissions"), help="서비스 제공사에 넘기는 곳")
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("collect", help="공고를 수집하고 읽어서 제목과 읽은 내용을 넘긴다")
    collect.add_argument("postings", nargs="+", help="사람인 공고 주소 또는 공고 번호")
    args = parser.parse_args()
    load_env(args.env)

    collected = FileCollectedStore(args.data / "postings")
    readings = FileReadingStore(args.data / "readings")
    images = FilePostingImageSource(args.data / "postings")
    # 키가 없어도 시작한다. 읽어야 하는 공고만 실패한다.
    reader = OpenAIVisionReader(os.environ.get("OPENAI_API_KEY", ""))
    submitter = FileSubmitter(args.outbox)

    run_id = new_trace_id()
    started = time.monotonic()
    totals = {"calls": 0, "cost": 0.0}
    log(SERVICE, run_id, "run.started", postings=len(args.postings))
    # 공고 하나가 실패해도 다음 공고로 넘어간다. 실패가 있어도 0으로 끝나야 서비스 제공사 프로그램이 이어서 시작한다.
    results = [submit_posting(p, new_trace_id(), collected, readings, images, reader, submitter, totals) for p in args.postings]
    log(
        SERVICE,
        run_id,
        "run.finished",
        succeeded=sum(results),
        failed=len(results) - sum(results),
        llm_calls=totals["calls"],
        cost_usd=round(totals["cost"], 4),
        ms=int((time.monotonic() - started) * 1000),
    )


if __name__ == "__main__":
    main()
