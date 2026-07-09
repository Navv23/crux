import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import the standalone FastAPI application instances from your two separate files
from crux.core.identity_scoring_api import app as identity_subapp
from crux.core.parse_resume_api import app as resume_subapp

# 1. Initialize the master gateway application instance
app = FastAPI(
    title="CRUX Unified Gateway Pipeline",
    description="Unified API interface combining Phase 2 Identity Validation and Phase 3/4 Resume Parsing."
)

# 2. Optional: Add global CORS middleware to allow your React frontend to communicate with both sub-apps
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this to your specific React port (e.g., ["http://localhost:5173"]) in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Mount the independent apps as Sub-Applications onto the master port
app.mount("/identity-service", identity_subapp)
app.mount("/recruitment-service", resume_subapp)

if __name__ == "__main__":
    import uvicorn
    # Automatically boots up the master gateway on port 8000
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
    
    
    