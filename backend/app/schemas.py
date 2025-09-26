# backend/app/schemas.py
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class EventIn(BaseModel):
    title: str = Field(..., max_length=200)
    start: datetime
    end:   datetime
    # NEW:
    description: Optional[str] = Field(default=None, max_length=2000)
    location:    Optional[str] = Field(default=None, max_length=255)

class EventOut(EventIn):
    id: int
    model_config = {"from_attributes": True}  # ➜ Add this line to enable ORM serialization

#for responses, what fastapi will return back when event
#created or fetched
#include the id, which DB assigns automatically



    '''
# backend/app/schemas.py
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class EventIn(BaseModel):
    title: str = Field(..., max_length=200)
    start: datetime
    end:   datetime
    # NEW:
    description: Optional[str] = Field(default=None, max_length=2000)
    location:    Optional[str] = Field(default=None, max_length=255)

class EventOut(EventIn):
    id: int

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