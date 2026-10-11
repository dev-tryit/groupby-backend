"""읽기의 흐름. 공고의 이미지들을 조각내어 읽고 결과를 저장한다."""
import numpy as np

from .domain import PostingReading, SliceReading, plan_slices
from .ports import PostingImageSource, ReadingStore, VisionReader


class ReadPosting:
    def __init__(self, images: PostingImageSource, reader: VisionReader, store: ReadingStore):
        self._images = images
        self._reader = reader
        self._store = store

    def __call__(self, posting_id: str) -> PostingReading:
        """읽은 결과가 저장되어 있으면 다시 읽지 않는다. 읽을 때마다 결과가 달라지는 것과 비용을 막는다."""
        saved = self._store.load(posting_id)
        if saved is not None:
            return saved

        reading = PostingReading(posting_id=posting_id, model=self._reader.model)
        for name, image in self._images.load(posting_id):
            gray = np.asarray(image.convert("L"), dtype=np.float32)
            for index, box in enumerate(plan_slices(gray)):
                piece = image.crop((0, box.top, image.width, box.bottom))
                text, input_tokens, output_tokens = self._reader.read(piece)
                reading.slices.append(
                    SliceReading(name, index, box.top, box.bottom, text, input_tokens, output_tokens)
                )
        self._store.save(reading)
        return reading
