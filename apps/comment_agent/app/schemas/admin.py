from pydantic import BaseModel

from app.schemas.review import AIReplyRead, ReviewQueueRead
from app.schemas.task import ReplyTaskRead


class TaskDetailRead(BaseModel):
    task: ReplyTaskRead
    replies: list[AIReplyRead]
    reviews: list[ReviewQueueRead]
