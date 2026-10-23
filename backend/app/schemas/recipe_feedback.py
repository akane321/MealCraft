from datetime import datetime

from pydantic import BaseModel

from app.schemas.catalog_tags import FeedbackKind
from app.schemas.display import ShownTitle


class RecipeFeedbackUpdate(BaseModel):
    kind: FeedbackKind


class RecipeFeedbackResponse(BaseModel):
    recipe_id: int
    kind: FeedbackKind


class RecipeFeedbackItem(BaseModel):
    recipe_id: int
    slug: str
    title: ShownTitle
    kind: FeedbackKind
    created_at: datetime


class RecipeFeedbackCollectionResponse(BaseModel):
    items: list[RecipeFeedbackItem]
