from datetime import datetime
from pydantic import BaseModel, Field


# defines what data comes in an out of api
#for requests, when someone send post to add a new event
class EventIn(BaseModel):
    title: str = Field(..., max_length=200)
    start: datetime
    end:   datetime

#for responses, what fastapi will return back when event
#created or fetched
#include the id, which DB assigns automatically

class EventOut(EventIn):
    id: int