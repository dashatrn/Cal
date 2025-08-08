# app/main.py

from datetime import datetime, date, timedelta
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from sqlalchemy.exc import IntegrityError

import uuid
import tempfile, re
from pathlib import Path
from dateutil import parser as dtparse
import pytesseract
from PIL import Image

# ── local modules ─────────────────────────────────────────────
from .db import Base, engine, get_db
from .models import Event
from .schemas import EventIn, EventOut
# ─────────────────────────────────────────────────────────────

app = FastAPI(title="Cal API")

# ──────────────────────────────── OCR helpers ────────────────────────────────

def ocr_to_text(data: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(data)
    try:
        text = pytesseract.image_to_string(Image.open(tmp.name))
        return text
    finally:
        Path(tmp.name).unlink(missing_ok=True)

UPLOAD_DIR = Path(__file__).resolve().parents[1] / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

_date_re = re.compile(
    r"\b(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\w+\s+\d{1,2},\s*\d{4})\b",
    re.IGNORECASE,
)
_time_range_re = re.compile(
    r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*(?:-|–|—|to)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
    re.IGNORECASE,
)

def extract_event_fields(text: str) -> dict[str, str] | None:
    """Very simple extractor used for /uploads OCR results."""
    date_m = _date_re.search(text)
    time_m = _time_range_re.search(text)
    if not (date_m and time_m):
        return None

    date_iso = dtparse.parse(date_m.group(1)).date().isoformat()
    start_iso = dtparse.parse(f"{date_iso} {time_m.group(1)}").isoformat(timespec="seconds")
    end_iso   = dtparse.parse(f"{date_iso} {time_m.group(2)}").isoformat(timespec="seconds")

    # Title → first non-empty line that isn’t the date/time line
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = "Untitled"
    if lines:
        try:
            date_idx = next(i for i, l in enumerate(lines) if _date_re.search(l))
            # heuristic: date line, (maybe) time line, then title-ish
            if date_idx + 2 < len(lines):
                title = lines[date_idx + 2][:200]
            else:
                title = lines[0][:200]
        except StopIteration:
            title = lines[0][:200]

    return {"title": title, "start": start_iso, "end": end_iso}

@app.post("/uploads", status_code=201)
async def upload_file(file: UploadFile = File(...)):
    raw = await file.read()

    # save original
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

    extracted["thumb"] = f"/uploads/{filename}"
    return extracted

# ────────────────────────────── Prompt parser ────────────────────────────────
# No external libs beyond dateutil & regex; supports:
#  - dates: explicit (Aug 9, 8/9, 2025-08-09), “today”, “tomorrow”
#  - days: mon/tue/wed/thu/fri/sat/sun, “weekday(s)”, “weekend(s)”
#  - ranges: "10-11", "10am-11:15", "from 3pm to 4", "7:30 to 8"
#  - repetition: “every mon/wed”, “mwf”, “until Dec 10”
#  - title: leftover words after removing date/time keywords

DAYS = {
    "sun": 0, "sunday": 0,
    "mon": 1, "monday": 1,
    "tue": 2, "tues": 2, "tuesday": 2,
    "wed": 3, "wednesday": 3,
    "thu": 4, "thur": 4, "thurs": 4, "thursday": 4,
    "fri": 5, "friday": 5,
    "sat": 6, "saturday": 6,
}
WEEKDAY_SET = {1,2,3,4,5}
WEEKEND_SET = {0,6}

one_time_re   = re.compile(r"\b(?:at\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", re.IGNORECASE)
range_re      = _time_range_re
from_to_re    = re.compile(r"\bfrom\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s+to\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", re.IGNORECASE)
date_word_re  = re.compile(r"\b(today|tomorrow)\b", re.IGNORECASE)
explicit_date = _date_re
every_re      = re.compile(r"\b(?:every|each)\b", re.IGNORECASE)
until_re      = re.compile(r"\b(?:until|till|through)\s+(.+)$", re.IGNORECASE)

def _next_weekday(dow: int, base: date) -> date:
    delta = (dow - base.weekday()) % 7
    return base + timedelta(days=delta)

def _parse_times(txt: str) -> tuple[Optional[str], Optional[str], str]:
    # 1) range "10-11", "10am-11:15"
    m = range_re.search(txt) or from_to_re.search(txt)
    if m:
        s, e = m.group(1), m.group(2)
        cleaned = txt[:m.start()] + txt[m.end():]
        return s, e, cleaned

    # 2) single time "at 7pm" → +1 hour default
    m = one_time_re.search(txt)
    if m:
        t = m.group(1)
        cleaned = txt[:m.start()] + txt[m.end():]
        return t, None, cleaned

    return None, None, txt

def _parse_days(txt: str) -> tuple[set[int], str]:
    dows: set[int] = set()
    cleaned = txt

    # weekdays / weekends
    for key, group in [("weekdays", WEEKDAY_SET), ("weekday", WEEKDAY_SET),
                       ("weekends", WEEKEND_SET), ("weekend", WEEKEND_SET)]:
        i = cleaned.lower().find(key)
        if i != -1:
            dows |= set(group)
            cleaned = cleaned[:i] + cleaned[i+len(key):]

    # words or comma/slash separated lists (mon, wed) (mon/wed)
    tokens = re.findall(r"\b([a-z]{2,9})\b", cleaned.lower())
    for tk in tokens:
        if tk in DAYS:
            dows.add(DAYS[tk])

    # compact forms like "mwf", "tth"
    for chunk in re.findall(r"\b([mtwhfsu]{2,7})\b", cleaned.lower()):
        # greedily map letter groups
        repl = chunk
        mapping = {
            "m":1,"t":2,"w":3,"th":4,"r":4,"f":5,"s":6,"su":0,"u":0
        }
        i=0
        while i < len(chunk):
            if chunk[i:i+2] in ("th","su"):
                dows.add(mapping[chunk[i:i+2]])
                i += 2
            else:
                c = chunk[i]
                if c in mapping:
                    dows.add(mapping[c])
                i += 1
        cleaned = cleaned.replace(chunk, "")

    # also remove explicit day words we matched
    for name in sorted(DAYS.keys(), key=len, reverse=True):
        cleaned = re.sub(rf"\b{name}\b", "", cleaned, flags=re.IGNORECASE)

    # remove words "every"/"each"
    cleaned = every_re.sub("", cleaned)

    return dows, cleaned

def _parse_date(txt: str, base_day: Optional[int]) -> tuple[date, str]:
    today = date.today()

    # explicit "today/tomorrow"
    m = date_word_re.search(txt)
    if m:
        word = m.group(1).lower()
        cleaned = txt[:m.start()] + txt[m.end():]
        return (today if word == "today" else today + timedelta(days=1)), cleaned

    # explicit date like Aug 9 / 8-9 / 2025-08-09
    m = explicit_date.search(txt)
    if m:
        d = dtparse.parse(m.group(1)).date()
        cleaned = txt[:m.start()] + txt[m.end():]
        return d, cleaned

    # use next occurrence of parsed weekday if present
    if base_day is not None:
        return _next_weekday(base_day, today), txt

    # fallback: today
    return today, txt

def _parse_until(txt: str) -> tuple[Optional[date], str]:
    m = until_re.search(txt)
    if not m:
        return None, txt
    try:
        d = dtparse.parse(m.group(1)).date()
        cleaned = txt[:m.start()] + txt[m.end():]
        return d, cleaned
    except Exception:
        return None, txt

def _strip_extraneous(txt: str) -> str:
    # very light cleanup after yanking tokens out
    txt = re.sub(r"\s{2,}", " ", txt)
    txt = re.sub(r"\b(?:at|on|from|to|the|a|an|and|of)\b", " ", txt, flags=re.IGNORECASE)
    return " ".join(txt.split()).strip(" ,.-")

@app.post("/parse")
def parse_prompt(payload: dict):
    """
    Input:  { "prompt": "CS 124 Mon/Wed 9:30-10:20 until Dec 10" }
    Output: {
      "title": "CS 124",
      "start": "2025-08-06T09:30:00",
      "end": "2025-08-06T10:20:00",
      "repeatDays": [1,3],
      "repeatUntil": "2025-12-10"
    }
    All times are LOCAL (naive) to match the current app behavior.
    """
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return {}

    txt = " " + prompt + " "  # padding for regex slicing simplicity

    # repetition “until …”
    repeat_until, txt = _parse_until(txt)

    # days of week / groups
    dows, txt = _parse_days(txt)

    # time(s)
    t1, t2, txt = _parse_times(txt)

    # date (if any) — if repeating days were given, use the first of those for the initial date
    first_dow = min(dows) if dows else None
    the_date, txt = _parse_date(txt, first_dow)

    # Build start/end (LOCAL) — if only single time was given, make it a 60-min block
    def _resolve(when: date, t: str) -> datetime:
        return dtparse.parse(f"{when.isoformat()} {t}")

    start_dt = None
    end_dt   = None
    if t1 and t2:
        start_dt = _resolve(the_date, t1)
        end_dt   = _resolve(the_date, t2)
        # if user writes "10-9" by mistake, swap
        if end_dt <= start_dt:
            end_dt = start_dt + timedelta(hours=1)
    elif t1:
        start_dt = _resolve(the_date, t1)
        end_dt   = start_dt + timedelta(hours=1)

    # Title is the leftover text
    title = _strip_extraneous(txt)
    if not title:
        # fallback: use first 3 words of the original prompt
        title = " ".join(prompt.split()[:3]) or "Untitled"

    out = {"title": title}
    if start_dt and end_dt:
        out["start"] = start_dt.isoformat(timespec="seconds")
        out["end"]   = end_dt.isoformat(timespec="seconds")
    if dows:
        out["repeatDays"] = sorted(list(dows))
    if repeat_until:
        out["repeatUntil"] = repeat_until.isoformat()

    return out

# ─────────────────────────────── CORS & startup ──────────────────────────────

from os import getenv
origins = [getenv("FRONTEND_ORIGIN", "http://localhost:5173")]
codespaces_origin = getenv("CODESPACES_FRONTEND")
if codespaces_origin:
    origins.append(codespaces_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # dev-only; tighten later
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

# ─────────────────────────────── events CRUD ────────────────────────────────

@app.get("/events", response_model=list[EventOut])
def list_events(db: Session = Depends(get_db)):
    return db.scalars(select(Event)).all()

@app.post("/events", response_model=EventOut, status_code=201)
def create_event(data: EventIn, db: Session = Depends(get_db)):
    payload = data.model_dump()

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

    evt = Event(**payload)
    db.add(evt)
    db.commit()
    db.refresh(evt)
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

@app.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: int, db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    db.delete(event)
    db.commit()

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