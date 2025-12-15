# Cal

### a smart calendar web app (OCR + parsing + scheduling intelligence)

> Drop in a screenshot/PDF or type a plan in plain English.  
> Cal extracts event details, saves them to your calendar, and helps you schedule around

## Table of Contents
- [Background](#background)
- [What It Does](#what-it-does)


## Background
In this day and age, scheduling meetings from seemingly endless types of sources of information with the rise of virtual communication can be time-consuming and painfully mundane, **Cal** turns messy inputs into structured calendar events and adds scheduling helpers like conflict detection, next-free suggestions, and recurring events with exceptions.


## What It Does
### Ingestion & extraction
- **Free-text parsing**: type something like “Dinner Friday 7pm” and get structured fields (title/start/end).
- **Screenshot OCR → event fields**: upload an image; Cal runs OCR, then parses the extracted text into event fields.
- **PDF text extraction → event fields**: upload a PDF; Cal extracts text and parses it into event fields.

### Calendar core
- **Event CRUD** (create/read/update/delete) backed by **PostgreSQL**.
- **Range queries** (fetch events for a week/month window) for calendar views.

### Scheduling intelligence
- **Conflict detection**: prevents overlapping events.
- **Next-free suggestion**: given a proposed time window, Cal finds the next available slot of the same duration.

