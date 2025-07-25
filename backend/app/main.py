# app/main.py

''' 
import Fast API to create web routes (GET/POST)
Depends: handles dependency injection, auto plugging in database when necessary
Get a database session for each request
select from database table, makes queries like SELECT * FROM events
in a clean way
'''
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select

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

# Creates API
app = FastAPI(title="Cal API")


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


#https://silver-goldfish-44r7x5x9qg5255jv-8000.app.github.dev/health



'''
backend route, sits on server waiting for GET request to /events. request comes from React frontend. 
When react code runs, send get request here.
Receving get request, sends from database. 
select(Event) = Give all rows from events table
db.scalars(...).all() - Turn that into a list of event objects
FastAPI autoconverst into JSON
sends back to frontend
events are stored in SQLite database file on server

The website requests the events, 
events live in database
backend is middle layer speaks to db and internet
'''

@app.get("/events", response_model=list[EventOut])
def list_events(db: Session = Depends(get_db)):
    return db.scalars(select(Event)).all()






@app.post("/events", response_model=EventOut, status_code=201)
def create_event(data: EventIn, db: Session = Depends(get_db)):
    evt = Event(**data.model_dump())
    db.add(evt)
    db.commit()
    db.refresh(evt)
    return evt