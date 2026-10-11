"""OpenAI의 모델로 직무와 그 직무의 특징을 뽑는 어댑터. 프롬프트 하나와 구조화된 출력을 쓴다."""
import json
import urllib.request
from pathlib import Path

from groupby.shared.submission import Submission
from groupby.server.extraction.domain import CONDITION_GROUPS, DUTY, KINDS, Item, PostingFeatures, Section, settle_group

PROMPT_PATH = Path(__file__).parent / "prompts" / "extract_features.md"


def _strings() -> dict:
    return {"type": "array", "items": {"type": "string"}}


def _object(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


# 출력의 순서가 생각의 순서다. 칸 → 직무 → 그 직무의 담당업무 → 그 직무의 조건.
SCHEMA = _object(
    {
        "sections": {"type": "array", "items": _object({"title": {"type": "string"}, "role": {"type": "string"}})},
        "job": {"type": "string"},
        "job_basis": {"type": "string"},
        "duties": _strings(),
        "conditions": {
            "type": "array",
            "items": _object(
                {
                    # 판단보다 생각을 먼저 쓰게 한다. 조건 → 생각 → 무엇에 관한 것인가 → 그룹.
                    "text": {"type": "string"},
                    "reason": {"type": "string"},
                    "kind": {"type": "string", "enum": list(KINDS)},
                    "group": {"type": "string", "enum": list(CONDITION_GROUPS)},
                }
            ),
        },
    }
)


class OpenAIFeatureExtractor:
    def __init__(self, api_key: str, model: str = "gpt-4.1-mini"):
        self._api_key = api_key
        self.model = model
        self._prompt = PROMPT_PATH.read_text(encoding="utf-8")

    def extract(self, submission: Submission) -> PostingFeatures:
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": self._prompt},
                {"role": "user", "content": f"[공고 제목]\n{submission.title}\n\n[공고를 읽은 내용]\n{submission.text}"},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "posting_features", "strict": True, "schema": SCHEMA},
            },
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.load(response)
        data = json.loads(result["choices"][0]["message"]["content"])
        usage = result["usage"]
        return PostingFeatures(
            posting_id=submission.posting_id,
            model=self.model,
            job=data["job"],
            job_basis=data["job_basis"],
            sections=[Section(**s) for s in data["sections"]],
            items=[
                *(
                    Item(id=f"D{i}", kind="", group=DUTY, text=text, reason="")
                    for i, text in enumerate(data["duties"], start=1)
                ),
                *(
                    Item(
                        id=f"C{i}",
                        kind=c["kind"],
                        group=settle_group(c["kind"], c["group"]),
                        text=c["text"],
                        reason=c["reason"],
                    )
                    for i, c in enumerate(data["conditions"], start=1)
                ),
            ],
            input_tokens=usage["prompt_tokens"],
            output_tokens=usage["completion_tokens"],
        )
