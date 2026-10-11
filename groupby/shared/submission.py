"""고객사가 서비스 제공사에 넘기는 것. 두 프로그램 사이의 경계다.

공고의 이미지는 넘기지 않는다. 제목과 읽은 내용만 넘긴다.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Submission:
    posting_id: str
    title: str
    text: str  # 공고의 이미지를 읽은 내용 전체
    trace_id: str = ""  # 두 프로그램의 로그를 잇는 값. 공고의 내용이 아니다 (11_log/log.md 3장)
