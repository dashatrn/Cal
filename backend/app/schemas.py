from __future__ import annotations
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class EventIn(BaseModel):
    title: str
    start: datetime  # UTC ISO string in/out
    end:   datetime
    description: Optional[str] = None
    location:    Optional[str] = None

class EventOut(EventIn):
    id: int
    # allow creating Pydantic models from ORM rows
    model_config = ConfigDict(from_attributes=True)



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