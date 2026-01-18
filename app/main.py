from fastapi import FastAPI

app = FastAPI(
    title="Dev Workflows",
    description="Weekly planning & execution platform for field reps",
    version="0.1.0",
)

@app.get("/")
def root():
    return {"status": "ok", "message": "Dev Workflows API is running"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

