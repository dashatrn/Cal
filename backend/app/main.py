from datetime import datetime, date, timedelta, timezone
from typing import Optional
from pathlib import Path
import os
import re
import tempfile
import uuid

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, inspect
from dateutil import parser as dtparse
from dateutil.parser import isoparse as iso_parse
from zoneinfo import ZoneInfo
import pytesseract
from PIL import Image

# ── local modules ───────────────────────────────────────────────────
from .db import Base, engine, get_db
from .models import Event
from .schemas import EventIn, EventOut
# ────────────────────────────────────────────────────────────────────

app = FastAPI(title="Cal API")

# ───────────────────────── CORS ─────────────────────────────────────
frontend_origin = os.getenv("FRONTEND_ORIGIN")
codespaces_origin = os.getenv("CODESPACES_FRONTEND")

origins: list[str] = []
if frontend_origin:
    origins.append(frontend_origin)
if codespaces_origin:
    origins.append(codespaces_origin)
if not origins:  # dev-friendly default
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
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
        tmp_path = tmp.name
    try:
        return pytesseract.image_to_string(Image.open(tmp_path))
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass

# ───────────────────────── Helpers: parsing ─────────────────────────
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
    \s*(?P<s_ampm>[ap]m)?
    \s*(?:-|–|—|to)\s*
    (?P<e_h>\d{1,2})
    (?::(?P<e_m>\d{2}))?
    \s*(?P<e_ampm>[ap]m)?
""", re.IGNORECASE | re.VERBOSE)

TIME_SINGLE_RE = re.compile(r"\b(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ampm>[ap]m)?\b", re.IGNORECASE)
DURATION_RE = re.compile(r"\bfor\s+(?:(?P<h>\d+)\s*(?:hours?|hrs?|h))?\s*(?:(?P<m>\d+)\s*(?:minutes?|mins?|m))?\b", re.IGNORECASE)
UNTIL_RE    = re.compile(r"\buntil\s+(?P<date>(?:\d{1,2}/\d{1,2}(?:/\d{2,4})?|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\w*\s+\d{1,2}(?:,\s*\d{4})?))", re.IGNORECASE)
DAYS_LIST_RE = re.compile(r"""
    \b
    (?:(?:every|on)\s+)?                                  
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
DATE_TOKEN_RE   = re.compile(r"\b(?:\d{1,2}/\d{1,2}(?:/\d{2,4})?|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\w*\s+\d{1,2})\b", re.IGNORECASE)
EVERY_WEEKS_RE  = re.compile(r"\b(?:biweekly|every\s+other\s+week|every\s+(?P<n>\d+)\s+weeks?)\b", re.IGNORECASE)
FOR_WEEKS_RE    = re.compile(r"\bfor\s+(?P<n>\d+)\s+weeks?\b", re.IGNORECASE)

def to_24h(h: int, m: int, ampm: Optional[str]) -> tuple[int,int]:
    if ampm:
        ampm = ampm.lower()
        if ampm == "pm" and h != 12: h += 12
        if ampm == "am" and h == 12: h = 0
    return h, m

def parse_time_range(text: str):
    m = TIME_RANGE_RE.search(text)
    if not m: return None
    s_h = int(m.group("s_h")); s_m = int(m.group("s_m") or 0)
    e_h = int(m.group("e_h")); e_m = int(m.group("e_m") or 0)
    s_h, s_m = to_24h(s_h, s_m, m.group("s_ampm"))
    e_h, e_m = to_24h(e_h, e_m, m.group("e_ampm"))
    return (s_h, s_m, e_h, e_m)

def parse_single_time_and_duration(text: str) -> Optional[tuple[int,int,int]]:
    tm = TIME_SINGLE_RE.search(text)
    if not tm: return None
    h = int(tm.group("h")); m = int(tm.group("m") or 0)
    h, m = to_24h(h, m, tm.group("ampm"))
    dm = DURATION_RE.search(text)
    if not dm: return None
    dh = int(dm.group("h") or 0); dm_ = int(dm.group("m") or 0)
    duration = dh*60 + dm_
    if duration <= 0: duration = 60
    return (h, m, duration)

def parse_until_date(text: str, tz: ZoneInfo) -> Optional[date]:
    m = UNTIL_RE.search(text)
    if not m: return None
    raw = m.group("date")
    try:
        dt = dtparse.parse(raw, fuzzy=True, default=datetime.now(tz))
        today = datetime.now(tz).date()
        d = dt.date()
        if d < today and re.match(r"^\d{1,2}/\d{1,2}$", raw.strip()):
            d = date(today.year + 1, d.month, d.day)
        return d
    except Exception:
        return None

def parse_days_list(text: str) -> Optional[list[int]]:
    m = DAYS_LIST_RE.search(text)
    if not m: return None
    raw = m.group("days")
    parts = re.split(r"[/,]\s*", raw)
    out: list[int] = []
    for p in parts:
        p = p.strip().lower()
        key = {
            "mon":"monday","tue":"tuesday","tues":"tuesday","wed":"wednesday","weds":"wednesday",
            "thu":"thursday","thur":"thursday","thurs":"thursday",
            "fri":"friday","sat":"saturday","sun":"sunday"
        }.get(p, p)
        if key in DOW_MAP:
            out.append(DOW_MAP[key])
    return sorted(set(out)) or None

def parse_repeat(text: str) -> Optional[list[int]]:
    t = text.lower()
    if "every weekday" in t or "weekdays" in t: return [1,2,3,4,5]
    if "every day" in t or "everyday" in t or "daily" in t: return [0,1,2,3,4,5,6]
    dl = parse_days_list(text)
    return dl or None

def parse_every_weeks(text: str) -> Optional[int]:
    m = EVERY_WEEKS_RE.search(text)
    if not m: return None
    if m.group("n"):
        try: return max(1, int(m.group("n")))
        except Exception: return 2
    return 2

def parse_for_weeks(text: str) -> Optional[int]:
    m = FOR_WEEKS_RE.search(text)
    if not m: return None
    try: return max(1, int(m.group("n")))
    except Exception: return None

def scrub_title(text: str) -> str:
    t = UNTIL_RE.sub("", text)
    t = FOR_WEEKS_RE.sub("", t)
    t = EVERY_WEEKS_RE.sub("", t)
    t = DURATION_RE.sub("", t)
    t = TIME_RANGE_RE.sub("", t)
    t = re.sub(r"\b(daily|every\s+day|everyday|every\s+weekday|weekday|weekdays)\b", "", t, flags=re.I)
    t = DAYS_LIST_RE.sub("", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" ,.-\n\t")
    return (t or "Untitled").strip()

def build_iso(dt_local: datetime, tz: ZoneInfo) -> str:
    dt_local = dt_local.replace(tzinfo=tz)
    return dt_local.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")

# ───────────────────────── DB migrations (optional) ─────────────────
from alembic import command
from alembic.config import Config

def run_migrations() -> None:
    """Run Alembic migrations using app-local alembic.ini."""
    app_dir = Path(__file__).resolve().parent            # .../backend/app
    cfg = Config(str(app_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(app_dir / "migrations"))
    # If DATABASE_URL is set, use it; otherwise env/ini will take over
    if "DATABASE_URL" in os.environ:
        cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    command.upgrade(cfg, "head")

def ensure_event_columns(engine) -> None:
    """Best-effort no-op if table missing; safe on Postgres/SQLite."""
    with engine.begin() as conn:
        insp = inspect(conn)
        try:
            cols = {c["name"] for c in insp.get_columns("events")}
        except Exception:
            return  # table not present yet; migrations should handle it
        if "description" not in cols:
            conn.exec_driver_sql("ALTER TABLE events ADD COLUMN IF NOT EXISTS description TEXT")
        if "location" not in cols:
            conn.exec_driver_sql("ALTER TABLE events ADD COLUMN IF NOT EXISTS location TEXT")

@app.on_event("startup")
def on_startup():
    # Only run schema work if explicitly enabled
    if os.getenv("AUTO_MIGRATE") == "1":
        run_migrations()
        ensure_event_columns(engine)

# ───────────────────────── Lifecycle & health ───────────────────────
@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/")
def read_root():
    return {"message": "FastAPI backend is running."}

# ───────────────────────── Uploads → OCR ────────────────────────────
@app.post("/uploads", status_code=201)
async def upload_file(file: UploadFile = File(...)):
    raw = await file.read()
    ext = (Path(file.filename).suffix or ".png").lower()
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / filename
    dest.write_bytes(raw)

    text = ocr_to_text(raw)
    print("──── OCR TEXT ────")
    print(text)
    print("──────────────────")

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
        title = lines[date_idx + 2]
    except Exception:
        title = lines[0] if lines else "Untitled"
    title = title[:200]

    return {
        "title": title,
        "start": start_iso,
        "end": end_iso,
        "thumb": f"/uploads/{filename}",
    }

# ───────────────────────── Parse prompt (TZ aware) ──────────────────
@app.post("/parse")
async def parse_prompt(payload: dict):
    """
    Expects: { "prompt": string, "tz": "America/Los_Angeles" }
    Returns: { title?, start?, end?, repeatDays?, repeatUntil?, repeatEveryWeeks? }
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

    raw = prompt
    raw = re.sub(r"\bnoon\b", "12:00pm", raw, flags=re.I)
    raw = re.sub(r"\bmidnight\b", "12:00am", raw, flags=re.I)

    today = datetime.now(tz).date()
    WEEKDAY = {"mon":0,"tue":1,"tues":1,"wed":2,"thu":3,"thur":3,"thurs":3,"fri":4,"sat":5,"sun":6}

    def next_weekday(base: date, target_idx: int, inclusive=False) -> date:
        cur = base.weekday()  # Mon=0..Sun=6
        delta = (target_idx - cur) % 7
        if delta == 0 and not inclusive:
            delta = 7
        return base + timedelta(days=delta)

    def replace_relative(m: re.Match) -> str:
        w = m.group(0).lower()
        if w == "today":
            return today.isoformat()
        if w == "tomorrow":
            return (today + timedelta(days=1)).isoformat()
        mt = re.match(r"(this|next)\s+(mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)", w)
        if mt:
            kind, wd = mt.groups()
            idx = WEEKDAY[wd]
            if kind == "this":
                d = next_weekday(today, idx, inclusive=True)
            else:
                d = next_weekday(today, idx, inclusive=False)
            return d.isoformat()
        return w

    raw = re.sub(
        r"\b(today|tomorrow|(?:this|next)\s+(?:mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun))\b",
        replace_relative, raw, flags=re.I
    )

    prompt = raw

    tr = parse_time_range(prompt)
    s_h = s_m = e_h = e_m = None
    if tr:
        s_h, s_m, e_h, e_m = tr
    else:
        one = parse_single_time_and_duration(prompt)
        if one:
            s_h, s_m, dur = one
            end_dt = datetime(2000, 1, 1, s_h, s_m) + timedelta(minutes=dur)
            e_h, e_m = end_dt.hour, end_dt.minute
        else:
            s_h, s_m, e_h, e_m = (9, 0, 10, 0)

    repeat_days = parse_repeat(prompt)
    every_weeks = parse_every_weeks(prompt)
    for_weeks   = parse_for_weeks(prompt)
    until_d     = parse_until_date(prompt, tz)

    explicit_date = None
    try:
        if DATE_TOKEN_RE.search(prompt):
            dt = dtparse.parse(prompt, fuzzy=True, default=datetime.now(tz))
            explicit_date = dt.date()
    except Exception:
        explicit_date = None

    today_local = datetime.now(tz).date()
    base_date = explicit_date or today_local

    if every_weeks and not repeat_days:
        js_dow = (base_date.weekday() + 1) % 7  # map Mon=0..Sun=6 → Sun=0..Sat=6
        repeat_days = [js_dow]

    if for_weeks and not until_d:
        until_d = base_date + timedelta(weeks=for_weeks)

    title = scrub_title(prompt)

    start_local = datetime(base_date.year, base_date.month, base_date.day, s_h, s_m, 0)
    end_local   = datetime(base_date.year, base_date.month, base_date.day, e_h, e_m, 0)
    if end_local <= start_local:
        end_local += timedelta(hours=1)

    start_iso = build_iso(start_local, tz)
    end_iso   = build_iso(end_local, tz)

    out: dict = { "title": title, "start": start_iso, "end": end_iso }
    if repeat_days:
        out["repeatDays"] = repeat_days
    if until_d:
        out["repeatUntil"] = until_d.isoformat()
    if every_weeks:
        out["repeatEveryWeeks"] = every_weeks

    return out

# ───────────────────────── Suggest next free slot ───────────────────
@app.get("/suggest")
def suggest_next_free(start: str, end: str, db: Session = Depends(get_db)):
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
                "start": s.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "end":   (s + duration).astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        s = max(s, conflict.end)

# ───────────────────────── Events CRUD & list (range) ───────────────
@app.get("/events", response_model=list[EventOut])
def list_events(
    start: Optional[datetime] = Query(default=None),
    end:   Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
):
    q = select(Event)
    if start and end:
        q = q.where(and_(Event.start < end, Event.end > start))
    return db.scalars(q).all()

@app.post("/events", response_model=EventOut, status_code=201)
def create_event(data: EventIn, db: Session = Depends(get_db)):
    payload = data.model_dump()
    overlap_stmt = select(Event).where(and_(Event.start < payload["end"], Event.end > payload["start"]))
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
    db.add(evt); db.commit(); db.refresh(evt)
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
    db.commit(); db.refresh(event)
    return event

@app.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: int, db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    db.delete(event); db.commit()

# ───────────────────────── ICS export ───────────────────────────────
def _ics_dt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

@app.get("/events.ics")
def export_ics(
    start: Optional[datetime] = Query(default=None),
    end:   Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
):
    q = select(Event)
    if start and end:
        q = q.where(and_(Event.start < end, Event.end > start))
    rows = db.scalars(q).all()

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Cal//Dasha//EN",
    ]
    now_utc = datetime.now(timezone.utc)
    for e in rows:
        lines += [
            "BEGIN:VEVENT",
            f"UID:cal-{e.id}@local",
            f"DTSTAMP:{_ics_dt(now_utc)}",
            f"DTSTART:{_ics_dt(e.start)}",
            f"DTEND:{_ics_dt(e.end)}",
            f"SUMMARY:{(e.title or '').replace('\\n',' ')}",
            *( [f"LOCATION:{e.location}"] if getattr(e, 'location', None) else [] ),
            f"DESCRIPTION:{(getattr(e, 'description', '') or '').replace('\\n','\\n ')}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    ics = "\r\n".join(lines) + "\r\n"
    from fastapi.responses import Response
    return Response(content=ics, media_type="text/calendar")