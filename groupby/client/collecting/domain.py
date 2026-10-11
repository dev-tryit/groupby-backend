"""수집의 도메인. 공고 주소에서 공고 번호를 얻는 규칙과, 본문 이미지를 가려내는 규칙."""
import re
from dataclasses import dataclass, field

# 본문이 아닌 그림. 템플릿의 머리 그림, 워터마크, 아이콘이다 (02_research/crawling/crawling.md 4장).
DECORATION_HOSTS = ("static.saraminimage.co.kr",)
DECORATION_WORDS = ("watermark", "icon", "blank.")


@dataclass
class CollectedImage:
    name: str
    content: bytes


@dataclass
class CollectedPosting:
    posting_id: str
    title: str
    images: list[CollectedImage] = field(default_factory=list)


def posting_id_of(url_or_id: str) -> str:
    """공고 주소 또는 공고 번호에서 공고 번호를 얻는다."""
    if url_or_id.isdigit():
        return url_or_id
    found = re.search(r"rec_idx=(\d+)", url_or_id)
    if not found:
        raise ValueError(f"공고 주소에서 공고 번호(rec_idx)를 찾지 못했다: {url_or_id}")
    return found.group(1)


def is_body_image(src: str) -> bool:
    lowered = src.lower()
    if any(host in lowered for host in DECORATION_HOSTS):
        return False
    return not any(word in lowered for word in DECORATION_WORDS)


def clean_title(raw: str) -> str:
    """페이지 제목에서 사이트 이름을 뗀다."""
    return re.sub(r"\s*-\s*사람인\s*$", "", raw).strip()
