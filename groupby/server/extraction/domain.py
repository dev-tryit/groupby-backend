"""특징 추출의 도메인. 직무와 그 직무의 담당업무, 자격요건, 우대사항, 참고사항."""
import re
import unicodedata
from dataclasses import dataclass, field

# 직무에서 뽑는 네 가지. 자격요건과 우대사항은 점수에 넣는다.
# 담당업무와 참고사항은 점수에 넣지 않고 보여 주기만 한다.
DUTY = "담당업무"
CONDITION_GROUPS = ("자격요건", "우대사항", "참고사항")
GROUPS = (DUTY, *CONDITION_GROUPS)
SCORED_GROUPS = ("자격요건", "우대사항")
# 조건이 무엇에 관한 것인가. 개인 사정은 공고가 어느 칸에 적었든 참고사항이다.
KINDS = ("일과 배움으로 갖춘 것", "개인 사정")
PERSONAL = "개인 사정"


@dataclass
class Item:
    """직무에서 뽑은 항목 하나. 담당업무이거나 조건이다."""

    id: str
    kind: str
    group: str
    text: str  # 공고의 글자를 그대로 옮긴 것이다
    reason: str  # 이 그룹으로 본 생각. 결과물이 아니라 판단의 과정이다
    in_reading: bool = False  # 조건이 읽은 글자 안에 실제로 있는가


@dataclass
class Section:
    title: str
    role: str  # 이 칸이 무엇을 적은 칸인지


@dataclass
class PostingFeatures:
    posting_id: str
    model: str
    job: str  # 어떤 직무를 뽑는가. 필수와 우대를 가르는 기준이다
    job_basis: str  # 직무를 공고의 어디에서 얻었는가
    sections: list[Section] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0

    def of(self, group: str) -> list[Item]:
        return [item for item in self.items if item.group == group]


def settle_group(kind: str, group: str) -> str:
    """개인 사정(병역, 거주지, 가족, 기르는 동물 등)은 점수에 넣지 않는다. 그룹을 참고사항으로 고정한다."""
    return "참고사항" if kind == PERSONAL else group


def squeeze(text: str) -> str:
    """띄어쓰기와 줄바꿈, 유니코드의 표기 차이(눈으로 같은 글자의 다른 코드)를 지운다. 글자가 같은지만 본다."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def mark_in_reading(items: list[Item], reading_text: str) -> None:
    """뽑은 항목이 읽은 글자 안에 있는지 코드로 확인한다. LLM이 지어내거나 고쳐 쓴 것을 잡는다."""
    source = squeeze(reading_text)
    for item in items:
        text = squeeze(item.text)
        item.in_reading = bool(text) and text in source
