"""OpenAI의 비전 모델로 이미지를 읽는 어댑터."""
import base64
import io
import json
import urllib.request

from PIL import Image

# 조사에서 쓴 지시와 같다 (02_research/ocr/ocr.md 11.11).
INSTRUCTION = (
    "이 이미지는 채용 공고의 일부다. 이미지에 보이는 글자를 위에서 아래로 보이는 그대로 모두 받아써라. "
    "고치거나 요약하거나 설명을 덧붙이지 마라. 읽을 수 없는 글자는 쓰지 마라. "
    "표는 한 줄에 칸을 나란히 적어라. 글자가 없으면 빈 문자열을 내라."
)


class OpenAIVisionReader:
    def __init__(self, api_key: str, model: str = "gpt-4.1-mini"):
        self._api_key = api_key
        self.model = model
        self.last_request_id: str | None = None  # OpenAI가 응답에 준 요청 번호. 로그에 남긴다

    def read(self, image: Image.Image) -> tuple[str, int, int]:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        data_url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": INSTRUCTION},
                        {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
                    ],
                }
            ],
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)
            self.last_request_id = response.headers.get("x-request-id")
        usage = result["usage"]
        text = result["choices"][0]["message"]["content"] or ""
        return text.strip(), usage["prompt_tokens"], usage["completion_tokens"]
