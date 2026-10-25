from fastapi import FastAPI

app = FastAPI(title="api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
