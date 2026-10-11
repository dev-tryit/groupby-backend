"""OpenAI의 모델로 조건과 이력서를 비교하는 어댑터. 이력서 하나에 한 번 부른다."""
import json
import urllib.request
from datetime import date
from pathlib import Path

from groupby.server.extraction.domain import CONDITION_GROUPS, DUTY, PostingFeatures
from groupby.server.matching.domain import VERDICTS, Judgment, ResumeMatch
from groupby.server.matching.ports import Resume

PROMPT_PATH = Path(__file__).parent / "prompts" / "match_resume.md"

# 판단보다 생각을 먼저 쓰게 한다. 번호 → 생각 → 근거 → 판정.
SCHEMA = {
    "type": "object",
    "properties": {
        "judgments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "condition_id": {"type": "string"},
                    "thinking": {"type": "string"},
                    "quotes": {"type": "array", "items": {"type": "string"}},
                    "verdict": {"type": "string", "enum": list(VERDICTS)},
                },
                "required": ["condition_id", "thinking", "quotes", "verdict"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["judgments"],
    "additionalProperties": False,
}


def render_input(features: PostingFeatures, resume: Resume, today: date) -> str:
    duties = "\n".join(f"- {item.text}" for item in features.of(DUTY))
    conditions = "\n".join(
        f"- {item.id} [{group}] {item.text}" for group in CONDITION_GROUPS for item in features.of(group)
    )
    return f"[오늘 날짜]\n{today.isoformat()}\n\n[직무]\n{features.job}\n\n[담당업무]\n{duties}\n\n[조건]\n{conditions}\n\n[이력서]\n{resume.text}"


class OpenAIMatcher:
    def __init__(self, api_key: str, model: str = "gpt-4.1-mini", today: date | None = None):
        self._api_key = api_key
        self.model = model
        self.last_request_id: str | None = None  # OpenAI가 응답에 준 요청 번호. 로그에 남긴다
        # "현재"까지의 기간을 셈하려면 오늘이 언제인지 알아야 한다. 모델은 오늘 날짜를 모른다.
        self._today = today or date.today()
        self._prompt = PROMPT_PATH.read_text(encoding="utf-8")

    def match(self, features: PostingFeatures, resume: Resume) -> ResumeMatch:
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": self._prompt},
                {"role": "user", "content": render_input(features, resume, self._today)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "resume_match", "strict": True, "schema": SCHEMA},
            },
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.load(response)
            self.last_request_id = response.headers.get("x-request-id")
        data = json.loads(result["choices"][0]["message"]["content"])
        usage = result["usage"]
        return ResumeMatch(
            posting_id=features.posting_id,
            resume_id=resume.resume_id,
            model=self.model,
            judgments=[Judgment(j["condition_id"], j["thinking"], j["quotes"], j["verdict"]) for j in data["judgments"]],
            input_tokens=usage["prompt_tokens"],
            output_tokens=usage["completion_tokens"],
        )
