"""읽기의 도메인. 이미지를 어디서 자를지와 읽은 결과의 모양을 정한다."""
from dataclasses import dataclass, field

import numpy as np

# 조각의 높이. 조사에서 이 높이로 잘라 쟀다 (02_research/ocr/ocr.md 11.1).
SLICE_HEIGHT = 1400
# 자를 자리를 찾는 범위. 목표 높이에서 위아래로 이만큼 안에서 글자가 없는 줄을 찾는다.
SEARCH_RANGE = 200


@dataclass(frozen=True)
class SliceBox:
    top: int
    bottom: int


@dataclass
class SliceReading:
    image: str
    index: int
    top: int
    bottom: int
    text: str
    input_tokens: int
    output_tokens: int


@dataclass
class PostingReading:
    posting_id: str
    model: str
    slices: list[SliceReading] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(s.text for s in self.slices)


def plan_slices(gray: np.ndarray, slice_height: int = SLICE_HEIGHT, search_range: int = SEARCH_RANGE) -> list[SliceBox]:
    """세로로 긴 이미지를 자를 자리를 정한다.

    글자가 있는 줄을 가로지르면 그 줄을 읽지 못한다. 그래서 목표 높이 근처에서
    밝기가 가장 고른 줄(글자가 없는 줄)을 찾아 거기서 자른다.
    """
    height = gray.shape[0]
    row_spread = gray.std(axis=1)
    boxes: list[SliceBox] = []
    top = 0
    while height - top > slice_height + search_range:
        target = top + slice_height
        low, high = target - search_range, target + search_range
        cut = low + int(np.argmin(row_spread[low:high]))
        boxes.append(SliceBox(top, cut))
        top = cut
    boxes.append(SliceBox(top, height))
    return boxes
