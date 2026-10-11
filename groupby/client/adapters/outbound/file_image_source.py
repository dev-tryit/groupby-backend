"""폴더에 저장된 공고의 이미지를 읽어 오는 어댑터."""
from pathlib import Path

from PIL import Image

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


class FilePostingImageSource:
    def __init__(self, root: Path):
        self._root = root

    def load(self, posting_id: str) -> list[tuple[str, Image.Image]]:
        folder = self._root / posting_id
        paths = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
        return [(p.name, Image.open(p).convert("RGB")) for p in paths]
