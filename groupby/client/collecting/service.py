"""수집의 흐름. 공고 주소 하나를 받아 제목과 본문 이미지를 가져와 저장한다."""
from .domain import CollectedPosting, posting_id_of
from .ports import CollectedStore, PostingSite


class CollectPosting:
    def __init__(self, site: PostingSite, store: CollectedStore):
        self._site = site
        self._store = store

    def __call__(self, url_or_id: str) -> CollectedPosting:
        """가져온 것이 저장되어 있으면 다시 가져오지 않는다. 공고가 마감되어도 다시 돌릴 수 있다."""
        posting_id = posting_id_of(url_or_id)
        saved = self._store.load(posting_id)
        if saved is not None:
            return saved
        posting = self._site.fetch(posting_id)
        if not posting.images:
            raise RuntimeError(f"공고 {posting_id}에서 본문 이미지를 찾지 못했다. 이미지 공고가 아닐 수 있다.")
        self._store.save(posting)
        return posting
