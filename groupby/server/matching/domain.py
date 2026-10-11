"""비교의 도메인. 판정의 모양과, 근거가 이력서 안에 있는지 확인하는 규칙."""
import re
import unicodedata
from dataclasses import dataclass, field

MATCH, SIMILAR, DIFFERENT = "일치", "비슷", "다름"
VERDICTS = (MATCH, SIMILAR, DIFFERENT)


@dataclass
class Judgment:
    condition_id: str
    thinking: str  # 판정에 이른 생각. 왜 일치인지, 왜 비슷인지
    quotes: list[str]  # 근거. 이력서의 글자를 그대로 옮긴 구절들. 이력서에 적혀 있지 않으면 비어 있다
    verdict: str  # LLM이 낸 판정
    quotes_in_resume: bool = False  # 근거가 모두 이력서 안에 실제로 있는가

    @property
    def not_written(self) -> bool:
        """이력서에 적혀 있지 않아서 다름인 경우. 없는 것과 적지 않은 것을 사람이 구별해서 볼 수 있게 한다."""
        return self.verdict == DIFFERENT and not self.quotes

    @property
    def unverified(self) -> bool:
        """일치나 비슷이라고 했는데 근거가 이력서 안에 없는 경우. 이 판정은 믿지 않는다."""
        return self.verdict != DIFFERENT and not self.quotes_in_resume

    @property
    def trusted_verdict(self) -> str:
        """점수에 쓰는 판정. 근거를 확인하지 못한 판정은 다름으로 친다."""
        return DIFFERENT if self.unverified else self.verdict


@dataclass
class ResumeMatch:
    posting_id: str
    resume_id: str
    model: str
    judgments: list[Judgment] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0

    def of(self, condition_id: str) -> Judgment | None:
        return next((j for j in self.judgments if j.condition_id == condition_id), None)


def squeeze(text: str) -> str:
    """띄어쓰기, 줄바꿈, 글머리 기호(#, -, *)의 차이를 지운다. 글자가 같은지만 본다."""
    return re.sub(r"[\s#*`\-]+", "", unicodedata.normalize("NFKC", text))


def mark_quotes(judgments: list[Judgment], resume_text: str) -> None:
    """근거가 이력서 안에 글자 그대로 있는지 코드로 확인한다. LLM이 지어낸 근거를 잡는다.

    근거가 여러 개면 모두 있어야 한다. 하나라도 없으면 그 판정은 믿지 않는다.
    """
    source = squeeze(resume_text)
    for judgment in judgments:
        judgment.quotes = [q for q in judgment.quotes if squeeze(q)]
        judgment.quotes_in_resume = bool(judgment.quotes) and all(squeeze(q) in source for q in judgment.quotes)
