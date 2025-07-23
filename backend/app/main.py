# app/main.py


'''bringing in FastAPI tools (Depends, FastAPI) and SQL
 tools (Session, select) for DB interaction.
'''

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select


app = FastAPI(title="Cal API")


# runs when app starts and creats table if it doesn't existyet
@app.on_event("startup")
def init_db() -> None:
    Base.metadata.create_all(bind=engine)

#simple check to confirm server running
@app.get("/health")
def health_check():
    return {"status": "ok"}



#https://silver-goldfish-44r7x5x9qg5255jv-8000.app.github.dev/health




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