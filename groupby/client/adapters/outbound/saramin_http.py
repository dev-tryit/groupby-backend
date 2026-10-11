"""사람인에서 공고의 제목과 본문 이미지를 HTTP 요청으로 가져오는 어댑터.

공식 Open API를 쓰지 않는다. 브라우저도 쓰지 않는다 (02_research/crawling/crawling.md 1장).
"""
import html
import re
import time
import urllib.request

from groupby.client.collecting.domain import CollectedImage, CollectedPosting, clean_title, is_body_image

BASE = "https://www.saramin.co.kr/zf_user/jobs/relay"
# 정체를 밝힌 User-Agent. 헤더가 없으면 거절된다.
USER_AGENT = "groupby-assignment/0.1 (hiring assignment; single posting fetch)"
PAUSE_SECONDS = 2


class SaraminHttpSite:
    def _get(self, url: str) -> tuple[bytes, str]:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
        time.sleep(PAUSE_SECONDS)
        return body, content_type

    def fetch(self, posting_id: str) -> CollectedPosting:
        outer, _ = self._get(f"{BASE}/view?rec_idx={posting_id}")
        found = re.search(r"<title>(.*?)</title>", outer.decode("utf-8", errors="ignore"), re.S)
        title = clean_title(html.unescape(found.group(1))) if found else ""

        detail, _ = self._get(f"{BASE}/view-detail?rec_idx={posting_id}&rec_seq=0")
        sources = re.findall(r'<img[^>]*\ssrc="([^"]+)"', detail.decode("utf-8", errors="ignore"))

        posting = CollectedPosting(posting_id=posting_id, title=title)
        for src in sources:
            if not is_body_image(src):
                continue
            url = "https:" + src if src.startswith("//") else src
            content, content_type = self._get(url)
            # 거절할 때도 상태가 200으로 온다. 이미지인지는 Content-Type으로 확인한다.
            if not content_type.startswith("image/"):
                raise RuntimeError(f"이미지가 아닌 응답을 받았다: {url} ({content_type})")
            suffix = url.rsplit(".", 1)[-1].lower().split("?")[0]
            posting.images.append(CollectedImage(f"{len(posting.images) + 1:02d}.{suffix}", content))
        return posting
