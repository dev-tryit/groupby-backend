"""서비스 제공사 프로그램의 명령줄 진입점. 고객사가 넘긴 것 → 특징 추출 → 비교 → 점수와 랭킹."""
import argparse
import json
import os
import time
from pathlib import Path

from groupby.server.adapters.outbound.file_feature_store import FileFeatureStore
from groupby.server.adapters.inbound.http import serve
from groupby.server.adapters.outbound.file_match_store import FileMatchStore
from groupby.server.adapters.outbound.file_posting_catalog import FilePostingCatalog
from groupby.server.adapters.outbound.file_resume_source import FileResumeSource
from groupby.server.adapters.outbound.file_submission_source import FileSubmissionSource
from groupby.server.adapters.outbound.openai_feature_extractor import OpenAIFeatureExtractor
from groupby.server.adapters.outbound.openai_matcher import OpenAIMatcher
from groupby.server.extraction.domain import CONDITION_GROUPS, GROUPS, PostingFeatures, mark_in_reading
from groupby.server.extraction.service import ExtractFeatures
from groupby.server.matching.domain import VERDICTS, ResumeMatch
from groupby.server.matching.service import MatchResume
from groupby.server.scoring.domain import Ranked, rank, score_resume
from groupby.server.viewing.service import ViewResults
from groupby.shared.env import load_env
from groupby.shared.log import cost_usd, log, new_trace_id, trace_id_or_new

def print_features(result: PostingFeatures) -> None:
    print(f"{result.posting_id} 직무: {result.job}")
    for group in GROUPS:
        print(f"  {group}")
        for item in result.of(group):
            mark = "" if item.in_reading else "  ← 읽은 내용에 없음"
            print(f"    {item.id} {item.text}{mark}")


def mark_of(match: ResumeMatch, condition_id: str) -> tuple[str, str]:
    """화면에 보여 줄 판정과 근거."""
    judgment = match.of(condition_id)
    if judgment is None:
        return "다름", "판정을 받지 못함"
    if judgment.unverified:
        return "다름", f"근거를 확인하지 못함 (모델의 판정: {judgment.verdict})"
    if judgment.not_written:
        return "다름", "이력서에 적혀 있지 않음"
    return judgment.verdict, " / ".join(f"\"{q}\"" for q in judgment.quotes)


def print_ranking(features: PostingFeatures, ranking: list[Ranked], matches: dict[str, ResumeMatch]) -> None:
    print(f"\n=== {features.posting_id} {features.job} 랭킹 ===")
    for entry in ranking:
        s = entry.score
        preferred = f", 우대사항 {s.preferred.matched}/{s.preferred.count}" if s.preferred.count else ""
        print(f"{entry.rank}위  {s.rounded:>3}점  {s.resume_id}  (자격요건 {s.required.matched}/{s.required.count} 일치{preferred})")
    for entry in ranking:
        s = entry.score
        match = matches[s.resume_id]
        print(f"\n[{s.resume_id}] {s.rounded}점")
        for group in CONDITION_GROUPS:
            for item in features.of(group):
                verdict, evidence = mark_of(match, item.id)
                points = f"{s.points_by_condition[item.id]}점" if item.id in s.points_by_condition else "점수 없음"
                print(f"  {item.id} [{group}] {item.text}")
                print(f"      {verdict} ({points}) · 근거: {evidence}")


def result_json(features: PostingFeatures, ranking: list[Ranked], matches: dict[str, ResumeMatch]) -> dict:
    return {
        "posting_id": features.posting_id,
        "job": features.job,
        "items": [{"id": i.id, "group": i.group, "text": i.text} for i in features.items],
        "ranking": [
            {
                "rank": entry.rank,
                "resume_id": entry.score.resume_id,
                "score": entry.score.rounded,
                "required": f"{entry.score.required.points}/{entry.score.required.full}",
                "preferred": f"{entry.score.preferred.points}/{entry.score.preferred.full}",
                "judgments": [
                    {
                        "condition_id": item.id,
                        "group": item.group,
                        "verdict": mark_of(matches[entry.score.resume_id], item.id)[0],
                        "evidence": mark_of(matches[entry.score.resume_id], item.id)[1],
                        "thinking": getattr(matches[entry.score.resume_id].of(item.id), "thinking", ""),
                        "points": entry.score.points_by_condition.get(item.id),
                    }
                    for group in CONDITION_GROUPS
                    for item in features.of(group)
                ],
            }
            for entry in ranking
        ],
    }


def match_postings(posting_ids, submissions, feature_store, match_store, extract_features, match_resume, resumes, extractor, matcher) -> None:
    """넘겨받은 공고마다 특징 추출과 비교를 하고, 한 일을 로그로 남긴다 (11_log/log.md).

    저장된 것이 있으면 LLM을 부르지 않는다. 하나가 실패해도 다음으로 넘어간다.
    로그에는 번호와 수만 남긴다. 이력서의 글자, 근거의 구절, 읽은 내용은 남기지 않는다.
    """
    run_id = new_trace_id()
    started = time.monotonic()
    totals = {"done": 0, "failed": 0, "calls": 0, "cost": 0.0}
    log("server", run_id, "run.started", postings=len(posting_ids))

    def called(emit, purpose: str, result, adapter, since: float, **fields) -> None:
        cost = cost_usd(result.input_tokens, result.output_tokens)
        totals["calls"] += 1
        totals["cost"] += cost
        emit(
            "llm.called",
            purpose=purpose,
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost_usd=round(cost, 4),
            ms=int((time.monotonic() - since) * 1000),
            openai_request_id=getattr(adapter, "last_request_id", None),
            **fields,
        )

    for posting_id in posting_ids:
        try:
            submission = submissions.load(posting_id)
        except Exception:
            submission = None
        # 고객사 프로그램이 넘긴 값을 이어 쓴다. 없으면(앞의 실행에서 넘긴 것) 하나 만든다.
        trace_id = trace_id_or_new(submission.trace_id if submission else None)

        def emit(event: str, level: str = "INFO", **fields) -> None:
            log("server", trace_id, event, level, posting_id=posting_id, **fields)

        stored = feature_store.load(posting_id) is not None
        since = time.monotonic()
        try:
            features = extract_features(posting_id)
        except Exception as e:
            totals["failed"] += 1
            emit("llm.failed", "ERROR", purpose="extract", error=type(e).__name__)
            continue
        if stored:
            emit("stage.skipped", stage="extract")
        else:
            called(emit, "extract", features, extractor, since)
            emit("features.extracted", groups={group: len(features.of(group)) for group in GROUPS})
        if submission:
            mark_in_reading(features.items, submission.text)
        for item in features.items:
            if not item.in_reading:
                emit("item.not_in_reading", "WARN", item_id=f"{posting_id}-{item.id}")

        for resume in resumes.of_posting(posting_id):
            stored = match_store.load(posting_id, resume.resume_id) is not None
            since = time.monotonic()
            try:
                match = match_resume(features, resume)
            except Exception as e:
                totals["failed"] += 1
                emit("llm.failed", "ERROR", resume_id=resume.resume_id, purpose="match", error=type(e).__name__)
                continue
            if stored:
                emit("stage.skipped", resume_id=resume.resume_id, stage="match")
            else:
                called(emit, "match", match, matcher, since, resume_id=resume.resume_id)
            for judgment in match.judgments:
                if judgment.quotes and not judgment.quotes_in_resume:
                    emit("quote.not_in_resume", "WARN", resume_id=resume.resume_id, item_id=f"{posting_id}-{judgment.condition_id}", verdict=judgment.verdict)
            verdicts = {verdict: sum(j.trusted_verdict == verdict for j in match.judgments) for verdict in VERDICTS}
            emit("resume.matched", resume_id=resume.resume_id, verdicts=verdicts)
            totals["done"] += 1

    log(
        "server",
        run_id,
        "run.finished",
        succeeded=totals["done"],
        failed=totals["failed"],
        llm_calls=totals["calls"],
        cost_usd=round(totals["cost"], 4),
        ms=int((time.monotonic() - started) * 1000),
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="groupby-server", description="서비스 제공사의 프로그램")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--inbox", type=Path, default=Path("data/submissions"), help="고객사가 넘긴 것이 있는 곳")
    parser.add_argument("--data", type=Path, default=Path("data/server"), help="서비스 제공사 쪽에 남는 데이터")
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract", help="넘겨받은 제목과 읽은 내용에서 직무와 그 직무의 특징을 뽑는다")
    extract.add_argument("posting_ids", nargs="*", help="공고 번호. 비우면 넘겨받은 것 전부")
    ranker = commands.add_parser("rank", help="이력서들을 조건과 비교해 점수와 랭킹과 근거를 낸다")
    ranker.add_argument("posting_ids", nargs="*", help="공고 번호. 비우면 넘겨받은 것 전부")
    ranker.add_argument("--resumes", type=Path, required=True, help="공고 번호별 이력서 폴더가 있는 폴더")
    server = commands.add_parser("serve", help="넘겨받은 공고를 비교한 뒤 화면과 API를 연다")
    server.add_argument("--resumes", type=Path, required=True, help="공고 번호별 이력서 폴더가 있는 폴더")
    server.add_argument("--static", type=Path, default=None, help="화면의 정적 파일이 있는 폴더")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    load_env(args.env)

    # 키가 없어도 저장된 결과는 보여 준다. LLM을 불러야 하는 단계만 실패한다.
    api_key = os.environ.get("OPENAI_API_KEY", "")
    submissions = FileSubmissionSource(args.inbox)
    extractor = OpenAIFeatureExtractor(api_key)
    feature_store = FileFeatureStore(args.data / "features")
    extract_features = ExtractFeatures(submissions, extractor, feature_store)
    posting_ids = getattr(args, "posting_ids", None) or submissions.posting_ids()

    if args.command == "extract":
        for posting_id in posting_ids:
            print_features(extract_features(posting_id))
        return

    match_store = FileMatchStore(args.data / "matches")
    matcher = OpenAIMatcher(api_key)
    match_resume = MatchResume(matcher, match_store)
    resumes = FileResumeSource(args.resumes)

    if args.command == "serve":
        match_postings(posting_ids, submissions, feature_store, match_store, extract_features, match_resume, resumes, extractor, matcher)
        catalog = FilePostingCatalog(args.data / "features", args.inbox)
        view = ViewResults(catalog, feature_store, match_store, resumes)
        serve(view, args.static, args.host, args.port)
        return

    spent = 0.0
    for posting_id in posting_ids:
        features = extract_features(posting_id)
        matches = {r.resume_id: match_resume(features, r) for r in resumes.of_posting(posting_id)}
        ranking = rank([score_resume(features, m) for m in matches.values()])
        print_ranking(features, ranking, matches)
        out = args.data / "results" / f"{posting_id}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result_json(features, ranking, matches), ensure_ascii=False, indent=2), encoding="utf-8")
        spent += sum(cost_usd(m.input_tokens, m.output_tokens) for m in matches.values())
    print(f"\n비교에 쓴 토큰의 비용: 약 ${spent:.4f} (저장된 결과를 다시 쓴 경우에도 처음 만들 때의 비용이다)")


if __name__ == "__main__":
    main()
