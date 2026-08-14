from __future__ import annotations

from abc import ABC, abstractmethod

from app.config import FeedDefinition
from app.schemas import SourceItemData


class SourceAdapter(ABC):
    @abstractmethod
    async def fetch(self, source: FeedDefinition) -> list[SourceItemData]:
        raise NotImplementedError
