"""서비스 제공사 프로그램의 명령줄 진입점. 고객사가 넘긴 것 → 특징 추출."""
import argparse
import os
from pathlib import Path

from groupby.server.adapters.outbound.file_feature_store import FileFeatureStore
from groupby.server.adapters.outbound.file_submission_source import FileSubmissionSource
from groupby.server.adapters.outbound.openai_feature_extractor import OpenAIFeatureExtractor
from groupby.server.extraction.domain import GROUPS
from groupby.server.extraction.service import ExtractFeatures
from groupby.shared.env import load_env

# gpt-4.1-mini의 가격. 토큰 100만 개당 달러 (02_research/ocr/ocr.md 2.3).
INPUT_PRICE, OUTPUT_PRICE = 0.40, 1.60


def main() -> None:
    parser = argparse.ArgumentParser(prog="groupby-server", description="서비스 제공사의 프로그램")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--inbox", type=Path, default=Path("data/submissions"), help="고객사가 넘긴 것이 있는 곳")
    parser.add_argument("--data", type=Path, default=Path("data/server"), help="서비스 제공사 쪽에 남는 데이터")
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract", help="넘겨받은 제목과 읽은 내용에서 직무와 그 직무의 특징을 뽑는다")
    extract.add_argument("posting_ids", nargs="*", help="공고 번호. 비우면 넘겨받은 것 전부")
    args = parser.parse_args()
    load_env(args.env)

    submissions = FileSubmissionSource(args.inbox)
    extract_features = ExtractFeatures(
        submissions=submissions,
        extractor=OpenAIFeatureExtractor(os.environ["OPENAI_API_KEY"]),
        store=FileFeatureStore(args.data / "features"),
    )
    for posting_id in args.posting_ids or submissions.posting_ids():
        result = extract_features(posting_id)
        cost = (result.input_tokens * INPUT_PRICE + result.output_tokens * OUTPUT_PRICE) / 1_000_000
        print(f"{result.posting_id} 직무: {result.job} (약 ${cost:.4f})")
        for group in GROUPS:
            print(f"  {group}")
            for item in result.of(group):
                mark = "" if item.in_reading else "  ← 읽은 내용에 없음"
                print(f"    {item.id} {item.text}{mark}")


if __name__ == "__main__":
    main()
