from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from crux.io.db_and_models import engine, Base
from crux.core.identity_scoring_api import router as identity_router
from crux.core.parse_resume_api import router as resume_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="CRUX Unified Gateway Pipeline",
              description="Unified API interface combining Phase 2 Identity Validation and Phase 3/4 Resume Parsing.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = {err["loc"][-1]: {"required": err["type"] == "missing", "message": err["msg"]} for err in exc.errors()}
    return JSONResponse(status_code=422, content={"success": False, "message": "Validation failed.", "errors": errors})

app.include_router(identity_router, prefix="/identity-service")
app.include_router(resume_router, prefix="/recruitment-service")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)