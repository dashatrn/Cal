# app/main.py

from datetime import datetime
from typing import List

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from sqlalchemy.exc import IntegrityError
'''
db: builds engine and gives access to db
models: defines the structure of event table
schemas: defines shapes of data coming in/out
'''
# ── local modules ─────────────────────────────────────────────
from .db import Base, engine, get_db
from .models import Event
from .schemas import EventIn, EventOut
# ───────────────────────────────────────

#new code
# ── imports – add at the top ──────────────────────────────────────────
from fastapi import UploadFile, File
from fastapi.staticfiles import StaticFiles
import uuid
import tempfile, subprocess, re, json
from pathlib import Path
from dateutil import parser as dtparse        # pip install python-dateutil
import pytesseract                            # pip install pytesseract pillow
from PIL import Image                         # (Pillow)
# ──────────────────────────────────────────────────────────────────────
app = FastAPI(title="Cal API")


# ── helper to run pytesseract on bytes ────────────────────────────────
def ocr_to_text(data: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(data)
    try:
        text = pytesseract.image_to_string(Image.open(tmp.name))
        return text
    finally:
        Path(tmp.name).unlink(missing_ok=True)


# ── naive parser: find first YYYY-MM-DD and first time range ──────────
_date_re = re.compile(
    r"\b(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\w+\s+\d{1,2},\s*\d{4})\b",
    re.IGNORECASE,
)

_time_re = re.compile(
    r"(\d{1,2}[:]\d{2}\s*(?:AM|PM|am|pm)?)\s*[-–—~to]+\s*(\d{1,2}[:]\d{2}\s*(?:AM|PM|am|pm)?)"
)

def extract_event_fields(text: str) -> dict[str, str] | None:
    date_m  = _date_re.search(text)
    time_m  = _time_re.search(text)
    if not (date_m and time_m):
        return None
    date_iso = dtparse.parse(date_m.group(1)).date().isoformat()
    start_iso = dtparse.parse(f"{date_iso} {time_m.group(1)}").isoformat()
    end_iso   = dtparse.parse(f"{date_iso} {time_m.group(2)}").isoformat()

    # Title → first non-empty line that isn’t the date/time line
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    try:
        # Prefer the line after the date/time block
        date_idx = next(i for i, l in enumerate(lines) if _date_re.search(l))
        title = lines[date_idx + 2]  # date line, time line, then title
    except Exception:
        title = lines[0] if lines else "Untitled"
    title = title[:200]

    return {"title": title, "start": start_iso, "end": end_iso}

UPLOAD_DIR = Path(__file__).resolve().parents[1] / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# ── new route ---------------------------------------------------------

@app.post("/uploads", status_code=201)
async def upload_file(file: UploadFile = File(...)):
    raw = await file.read()

    # 1. save original image
    ext = (Path(file.filename).suffix or ".png").lower()
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / filename
    dest.write_bytes(raw)

    text = ocr_to_text(raw)
    print("──── OCR TEXT ────")
    print(text)
    print("──────────────────")

    extracted = extract_event_fields(text)
    if not extracted:
        raise HTTPException(status_code=422, detail="Could not parse date/time")

    # 2. add URL for frontend
    extracted["thumb"] = f"/uploads/{filename}"
    return extracted

#end new code


# Creates API

from os import getenv

origins = [
    getenv("FRONTEND_ORIGIN", "http://localhost:5173"),
]

codespaces_origin = getenv("CODESPACES_FRONTEND")
if codespaces_origin:
    origins.append(codespaces_origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # dev-only; lock down later
    allow_methods=["*"],
    allow_headers=["*"],
)



# runs when app starts and creats table if it doesn't existyet
'''Base.metadata.create_all(...) scans all your SQLAlchemy models (like Event) and 
creates the actual table in the SQLite database — if it doesn't already exist.
'''

@app.on_event("startup")
def init_db() -> None:
    Base.metadata.create_all(bind=engine)

#simple check to confirm server running
@app.get("/health")
def health_check():
    return {"status": "ok"}
@app.get("/")
def read_root():
    return {"message": "FastAPI backend is running."}


#https://silver-goldfish-44r7x5x9qg5255jv-8000.app.github.dev/health



@app.get("/events", response_model=list[EventOut])
def list_events(db: Session = Depends(get_db)):
    return db.scalars(select(Event)).all()



'''runs when someone sends a POST to /events with JSON body
JSON must match shape of EventIn
data:Event in means FastAPI will validate with Pydantic
data.model()dump turns it into a dictionary. '''


@app.post("/events", response_model=EventOut, status_code=201)
def create_event(data: EventIn, db: Session = Depends(get_db)):
    #creeates SQLAlchemy object
    payload = data.model_dump()

    # --- conflict check  ------------------------
    overlap_stmt = select(Event).where(
    and_(Event.start < payload["end"], Event.end > payload["start"])
    )
    conflict = db.scalars(overlap_stmt).first()
    if conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Time overlaps with another event.",
                "conflicts": [
                    {
                        "id": conflict.id,
                        "title": conflict.title,
                        "start": conflict.start.isoformat(),
                        "end": conflict.end.isoformat(),
                    }
                ],
            },
        )

    # no conflict → create
    evt = Event(**payload)
    db.add(evt)
  

    #saves object to SQLite .db file
    db.commit()

    # updates evt.id with real DB generated ID
    db.refresh(evt)

    #event returned with new id
    return evt

@app.put("/events/{event_id}", response_model=EventOut)
def update_event(event_id: int, payload: EventIn, db: Session = Depends(get_db)):
    overlap_stmt = select(Event).where(
        and_(Event.id != event_id, Event.start < payload.end, Event.end > payload.start)
    )
    conflict = db.scalars(overlap_stmt).first()
    if conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Time overlaps with another event.",
                "conflicts": [
                    {
                        "id": conflict.id,
                        "title": conflict.title,
                        "start": conflict.start.isoformat(),
                        "end": conflict.end.isoformat(),
                    }
                ],
            },
        )

    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    for field, value in payload.model_dump().items():
        setattr(event, field, value)

    db.commit()
    db.refresh(event)
    return event

# ------------------------------------------------------------
# 7) Delete an event
# ------------------------------------------------------------
@app.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: int, db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    db.delete(event)
    db.commit()

from pydantic import BaseModel

class ParseIn(BaseModel):
    prompt: str

@app.post("/parse")
def parse_prompt(body: ParseIn):
    """
    Reuse the OCR parser for free text. Returns partial (title/start/end).
    Frontend shows a live preview and can override.
    """
    text = (body.prompt or "").strip()
    if not text:
        return {}
    extracted = extract_event_fields(text)
    return extracted or {}


'''
| Concept                    | What It Does                                                                                                        |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `FastAPI()`                | Creates the app — API brain.                                                                           |
| `@app.on_event("startup")` | Runs once when the server starts. builds the `events` table using `Base.metadata`.                          |
| `@app.get("/health")`      | A simple check to make sure the API is alive and running. Returns `{"status": "ok"}`.                               |
| `@app.get("/events")`      | Responds to GET requests from the frontend. Grabs all `Event` rows from the database and sends them back as JSON.   |
| `@app.post("/events")`     | Responds to POST requests. Takes in a JSON event, validates it, adds it to the database, and returns it with an ID. |
| `Depends(get_db)`          | Tells FastAPI: “Give this route a fresh database connection, and close it afterward.”                               |
| `response_model=...`       | Makes sure your API returns clean, well-shaped JSON that matches your schema (`EventOut`).                          |

'''




'''
backend route, sits on server waiting for GET request to /events. request comes from React frontend. 
When react code runs, send get request here.
Receving get request, sends from database. 
response_model = list[EventOUT] means return value shuold be list EventOut objects, defined by schemas.oy
db: Session = Depends(get_db) means FASTAPI will run get_db() and give result to this func as db
select(Event) = Give all rows from events table, like writing SELECT * FROM events in SQL
db.scalars(...).all() - Execute that query, return that into a Python list of event objects
FastAPI autoconverst into JSON
sends back to frontend
events are stored in SQLite database file on server


[
  {
    "id": 1,
    "title": "Dentist",
    "start": "2025-08-01T09:00:00",
    "end": "2025-08-01T10:00:00"
  },
  ...
]


The website requests the events, 
events live in database
backend is middle layer speaks to db and internet

React code runs and sends
fetch("https://your-url-8000.app.github.dev/events")

'''


''' 
import Fast API to create web routes (GET/POST)
Depends: handles dependency injection, auto plugging in database when necessary
Get a database session for each request
select from database table, makes queries like SELECT * FROM events
in a clean way
'''