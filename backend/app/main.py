# backend/app/main.py
from __future__ import annotations

import io
import os
import re
import json
from datetime import datetime, timedelta, date, time, timezone
from typing import Optional, Any, Dict, List, Tuple

from zoneinfo import ZoneInfo

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from PIL import Image
import pytesseract
from pypdf import PdfReader

from ics import Calendar, Event as ICSEvent

from .db import get_db
from .models import Event, RecurrenceSeries, RecurrenceException
from .schemas import EventIn, EventOut, SeriesIn, SeriesCreateOut


# ───────────────────────── App init / CORS ───────────────────────────
app = FastAPI(title="Cal API")

origins = [
    os.getenv("CORS_ORIGIN", "http://localhost:5173"),
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ───────────────────────── Helpers ───────────────────────────────────
def _tz(tz_name: Optional[str]) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_date_yyyy_mm_dd(s: str) -> Optional[date]:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _clean_text(s: str) -> str:
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


# ───────────────────────── OCR / PDF text extraction ─────────────────
def extract_text_from_image_bytes(data: bytes) -> str:
    img = Image.open(io.BytesIO(data))
    # You can tune OCR config if needed
    text = pytesseract.image_to_string(img)
    return _clean_text(text)


def extract_text_from_pdf_bytes(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return _clean_text("\n".join(parts))


# ───────────────────────── Parsing (free-text -> fields) ─────────────
class ParseRequest(BaseModel):
    prompt: str
    tz: Optional[str] = None


# Very lightweight parsing (your project can swap to LLM later)
DATE_PAT = re.compile(r"(\d{4}-\d{2}-\d{2})")
TIME_PAT = re.compile(r"(\d{1,2}:\d{2})")


def parse_prompt_to_fields(prompt: str, tz_name: str) -> Dict[str, Any]:
    tz = _tz(tz_name)
    text = _clean_text(prompt)

    # Defaults
    title = text[:60] if text else "New Event"
    start_dt = datetime.now(tz).replace(second=0, microsecond=0)
    end_dt = start_dt + timedelta(hours=1)

    # Date
    m = DATE_PAT.search(text)
    if m:
        d = _parse_date_yyyy_mm_dd(m.group(1))
        if d:
            start_dt = start_dt.replace(year=d.year, month=d.month, day=d.day)
            end_dt = end_dt.replace(year=d.year, month=d.month, day=d.day)

    # Time
    tm = TIME_PAT.search(text)
    if tm:
        hh, mm = tm.group(1).split(":")
        try:
            start_dt = start_dt.replace(hour=int(hh), minute=int(mm))
            end_dt = start_dt + timedelta(hours=1)
        except Exception:
            pass

    out = {
        "title": title,
        "start": _as_utc(start_dt).isoformat(),
        "end": _as_utc(end_dt).isoformat(),
    }

    # OPTIONAL recurrence hints (very simple heuristics)
    # If prompt contains days like "Mon Wed Fri until 2025-12-31"
    days_map = {
        "sun": 0, "sunday": 0,
        "mon": 1, "monday": 1,
        "tue": 2, "tues": 2, "tuesday": 2,
        "wed": 3, "wednesday": 3,
        "thu": 4, "thur": 4, "thurs": 4, "thursday": 4,
        "fri": 5, "friday": 5,
        "sat": 6, "saturday": 6,
    }
    lower = text.lower()
    repeat_days = []
    for k, v in days_map.items():
        if re.search(rf"\b{k}\b", lower):
            repeat_days.append(v)
    repeat_days = sorted(set(repeat_days))

    until = None
    um = re.search(r"\buntil\s+(\d{4}-\d{2}-\d{2})\b", lower)
    if um:
        until = um.group(1)

    if repeat_days and until:
        out["repeatDays"] = repeat_days
        out["repeatUntil"] = until
        # crude "every N weeks" hint
        em = re.search(r"\bevery\s+(\d+)\s+weeks?\b", lower)
        if em:
            out["repeatEveryWeeks"] = int(em.group(1))

    return out


@app.post("/parse")
def parse_endpoint(req: ParseRequest):
    tz_name = req.tz or "UTC"
    fields = parse_prompt_to_fields(req.prompt, tz_name)
    return fields


@app.post("/uploads")
async def upload_and_parse(file: UploadFile = File(...), tz: Optional[str] = Query(default=None)):
    data = await file.read()
    name = (file.filename or "").lower()

    if name.endswith(".pdf"):
        extracted = extract_text_from_pdf_bytes(data)
    else:
        extracted = extract_text_from_image_bytes(data)

    fields = parse_prompt_to_fields(extracted, tz or "UTC")
    # Frontend expects thumb optionally; you can extend here if you store images
    return fields


# ───────────────────────── Recurrence Series (server-side) ───────────
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

def _series_occurrences_utc(
    start_utc: datetime,
    end_utc: datetime,
    *,
    tz_name: str,
    repeat_days: list[int],
    repeat_every_weeks: int,
    repeat_until_local: date,
    freq: str = "WEEKLY",
) -> list[tuple[datetime, datetime]]:
    """Generate occurrence (start,end) datetimes in UTC.

    repeat_until_local is interpreted in tz_name.
    """
    if start_utc.tzinfo is None or end_utc.tzinfo is None:
        raise HTTPException(status_code=400, detail="start/end must be timezone-aware datetimes")

    if end_utc <= start_utc:
        raise HTTPException(status_code=400, detail="end must be after start")

    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid tz: {tz_name}")

    start_local = start_utc.astimezone(tz)
    end_local   = end_utc.astimezone(tz)
    dur = end_utc - start_utc

    start_date_local = start_local.date()
    until_date_local = repeat_until_local

    # If user gives an until before start date, nothing to do
    if until_date_local < start_date_local:
        return []

    # Normalize repeat days
    if not repeat_days:
        repeat_days = [start_local.weekday()]  # Python weekday: Mon=0..Sun=6
        # But our UI uses 0=Sun..6=Sat. Convert below.

    # UI: 0=Sun..6=Sat -> Python weekday: Mon=0..Sun=6
    ui_to_py = {0: 6, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}
    py_weekdays = sorted({ui_to_py.get(d, d) for d in repeat_days})

    occurrences: list[tuple[datetime, datetime]] = []

    if freq.upper() == "DAILY":
        interval = max(1, int(repeat_every_weeks))
        d = start_date_local
        while d <= until_date_local:
            delta_days = (d - start_date_local).days
            if delta_days % interval == 0:
                occ_local = datetime(
                    d.year, d.month, d.day,
                    start_local.hour, start_local.minute, start_local.second,
                    start_local.microsecond,
                    tzinfo=tz,
                )
                occ_utc = occ_local.astimezone(timezone.utc)
                occurrences.append((occ_utc, occ_utc + dur))
            d = d + timedelta(days=1)

        return occurrences

    if freq.upper() == "MONTHLY":
        interval = max(1, int(repeat_every_weeks))
        start_dom = start_date_local.day
        d = start_date_local
        while d <= until_date_local:
            months = (d.year - start_date_local.year) * 12 + (d.month - start_date_local.month)
            if d.day == start_dom and months % interval == 0:
                occ_local = datetime(
                    d.year, d.month, d.day,
                    start_local.hour, start_local.minute, start_local.second,
                    start_local.microsecond,
                    tzinfo=tz,
                )
                occ_utc = occ_local.astimezone(timezone.utc)
                occurrences.append((occ_utc, occ_utc + dur))
            d = d + timedelta(days=1)

        return occurrences

    # Default: WEEKLY
    interval_weeks = max(1, int(repeat_every_weeks))
    d = start_date_local
    while d <= until_date_local:
        weeks_since_start = (d - start_date_local).days // 7
        if weeks_since_start % interval_weeks == 0 and d.weekday() in py_weekdays:
            occ_local = datetime(
                d.year, d.month, d.day,
                start_local.hour, start_local.minute, start_local.second,
                start_local.microsecond,
                tzinfo=tz,
            )
            occ_utc = occ_local.astimezone(timezone.utc)
            occurrences.append((occ_utc, occ_utc + dur))
        d = d + timedelta(days=1)

    return occurrences


@app.post("/series", response_model=SeriesCreateOut, status_code=status.HTTP_201_CREATED)
def create_series(payload: SeriesIn, db: Session = Depends(get_db)):
    # Generate occurrences first (so we can validate + conflict-check before writing)
    occ = _series_occurrences_utc(
        payload.start,
        payload.end,
        tz_name=payload.tz,
        repeat_days=payload.repeat_days,
        repeat_every_weeks=payload.repeat_every_weeks,
        repeat_until_local=payload.repeat_until,
        freq=payload.freq,
    )
    if not occ:
        raise HTTPException(status_code=400, detail="No occurrences generated (check repeatDays/repeatUntil).")

    min_start = min(s for s, _ in occ)
    max_end   = max(e for _, e in occ)

    # Conflict check against existing events in the full range
    existing = db.scalars(
        select(Event).where(and_(Event.start < max_end, Event.end > min_start))
    ).all()

    conflicts = []
    for s, e in occ:
        for ex in existing:
            if ex.start < e and ex.end > s:
                conflicts.append({
                    "id": ex.id,
                    "title": ex.title,
                    "start": ex.start.isoformat(),
                    "end": ex.end.isoformat(),
                })
                break

    if conflicts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Time overlaps with another event.",
                "conflicts": conflicts[:25],
            },
        )

    # Create series + materialized occurrences as events
    series = RecurrenceSeries(
        title=payload.title,
        start=payload.start,
        end=payload.end,
        tz=payload.tz,
        freq=payload.freq.upper(),
        interval=max(1, int(payload.repeat_every_weeks)),
        byweekday=",".join(str(d) for d in payload.repeat_days) if payload.repeat_days else None,
        until=payload.repeat_until,
        description=payload.description,
        location=payload.location,
        created_at=_utcnow(),
    )
    db.add(series)
    db.flush()  # get series.id

    events: list[Event] = []
    for s, e in occ:
        evt = Event(
            title=payload.title,
            start=s,
            end=e,
            description=payload.description,
            location=payload.location,
            series_id=series.id,
            original_start=s,
            is_exception=False,
        )
        db.add(evt)
        events.append(evt)

    db.commit()
    for evt in events:
        db.refresh(evt)

    return {"seriesId": series.id, "events": events}

# ───────────────────────── Events CRUD & list (range) ───────────────
@app.get("/events", response_model=List[EventOut])
def list_events(
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
):
    stmt = select(Event).order_by(Event.start.asc())
    if start and end:
        stmt = stmt.where(and_(Event.start < end, Event.end > start))
    return db.scalars(stmt).all()


@app.post("/events", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def create_event(payload: EventIn, db: Session = Depends(get_db)):
    overlap_stmt = select(Event).where(and_(Event.start < payload.end, Event.end > payload.start))
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

    evt = Event(**payload.model_dump())
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

    # Capture recurrence linkage before mutation
    series_id = event.series_id
    original_start = event.original_start or event.start

    # Apply updates
    for field, value in payload.model_dump().items():
        setattr(event, field, value)

    # If this event is part of a series, treat any edit as an "override" exception
    if series_id is not None:
        event.original_start = original_start
        event.is_exception = True

        exc = db.scalars(
            select(RecurrenceException).where(
                and_(
                    RecurrenceException.series_id == series_id,
                    RecurrenceException.original_start == original_start,
                )
            )
        ).first()

        if exc is None:
            exc = RecurrenceException(
                series_id=series_id,
                original_start=original_start,
                kind="override",
                created_at=_utcnow(),
            )
            db.add(exc)

        exc.kind = "override"
        exc.override_title = event.title
        exc.override_start = event.start
        exc.override_end = event.end
        exc.override_description = event.description
        exc.override_location = event.location
        exc.created_at = _utcnow()

    db.commit()
    db.refresh(event)
    return event


@app.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: int, db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    # If this is a recurring occurrence, record a skip exception before deletion
    if event.series_id is not None:
        series_id = event.series_id
        original_start = event.original_start or event.start

        exc = db.scalars(
            select(RecurrenceException).where(
                and_(
                    RecurrenceException.series_id == series_id,
                    RecurrenceException.original_start == original_start,
                )
            )
        ).first()

        if exc is None:
            exc = RecurrenceException(
                series_id=series_id,
                original_start=original_start,
                kind="skip",
                created_at=_utcnow(),
            )
            db.add(exc)

        exc.kind = "skip"
        exc.override_title = None
        exc.override_start = None
        exc.override_end = None
        exc.override_description = None
        exc.override_location = None
        exc.created_at = _utcnow()

    db.delete(event)
    db.commit()


# ───────────────────────── ICS export ────────────────────────────────
@app.get("/events.ics")
def export_ics(db: Session = Depends(get_db)):
    cal = Calendar()
    events = db.scalars(select(Event).order_by(Event.start.asc())).all()
    for e in events:
        ics_e = ICSEvent()
        ics_e.name = e.title
        ics_e.begin = e.start
        ics_e.end = e.end
        if getattr(e, "location", None):
            ics_e.location = e.location
        if getattr(e, "description", None):
            ics_e.description = e.description
        cal.events.add(ics_e)

    data = str(cal).encode("utf-8")
    return StreamingResponse(io.BytesIO(data), media_type="text/calendar")


# ───────────────────────── Next-free suggestion ──────────────────────
@app.get("/suggest")
def suggest_next(
    start: datetime = Query(...),
    end: datetime = Query(...),
    db: Session = Depends(get_db),
):
    # Find next free slot of the same duration after (start,end)
    duration = end - start
    cursor = start

    # Look ahead up to 30 days
    for _ in range(0, 30 * 24):
        candidate_start = cursor
        candidate_end = candidate_start + duration

        conflict = db.scalars(
            select(Event).where(and_(Event.start < candidate_end, Event.end > candidate_start))
        ).first()

        if not conflict:
            return {"start": candidate_start.isoformat(), "end": candidate_end.isoformat()}

        cursor = max(cursor, conflict.end)

    raise HTTPException(status_code=404, detail="No free slot found within search window")