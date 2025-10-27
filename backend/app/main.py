from datetime import datetime, date, timedelta, timezone
from typing import Optional, Tuple, Dict, Any
from pathlib import Path
import os
import re
import tempfile
import uuid

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, inspect
from dateutil import parser as dtparse
from dateutil.parser import isoparse as iso_parse
from zoneinfo import ZoneInfo

import pytesseract
from PIL import Image

# NEW: light-weight PDF text extraction
from pypdf import PdfReader

# ── local modules ───────────────────────────────────────────────────
from .db import Base, engine, get_db
from .models import Event
from .schemas import EventIn, EventOut
# ────────────────────────────────────────────────────────────────────

app = FastAPI(title="Cal API")

# ───────────────────────── CORS ─────────────────────────────────────
from fastapi.middleware.cors import CORSMiddleware

def _clean(s: str | None) -> str | None:
    return s.strip().rstrip("/") if s and s.strip() else None

FRONTEND_ORIGIN = _clean(os.getenv("FRONTEND_ORIGIN")) or "http://localhost:5173"
_raw_extra = os.getenv("EXTRA_CORS_ORIGINS", "")
EXTRA = [x for x in (_clean(p) for p in _raw_extra.split(",")) if x]
allow_origins = ["*"] if "*" in EXTRA else [o for o in {FRONTEND_ORIGIN, *EXTRA} if o]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,
)

# ───────────────────────── Static uploads ───────────────────────────
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"  # => /app/uploads
UPLOAD_DIR.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# ───────────────────────── OCR / PDF helpers ────────────────────────
def ocr_to_text(data: bytes) -> str:
    # Heuristic: tesseract likes PNG; write temp and read
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        # PSM 6: Assume a uniform block of text. OEM default.
        return pytesseract.image_to_string(Image.open(tmp_path), config="--psm 6")
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass

def pdf_to_text(data: bytes) -> str:
    # pypdf can read from file-like; simplest is temp file
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(data)
        pdf_path = tmp.name
    try:
        reader = PdfReader(pdf_path)
        texts = []
        for page in reader.pages:
            try:
                texts.append(page.extract_text() or "")
            except Exception:
                pass
        return "\n".join(texts)
    finally:
        try:
            Path(pdf_path).unlink(missing_ok=True)
        except Exception:
            pass

# ───────────────────────── Regex & parsing helpers ──────────────────
DOW_MAP = {
    "sunday": 0, "sun": 0,
    "monday": 1, "mon": 1,
    "tuesday": 2, "tue": 2, "tues": 2,
    "wednesday": 3, "wed": 3, "weds": 3,
    "thursday": 4, "thu": 4, "thur": 4, "thurs": 4,
    "friday": 5, "fri": 5,
    "saturday": 6, "sat": 6,
}

TZ_ABBR = {
    # common US zones; default to standard where ambiguous
    "ET": "America/New_York", "EST": "America/New_York", "EDT": "America/New_York",
    "CT": "America/Chicago",  "CST": "America/Chicago",  "CDT": "America/Chicago",
    "MT": "America/Denver",   "MST": "America/Denver",   "MDT": "America/Denver",
    "PT": "America/Los_Angeles","PST":"America/Los_Angeles","PDT":"America/Los_Angeles",
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
DURATION_RE = re.compile(r"\bfor\s+(?:(?P<h>\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h))?\s*(?:(?P<m>\d+)\s*(?:minutes?|mins?|m))?\b", re.IGNORECASE)
UNTIL_RE    = re.compile(r"\b(?:until|through)\s+(?P<date>(?:\d{1,2}/\d{1,2}(?:/\d{2,4})?|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\w*\s+\d{1,2}(?:,\s*\d{4})?))", re.IGNORECASE)
DAYS_LIST_RE = re.compile(r"""
    \b
    (?:(?:every|on)\s+)?                                  
    (?P<days>
      (?:
        mon|monday|tue|tues|tuesday|wed|weds|wednesday|
        thu|thur|thurs|thursday|fri|friday|sat|saturday|
        sun|sunday|weekdays|weekday|daily|everyday
      )
      (?:\s*[/,]\s*
        (?:mon|monday|tue|tues|tuesday|wed|weds|wednesday|
           thu|thur|thurs|thursday|fri|friday|sat|saturday|
           sun|sunday)
      )*
    )
    \b
""", re.IGNORECASE | re.VERBOSE)

DATE_TOKEN_RE = re.compile(r"\b(?:\d{1,2}/\d{1,2}(?:/\d{2,4})?|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\w*\s+\d{1,2}(?:,\s*\d{2,4})?)\b", re.IGNORECASE)
DATE_RANGE_RE = re.compile(r"""
    (?P<d1>\d{1,2}/\d{1,2}(?:/\d{2,4})?|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\w*\s+\d{1,2}(?:,\s*\d{2,4})?)
    \s*(?:-|–|—|to|through)\s*
    (?P<d2>\d{1,2}/\d{1,2}(?:/\d{2,4})?|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\w*\s+\d{1,2}(?:,\s*\d{2,4})?)
""", re.IGNORECASE | re.VERBOSE)

LOCATION_RE = re.compile(r"(?:\b@|\bat\b|\bin\b)\s+(?P<loc>[^,.;\n]+)", re.IGNORECASE)
DESC_RE     = re.compile(r"\b(?:desc|notes?)\s*:\s*(?P<desc>.+)$", re.IGNORECASE | re.MULTILINE)
TZ_RE       = re.compile(r"\b(ET|EST|EDT|CT|CST|CDT|MT|MST|MDT|PT|PST|PDT)\b", re.IGNORECASE)

def to_24h(h: int, m: int, ampm: Optional[str]) -> tuple[int,int]:
    if ampm:
        a = ampm.lower()
        if a == "pm" and h != 12: h += 12
        if a == "am" and h == 12: h = 0
    return h, m

def infer_missing_ampm(s_ampm: Optional[str], e_ampm: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    # If one side has am/pm, assume the other is the same
    if s_ampm and not e_ampm:
        return s_ampm, s_ampm
    if e_ampm and not s_ampm:
        return e_ampm, e_ampm
    return s_ampm, e_ampm

def parse_time_range(text: str):
    m = TIME_RANGE_RE.search(text)
    if not m: return None
    s_h = int(m.group("s_h")); s_m = int(m.group("s_m") or 0)
    e_h = int(m.group("e_h")); e_m = int(m.group("e_m") or 0)
    s_ampm, e_ampm = infer_missing_ampm(m.group("s_ampm"), m.group("e_ampm"))
    s_h, s_m = to_24h(s_h, s_m, s_ampm)
    e_h, e_m = to_24h(e_h, e_m, e_ampm)
    return (s_h, s_m, e_h, e_m)

def parse_single_time_and_duration(text: str) -> Optional[tuple[int,int,int]]:
    tm = TIME_SINGLE_RE.search(text)
    if not tm: return None
    h = int(tm.group("h")); m = int(tm.group("m") or 0)
    h, m = to_24h(h, m, tm.group("ampm"))
    dm = DURATION_RE.search(text)
    if not dm: return None
    # allow fractional hours eg "1.5h"
    dh_raw = dm.group("h")
    dh = float(dh_raw) if dh_raw else 0.0
    mm = int(dm.group("m") or 0)
    duration = int(round(dh*60 + mm))
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
    t = raw.lower().strip()
    if any(k in t for k in ["weekday", "weekdays"]):
        return [1,2,3,4,5]
    if any(k in t for k in ["daily", "everyday"]):
        return [0,1,2,3,4,5,6]
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

EVERY_WEEKS_RE  = re.compile(r"\b(?:biweekly|every\s+other\s+week|every\s+(?P<n>\d+)\s+weeks?)\b", re.IGNORECASE)
FOR_WEEKS_RE    = re.compile(r"\bfor\s+(?P<n>\d+)\s+weeks?\b", re.IGNORECASE)

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
    # remove trailing control phrases to leave a clean title
    t = DESC_RE.sub("", text)
    t = UNTIL_RE.sub("", t)
    t = FOR_WEEKS_RE.sub("", t)
    t = EVERY_WEEKS_RE.sub("", t)
    t = DURATION_RE.sub("", t)
    t = TIME_RANGE_RE.sub("", t)
    t = re.sub(r"\b(daily|every\s+day|everyday|every\s+weekday|weekday|weekdays)\b", "", t, flags=re.I)
    t = DAYS_LIST_RE.sub("", t)
    t = DATE_RANGE_RE.sub("", t)
    t = DATE_TOKEN_RE.sub("", t)
    t = LOCATION_RE.sub("", t)
    t = TZ_RE.sub("", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" ,.-\n\t")
    return (t or "Untitled").strip()

def build_iso(dt_local: datetime, tz: ZoneInfo) -> str:
    dt_local = dt_local.replace(tzinfo=tz)
    return dt_local.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")

def pick_tz(prompt_tz: Optional[str], fallback: ZoneInfo) -> ZoneInfo:
    if not prompt_tz:
        return fallback
    abbr = prompt_tz.upper()
    if abbr in TZ_ABBR:
        return ZoneInfo(TZ_ABBR[abbr])
    try:
        return ZoneInfo(prompt_tz)
    except Exception:
        return fallback

# ───────────────────────── DB migrations (optional) ─────────────────
from alembic import command
from alembic.config import Config

def run_migrations() -> None:
    app_dir = Path(__file__).resolve().parent
    cfg = Config(str(app_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(app_dir / "migrations"))
    if "DATABASE_URL" in os.environ:
        cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    command.upgrade(cfg, "head")

def ensure_event_columns(engine) -> None:
    with engine.begin() as conn:
        insp = inspect(conn)
        try:
            cols = {c["name"] for c in insp.get_columns("events")}
        except Exception:
            return
        if "description" not in cols:
            conn.exec_driver_sql("ALTER TABLE events ADD COLUMN IF NOT EXISTS description TEXT")
        if "location" not in cols:
            conn.exec_driver_sql("ALTER TABLE events ADD COLUMN IF NOT EXISTS location TEXT")

@app.on_event("startup")
def on_startup():
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

from sqlalchemy import text
@app.get("/dbcheck")
def dbcheck(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"db": "ok"}

# ───────────────────────── Core NLP parser ──────────────────────────
def parse_text_into_fields(raw_prompt: str, tz_name: str | None) -> Dict[str, Any]:
    """
    Returns: { title?, start?, end?, repeatDays?, repeatUntil?, repeatEveryWeeks?, location?, description? }
    Times are UTC ISO Z. repeatUntil is local YYYY-MM-DD.
    """
    base_tz = ZoneInfo(tz_name) if tz_name else ZoneInfo("UTC")

    text = raw_prompt.strip()
    if not text:
        return {}

    # normalize dashes, special words, and extract tz hint (ET/EST/etc.)
    text = text.replace("—", "-").replace("–", "-")
    text = re.sub(r"\bnoon\b", "12:00pm", text, flags=re.I)
    text = re.sub(r"\bmidnight\b", "12:00am", text, flags=re.I)
    tz_hint = None
    mtz = TZ_RE.search(text)
    if mtz:
        tz_hint = mtz.group(1)
    tz = pick_tz(tz_hint, base_tz)

    today = datetime.now(tz).date()
    WEEKDAY = {"mon":0,"tue":1,"tues":1,"wed":2,"thu":3,"thur":3,"thurs":3,"fri":4,"sat":5,"sun":6}

    def next_weekday(base: date, target_idx: int, inclusive=False) -> date:
        cur = base.weekday()
        delta = (target_idx - cur) % 7
        if delta == 0 and not inclusive:
            delta = 7
        return base + timedelta(days=delta)

    # relative dates → concrete yyyy-mm-dd
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
            d = next_weekday(today, idx, inclusive=(kind == "this"))
            return d.isoformat()
        return w

    text = re.sub(
        r"\b(today|tomorrow|(?:this|next)\s+(?:mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun))\b",
        replace_relative, text, flags=re.I
    )

    # Extract optional location/description early so they don’t pollute title
    location = None
    mloc = LOCATION_RE.search(text)
    if mloc:
        location = mloc.group("loc").strip()

    description = None
    mdesc = DESC_RE.search(text)
    if mdesc:
        description = mdesc.group("desc").strip()

    # Date range (e.g., "Nov 1-3", "11/01-11/03")
    range_m = DATE_RANGE_RE.search(text)
    date_range: Tuple[Optional[date], Optional[date]] = (None, None)
    if range_m:
        try:
            d1 = dtparse.parse(range_m.group("d1"), fuzzy=True, default=datetime.now(tz)).date()
            d2 = dtparse.parse(range_m.group("d2"), fuzzy=True, default=datetime.now(tz)).date()
            if d2 < d1:
                d2 = date(d1.year + 1, d2.month, d2.day)  # naive wrap if needed
            date_range = (d1, d2)
        except Exception:
            pass

    # Find an explicit single date token (fallback)
    explicit_date = None
    if not date_range[0]:
        try:
            if DATE_TOKEN_RE.search(text):
                dt = dtparse.parse(text, fuzzy=True, default=datetime.now(tz))
                explicit_date = dt.date()
        except Exception:
            explicit_date = None

    # Time extraction
    tr = parse_time_range(text)
    if tr:
        s_h, s_m, e_h, e_m = tr
    else:
        one = parse_single_time_and_duration(text)
        if one:
            s_h, s_m, dur = one
            end_dt = datetime(2000, 1, 1, s_h, s_m) + timedelta(minutes=dur)
            e_h, e_m = end_dt.hour, end_dt.minute
        else:
            s_h, s_m, e_h, e_m = (9, 0, 10, 0)

    # Repeat detection
    repeat_days = parse_days_list(text) or None
    every_weeks = parse_every_weeks(text)
    for_weeks   = parse_for_weeks(text)
    until_d     = parse_until_date(text, tz)

    # Range drives repeatUntil if present
    if date_range[0] and date_range[1]:
        # If no explicit repeat days provided, default to every day across the range
        if not repeat_days:
            repeat_days = [0,1,2,3,4,5,6]
        until_d = date_range[1]

    # Fallback base date
    base_date = explicit_date or date_range[0] or today

    # If “every N weeks” provided but no repeat days: use the weekday of base_date
    if every_weeks and not repeat_days:
        js_dow = (base_date.weekday() + 1) % 7  # Mon=0..Sun=6 → Sun=0..Sat=6
        repeat_days = [js_dow]

    # “for X weeks” without an explicit until date
    if for_weeks and not until_d:
        until_d = base_date + timedelta(weeks=for_weeks)

    # Title after scrubbing control phrases
    title = scrub_title(text)

    # Build ISO (timezone aware)
    start_local = datetime(base_date.year, base_date.month, base_date.day, s_h, s_m, 0)
    end_local   = datetime(base_date.year, base_date.month, base_date.day, e_h, e_m, 0)
    if end_local <= start_local:
        end_local += timedelta(hours=1)

    start_iso = build_iso(start_local, tz)
    end_iso   = build_iso(end_local,   tz)

    out: Dict[str, Any] = { "title": title, "start": start_iso, "end": end_iso }
    if location: out["location"] = location
    if description: out["description"] = description
    if repeat_days: out["repeatDays"] = repeat_days
    if until_d: out["repeatUntil"] = until_d.isoformat()
    if every_weeks: out["repeatEveryWeeks"] = every_weeks
    return out

# ───────────────────────── Uploads → OCR/PDF → parse ────────────────
@app.post("/uploads", status_code=201)
async def upload_file(file: UploadFile = File(...)):
    raw = await file.read()
    ext = (Path(file.filename).suffix or ".bin").lower()
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / filename
    dest.write_bytes(raw)

    # Extract text based on type
    text_ = ""
    is_image = ext in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
    is_pdf = ext == ".pdf"

    try:
        if is_image:
            text_ = ocr_to_text(raw)
        elif is_pdf:
            text_ = pdf_to_text(raw)
        else:
            # Fallback: try OCR anyway (e.g., unknown image)
            text_ = ocr_to_text(raw)
    except Exception:
        raise HTTPException(status_code=422, detail="Could not read that file")

    # Use our core parser (no tz passed here — client will localize after)
    fields = parse_text_into_fields(text_, None)

    # Provide thumb only for images (frontend shows a tiny preview)
    if is_image:
        fields["thumb"] = f"/uploads/{filename}"

    # Basic sanity: if we couldn’t find both date and time, signal a 422
    if not fields.get("start") or not fields.get("end"):
        raise HTTPException(status_code=422, detail="Could not parse date/time from the file")

    return fields

# ───────────────────────── Parse prompt (TZ aware) ──────────────────
@app.post("/parse")
async def parse_prompt(payload: dict):
    """
    Expects: { "prompt": string, "tz": "America/Los_Angeles" or "ET"/"EST"/... }
    Returns: { title?, start?, end?, repeatDays?, repeatUntil?, repeatEveryWeeks?, location?, description? }
    All times returned as UTC ISO Z; repeatUntil as YYYY-MM-DD (local date)
    """
    prompt = (payload.get("prompt") or "").strip()
    tz_name = payload.get("tz") or "UTC"
    if not prompt:
        return {}
    try:
        # If tz is an abbreviation, parse_text_into_fields will map it
        return parse_text_into_fields(prompt, tz_name)
    except Exception:
        # Be forgiving; worst case, return empty so UI can continue
        return {}

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