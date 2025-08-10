# app/main.py
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from pathlib import Path
import uuid, tempfile, re
from dateutil import parser as dtparse
import pytesseract
from PIL import Image

from .db import Base, engine, get_db
from .models import Event
from .schemas import EventIn, EventOut

app = FastAPI(title="Cal API")

# ───────────────── OCR helpers ─────────────────
def ocr_to_text(data: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(data)
    try:
        text = pytesseract.image_to_string(Image.open(tmp.name))
        return text
    finally:
        Path(tmp.name).unlink(missing_ok=True)

_date_re = re.compile(
    r"\b(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\w+\s+\d{1,2},\s*\d{4})\b",
    re.IGNORECASE,
)
_time_re = re.compile(
    r"(\d{1,2}(:\d{2})?\s*(?:AM|PM|am|pm)?)\s*(?:-|–|—|to)\s*(\d{1,2}(:\d{2})?\s*(?:AM|PM|am|pm)?)"
)

def extract_event_fields(text: str) -> Optional[dict]:
    date_m = _date_re.search(text)
    time_m = _time_re.search(text)
    if not (date_m and time_m):
        return None

    date_iso = dtparse.parse(date_m.group(1)).date().isoformat()

    # Treat parsed times as local, then keep timezone info in ISO
    start_local = dtparse.parse(f"{date_iso} {time_m.group(1)}")
    end_local   = dtparse.parse(f"{date_iso} {time_m.group(3)}")

    start_iso = start_local.astimezone().isoformat()
    end_iso   = end_local.astimezone().isoformat()

    # Title guess
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    try:
        date_idx = next(i for i, l in enumerate(lines) if _date_re.search(l))
        title = lines[date_idx + 2]
    except Exception:
        title = lines[0] if lines else "Untitled"
    title = title[:200]

    return {"title": title, "start": start_iso, "end": end_iso}

UPLOAD_DIR = Path(__file__).resolve().parents[1] / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

@app.post("/uploads", status_code=201)
async def upload_file(file: UploadFile = File(...)):
    raw = await file.read()
    ext = (Path(file.filename).suffix or ".png").lower()
    filename = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / filename).write_bytes(raw)

    text = ocr_to_text(raw)
    print("──── OCR TEXT ────"); print(text); print("──────────────────")

    extracted = extract_event_fields(text)
    if not extracted:
        raise HTTPException(status_code=422, detail="Could not parse date/time")

    extracted["thumb"] = f"/uploads/{filename}"
    return extracted

# ───────────────── CORS / startup ─────────────────
from os import getenv
origins = [getenv("FRONTEND_ORIGIN", "http://localhost:5173")]
codespaces_origin = getenv("CODESPACES_FRONTEND")
if codespaces_origin:
    origins.append(codespaces_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev-only; lock down later
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def init_db() -> None:
    Base.metadata.create_all(bind=engine)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/")
def read_root():
    return {"message": "FastAPI backend is running."}

# ───────────────── Events CRUD ─────────────────
@app.get("/events", response_model=list[EventOut])
def list_events(db: Session = Depends(get_db)):
    return db.scalars(select(Event)).all()

@app.post("/events", response_model=EventOut, status_code=201)
def create_event(data: EventIn, db: Session = Depends(get_db)):
    payload = data.model_dump()

    overlap = select(Event).where(
        and_(Event.start < payload["end"], Event.end > payload["start"])
    )
    conflict = db.scalars(overlap).first()
    if conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Time overlaps with another event.",
                "conflicts": [{
                    "id": conflict.id,
                    "title": conflict.title,
                    "start": conflict.start.isoformat(),
                    "end": conflict.end.isoformat(),
                }],
            },
        )

    evt = Event(**payload)
    db.add(evt)
    db.commit()
    db.refresh(evt)
    return evt

@app.put("/events/{event_id}", response_model=EventOut)
def update_event(event_id: int, payload: EventIn, db: Session = Depends(get_db)):
    overlap = select(Event).where(
        and_(Event.id != event_id, Event.start < payload.end, Event.end > payload.start)
    )
    conflict = db.scalars(overlap).first()
    if conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Time overlaps with another event.",
                "conflicts": [{
                    "id": conflict.id,
                    "title": conflict.title,
                    "start": conflict.start.isoformat(),
                    "end": conflict.end.isoformat(),
                }],
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

@app.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: int, db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    db.delete(event)
    db.commit()

# ───────────────── NEW: Natural language /parse ─────────────────
class ParseIn(BaseModel):
    prompt: str

class ParsedOut(BaseModel):
    title: Optional[str] = None
    start: Optional[str] = None  # ISO with timezone
    end:   Optional[str] = None

_time_range = re.compile(
    r"(?P<t1>\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*(?:-|–|—|to)\s*(?P<t2>\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
    re.I,
)
_until = re.compile(r"\b(?:until|thru|through|till|til)\s+(?P<date>.+)$", re.I)
_every_weekday = re.compile(r"\bevery\s+weekday\b", re.I)

def _next_weekday(base: datetime, target: int) -> datetime:
    delta = (target - base.weekday() + 7) % 7
    if delta == 0:
        delta = 7
    return base + timedelta(days=delta)

@app.post("/parse", response_model=ParsedOut)
def parse_prompt(data: ParseIn) -> ParsedOut:
    text = data.prompt.strip()
    if not text:
        return ParsedOut()

    base = datetime.now().astimezone()

    # time range
    tmatch = _time_range.search(text)
    t1 = t2 = None
    if tmatch:
        t1 = tmatch.group("t1")
        t2 = tmatch.group("t2")

    # try dateutil parse first (handles “next tue”, “tomorrow”, etc.)
    chosen_date: Optional[datetime] = None
    try:
        dt = dtparse.parse(text, default=base)
        if dt:
            chosen_date = dt if dt.tzinfo else dt.replace(tzinfo=base.tzinfo)
    except Exception:
        pass

    # fallback: every weekday → next business day
    if not chosen_date and _every_weekday.search(text):
        for add in range(1, 8):
            cand = base + timedelta(days=add)
            if cand.weekday() < 5:
                chosen_date = cand
                break

    if not chosen_date:
        chosen_date = base

    if t1 and t2:
        start_local = dtparse.parse(f"{chosen_date.date()} {t1}", default=chosen_date)
        end_local   = dtparse.parse(f"{chosen_date.date()} {t2}", default=chosen_date)
    else:
        start_local = chosen_date.replace(hour=10, minute=0, second=0, microsecond=0)
        end_local   = start_local + timedelta(hours=1)

    if end_local <= start_local:
        end_local = start_local + timedelta(hours=1)

    # title guess
    title = text
    if tmatch:
        title = title.replace(tmatch.group(0), "").strip()
    u = _until.search(title)
    if u:
        title = title.replace(u.group(0), "").strip()
    title = re.sub(r"^(on|at|this|next)\s+", "", title, flags=re.I)

    return ParsedOut(
        title=title or None,
        start=start_local.astimezone().isoformat(),
        end=end_local.astimezone().isoformat(),
    )
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