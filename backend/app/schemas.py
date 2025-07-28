from datetime import datetime
#^needed for start and end
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
    model_config = {"from_attributes": True}


    '''

    “Hey FastAPI, when someone calls my API, I want to validate and return JSON that looks like this:”
    {
  "id": 1,
  "title": "Dentist",
  "start": "2025-08-01T09:00:00",
  "end": "2025-08-01T10:00:00"
}


    defines API input/output structure
    translator for outside world, what data allowed in internal db
    as well as protocls for what is sent out
    API models built using Pydantic
    '''