"""고객사 프로그램의 명령줄 진입점. 공고 주소 → 수집 → 읽기 → 넘기기."""
import argparse
import os
from pathlib import Path

from groupby.client.adapters.outbound.file_collected_store import FileCollectedStore
from groupby.client.adapters.outbound.file_image_source import FilePostingImageSource
from groupby.client.adapters.outbound.file_reading_store import FileReadingStore
from groupby.client.adapters.outbound.file_submitter import FileSubmitter
from groupby.client.adapters.outbound.openai_vision import OpenAIVisionReader
from groupby.client.adapters.outbound.saramin_http import SaraminHttpSite
from groupby.client.collecting.service import CollectPosting
from groupby.client.reading.service import ReadPosting
from groupby.shared.env import load_env
from groupby.shared.submission import Submission

# gpt-4.1-mini의 가격. 토큰 100만 개당 달러 (02_research/ocr/ocr.md 2.3).
INPUT_PRICE, OUTPUT_PRICE = 0.40, 1.60


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

    collect_posting = CollectPosting(SaraminHttpSite(), FileCollectedStore(args.data / "postings"))
    read_posting = ReadPosting(
        images=FilePostingImageSource(args.data / "postings"),
        reader=OpenAIVisionReader(os.environ.get("OPENAI_API_KEY", "")),
        store=FileReadingStore(args.data / "readings"),
    )
    submitter = FileSubmitter(args.outbox)

    for url_or_id in args.postings:
        try:
            posting = collect_posting(url_or_id)
            reading = read_posting(posting.posting_id)
            path = submitter.submit(Submission(posting.posting_id, posting.title, reading.text))
            input_tokens = sum(s.input_tokens for s in reading.slices)
            output_tokens = sum(s.output_tokens for s in reading.slices)
            cost = (input_tokens * INPUT_PRICE + output_tokens * OUTPUT_PRICE) / 1_000_000
            print(f"{posting.posting_id} {posting.title}")
            print(f"  수집: 이미지 {len(posting.images)}장")
            print(f"  읽기: 조각 {len(reading.slices)}개, {len(reading.text)}자, 약 ${cost:.4f}")
            print(f"  넘김: {path}")
        except Exception as e:
            # 공고 하나가 실패해도 다음 공고로 넘어간다 (07_api/background 2장).
            print(f"{url_or_id} 실패: {type(e).__name__}")

if __name__ == "__main__":
    main()
