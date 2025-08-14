# app/main.py
from datetime import datetime, date, timedelta
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from pathlib import Path
import uuid
import tempfile
import re

from dateutil import parser as dtparse          # pip install python-dateutil
from dateutil.parser import isoparse as iso_parse
import pytesseract                              # pip install pytesseract pillow
from PIL import Image                           # pip install pillow
from zoneinfo import ZoneInfo                   # py3.9+

# ── local modules ───────────────────────────────────────────────────
from .db import Base, engine, get_db
from .models import Event
from .schemas import EventIn, EventOut
# ────────────────────────────────────────────────────────────────────

app = FastAPI(title="Cal API")

# ───────────────────────── CORS ─────────────────────────────────────
from os import getenv
origins = [
    getenv("FRONTEND_ORIGIN", "http://localhost:5173"),
]
codespaces_origin = getenv("CODESPACES_FRONTEND")
if codespaces_origin:
    origins.append(codespaces_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # dev-friendly; lock down later
    allow_methods=["*"],
    allow_headers=["*"],
)

# ───────────────────────── Static uploads ───────────────────────────
UPLOAD_DIR = Path(__file__).resolve().parents[1] / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# ───────────────────────── Helpers: OCR ─────────────────────────────
def ocr_to_text(data: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(data)
    try:
        text = pytesseract.image_to_string(Image.open(tmp.name))
        return text
    finally:
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except Exception:
            pass

# ───────────────────────── Helpers: prompt parsing ──────────────────
# day name → 0..6
DOW_MAP = {
    "sunday": 0, "sun": 0,
    "monday": 1, "mon": 1,
    "tuesday": 2, "tue": 2, "tues": 2,
    "wednesday": 3, "wed": 3, "weds": 3,
    "thursday": 4, "thu": 4, "thur": 4, "thurs": 4,
    "friday": 5, "fri": 5,
    "saturday": 6, "sat": 6,
}

TIME_RANGE_RE = re.compile(r"""
    (?P<s_h>\d{1,2})
    (?::(?P<s_m>\d{2}))?
    \s*(?P<s_ampm>[ap]m)?          # optional am/pm for start
    \s*(?:-|–|—|to)\s*
    (?P<e_h>\d{1,2})
    (?::(?P<e_m>\d{2}))?
    \s*(?P<e_ampm>[ap]m)?          # optional am/pm for end
""", re.IGNORECASE | re.VERBOSE)

# “until …” (8/31, 12/10, “Sept 15”, etc.)
UNTIL_RE = re.compile(
    r"\buntil\s+(?P<date>(?:\d{1,2}/\d{1,2}(?:/\d{2,4})?"
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\w*\s+\d{1,2}(?:,\s*\d{4})?))",
    re.IGNORECASE
)

# Lists like “Mon/Wed/Fri”, “Mon, Wed” — NO single-letter tokens anymore
DAYS_LIST_RE = re.compile(r"""
    \b
    (?:(?:every|on)\s+)?                                  # optional prefix
    (?P<days>
      (?:
        mon|monday|tue|tues|tuesday|wed|weds|wednesday|
        thu|thur|thurs|thursday|fri|friday|sat|saturday|
        sun|sunday
      )
      (?:\s*[/,]\s*
        (?:mon|monday|tue|tues|tuesday|wed|weds|wednesday|
           thu|thur|thurs|thursday|fri|friday|sat|saturday|
           sun|sunday)
      )*
    )
    \b
""", re.IGNORECASE | re.VERBOSE)

# For “explicit date” detection we ONLY accept slash-dates or month names
DATE_TOKEN_RE = re.compile(
    r"\b(?:\d{1,2}/\d{1,2}(?:/\d{2,4})?"
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\w*\s+\d{1,2})\b",
    re.IGNORECASE
)

def to_24h(h: int, m: int, ampm: Optional[str]) -> tuple[int, int]:
    if ampm:
        ampm = ampm.lower()
        if ampm == "pm" and h != 12:
            h += 12
        if ampm == "am" and h == 12:
            h = 0
    return h, m

def parse_time_range(text: str):
    m = TIME_RANGE_RE.search(text)
    if not m:
        return None
    s_h = int(m.group("s_h")); s_m = int(m.group("s_m") or 0)
    e_h = int(m.group("e_h")); e_m = int(m.group("e_m") or 0)
    s_h, s_m = to_24h(s_h, s_m, m.group("s_ampm"))
    e_h, e_m = to_24h(e_h, e_m, m.group("e_ampm"))
    return (s_h, s_m, e_h, e_m)

def parse_until_date(text: str, tz: ZoneInfo) -> Optional[date]:
    m = UNTIL_RE.search(text)
    if not m:
        return None
    raw = m.group("date")
    try:
        dt = dtparse.parse(raw, fuzzy=True, default=datetime.now(tz))
        today = datetime.now(tz).date()
        d = dt.date()
        # If no year and it parsed into past, roll to next year
        if d < today and re.match(r"^\d{1,2}/\d{1,2}$", raw.strip()):
            d = date(today.year + 1, d.month, d.day)
        return d
    except Exception:
        return None

def parse_days_list(text: str) -> Optional[list[int]]:
    m = DAYS_LIST_RE.search(text)
    if not m:
        return None
    raw = m.group("days")
    parts = re.split(r"[/,]\s*", raw)
    out: list[int] = []
    for p in parts:
        p = p.strip().lower()
        # normalize to keys in DOW_MAP
        if p in {"mon","monday","tue","tues","tuesday","wed","weds","wednesday",
                 "thu","thur","thurs","thursday","fri","friday","sat","saturday",
                 "sun","sunday"}:
            key = {"mon":"monday","tue":"tuesday","tues":"tuesday","wed":"wednesday",
                   "weds":"wednesday","thu":"thursday","thur":"thursday","thurs":"thursday",
                   "fri":"friday","sat":"saturday","sun":"sunday"}.get(p, p)
            out.append(DOW_MAP[key])
    return sorted(set(out)) or None

def parse_repeat(text: str) -> Optional[list[int]]:
    t = text.lower()
    if "every weekday" in t or "weekdays" in t:
        return [1,2,3,4,5]
    if "every day" in t or "everyday" in t or "daily" in t:
        return [0,1,2,3,4,5,6]
    dl = parse_days_list(text)
    if dl:
        return dl
    return None

def scrub_title(text: str) -> str:
    # remove recurrence & time phrases from the title
    t = UNTIL_RE.sub("", text)
    t = TIME_RANGE_RE.sub("", t)
    t = re.sub(r"\b(daily|every\s+day|everyday|every\s+weekday|weekday|weekdays)\b", "", t, flags=re.IGNORECASE)
    t = DAYS_LIST_RE.sub("", t)   # e.g., "Mon/Wed"
    t = re.sub(r"\s{2,}", " ", t).strip(" ,.-\n\t")
    return (t or "Untitled").strip()

def build_iso(dt_local: datetime, tz: ZoneInfo) -> str:
    # attach tz and convert to UTC Z
    dt_local = dt_local.replace(tzinfo=tz)
    return dt_local.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")

# ───────────────────────── Routes ───────────────────────────────────

@app.on_event("startup")
def init_db() -> None:
    Base.metadata.create_all(bind=engine)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/")
def read_root():
    return {"message": "FastAPI backend is running."}

# Upload → OCR → naive parse
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

    # very naive: find first date line and time range line
    date_re = re.compile(
        r"\b(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\w+\s+\d{1,2},\s*\d{4})\b",
        re.IGNORECASE,
    )
    time_m = TIME_RANGE_RE.search(text)
    date_m = date_re.search(text)
    if not (date_m and time_m):
        raise HTTPException(status_code=422, detail="Could not parse date/time")

    date_iso = dtparse.parse(date_m.group(1)).date().isoformat()

    tr = parse_time_range(text)
    if not tr:
        raise HTTPException(status_code=422, detail="Could not parse time range")
    s_h, s_m, e_h, e_m = tr

    start_iso = f"{date_iso}T{str(s_h).zfill(2)}:{str(s_m).zfill(2)}:00"
    end_iso   = f"{date_iso}T{str(e_h).zfill(2)}:{str(e_m).zfill(2)}:00"

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    try:
        date_idx = next(i for i, l in enumerate(lines) if date_re.search(l))
        title = lines[date_idx + 2]  # heuristic
    except Exception:
        title = lines[0] if lines else "Untitled"
    title = title[:200]

    return {
        "title": title,
        "start": start_iso,
        "end": end_iso,
        "thumb": f"/uploads/{filename}",
    }

# Prompt → smart-ish parse (local TZ aware)
@app.post("/parse")
async def parse_prompt(payload: dict):
    """
    Expects: { "prompt": string, "tz": "America/Los_Angeles" }
    Returns: { title?, start?, end?, repeatDays?, repeatUntil? }
    All times returned as UTC ISO Z; repeatUntil as YYYY-MM-DD (local date)
    """
    prompt = (payload.get("prompt") or "").strip()
    tz_name = payload.get("tz") or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")

    if not prompt:
        return {}

    # 1) time range
    tr = parse_time_range(prompt)
    # default to 09:00–10:00 if none
    if tr:
        s_h, s_m, e_h, e_m = tr
    else:
        s_h, s_m, e_h, e_m = (9, 0, 10, 0)

    # 2) repeat
    repeat_days = parse_repeat(prompt)

    # 3) until
    until_d = parse_until_date(prompt, tz)

    # 4) base date:
    explicit_date = None
    try:
        if DATE_TOKEN_RE.search(prompt):
            dt = dtparse.parse(prompt, fuzzy=True, default=datetime.now(tz))
            explicit_date = dt.date()
    except Exception:
        explicit_date = None

    today_local = datetime.now(tz).date()
    base_date = explicit_date or today_local

    # 5) title
    title = scrub_title(prompt)

    # 6) build start/end ISO (UTC) from local
    start_local = datetime(base_date.year, base_date.month, base_date.day, s_h, s_m, 0)
    end_local   = datetime(base_date.year, base_date.month, base_date.day, e_h, e_m, 0)
    if end_local <= start_local:
        end_local += timedelta(hours=1)  # safety

    start_iso = build_iso(start_local, tz)
    end_iso   = build_iso(end_local, tz)

    out: dict = {
        "title": title,
        "start": start_iso,
        "end": end_iso,
    }
    if repeat_days:
        out["repeatDays"] = repeat_days
    if until_d:
        out["repeatUntil"] = until_d.isoformat()

    return out

# ───────────────────────── Suggest next free slot ───────────────────
@app.get("/suggest")
def suggest_next_free(start: str, end: str, db: Session = Depends(get_db)):
    """
    Query params: start, end (ISO strings, usually UTC 'Z')
    Returns: {"start": ISO, "end": ISO} with the next non-overlapping window.
    """
    try:
        s = iso_parse(start)
        e = iso_parse(end)
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid ISO datetimes")

    if e <= s:
        e = s + timedelta(hours=1)

    duration = e - s

    while True:
        conflict = db.scalars(
            select(Event).where(and_(Event.start < s + duration, Event.end > s))
        ).first()
        if not conflict:
            return {
                "start": s.isoformat().replace("+00:00", "Z"),
                "end": (s + duration).isoformat().replace("+00:00", "Z"),
            }
        # Move start to the end of the conflicting event
        s = max(s, conflict.end)

# ───────────────────────── Events CRUD ──────────────────────────────

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
    overlap_stmt = select(Event).where(
        and_(Event.id != event_id, Event.start < payload.end, Event.end > payload.start)
    )
    conflict = db.scalars(overlap_stmt).first()
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