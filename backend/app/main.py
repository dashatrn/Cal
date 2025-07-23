from fastapi import FastAPI

app = FastAPI(title="Cal API")

@app.get("/health")
def health():
    """Simple heartbeat so you know the server runs."""
    return {"status": "ok"}
