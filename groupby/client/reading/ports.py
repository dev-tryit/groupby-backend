"""읽기가 바깥에 기대는 것. 읽기의 흐름은 이 포트만 알고, 구현은 어댑터가 맡는다."""
from typing import Protocol

from PIL import Image

from .domain import PostingReading


class PostingImageSource(Protocol):
    def load(self, posting_id: str) -> list[tuple[str, Image.Image]]:
        """공고의 본문 이미지를 (이름, 이미지)의 목록으로 순서대로 돌려준다."""


class VisionReader(Protocol):
    model: str

    def read(self, image: Image.Image) -> tuple[str, int, int]:
        """이미지 한 조각을 읽어 (글자, 입력 토큰, 출력 토큰)을 돌려준다."""


class ReadingStore(Protocol):
    def load(self, posting_id: str) -> PostingReading | None: ...

    def save(self, reading: PostingReading) -> None: ...
