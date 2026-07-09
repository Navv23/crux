import os
import re
from datetime import date
from typing import Optional
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import create_engine, Column, Integer, String, Date, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, Session

DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/identity_db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class VerificationRecord(Base):
    __tablename__ = "identity_verifications"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    dob = Column(Date, nullable=False)
    email = Column(String, nullable=False)
    
    aadhaar_number = Column(String, nullable=False)
    aadhaar_name = Column(String, nullable=False)
    aadhaar_valid = Column(Boolean, nullable=False)
    
    pan_number = Column(String, nullable=False)
    pan_name = Column(String, nullable=False)
    pan_valid = Column(Boolean, nullable=False)
    
    uan_number = Column(String, nullable=False)
    uan_name = Column(String, nullable=False)
    uan_valid = Column(Boolean, nullable=False)
    
    is_captured_image_valid = Column(Boolean, nullable=False)
    
    overall_status = Column(String, nullable=False)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app = FastAPI(title="CRUX Identity Verification API")

class IdentityRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, example="Navaneethan GN")
    dob: date = Field(..., example="2000-05-21")
    email: EmailStr = Field(..., example="nav@example.com")
    
    aadhaar_number: str = Field(..., example="123456789012")
    aadhaar_name: str = Field(..., example="Navaneethan GN")
    aadhaar_valid: bool = Field(..., description="Client passed validity status for Aadhaar", example=True)
    
    pan_number: str = Field(..., example="ABCDE1234F")
    pan_name: str = Field(..., example="Navaneethan GN")
    pan_valid: bool = Field(..., description="Client passed validity status for PAN", example=True)
    
    uan_number: str = Field(..., example="100200300400")
    uan_name: str = Field(..., example="Navaneethan GN")
    uan_valid: bool = Field(..., description="Client passed validity status for UAN", example=True)
    
    is_captured_image_valid: bool = Field(..., description="Client passed status showing if face matches the document photo", example=True)

    @field_validator('aadhaar_number')
    @classmethod
    def validate_aadhaar(cls, v: str) -> str:
        if not (v.isdigit() and len(v) == 12):
            raise ValueError('Aadhaar number must be exactly 12 digits.')
        return v

    @field_validator('pan_number')
    @classmethod
    def validate_pan(cls, v: str) -> str:
        v = v.upper()
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$', v):
            raise ValueError('Invalid PAN format. Must match standard Indian PAN layout (e.g., ABCDE1234F).')
        return v

    @field_validator('uan_number')
    @classmethod
    def validate_uan(cls, v: str) -> str:
        if not (v.isdigit() and len(v) == 12):
            raise ValueError('UAN must be exactly 12 numeric digits.')
        return v


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    field_errors = {}
    for error in exc.errors():
        field_name = error["loc"][-1]
        field_errors[field_name] = {"required": error["type"] == "missing", "message": error["msg"]}

    return JSONResponse(
        status_code=422,
        content={"success": False, "message": "Validation failed.", "errors": field_errors}
    )


def verify_document_name(primary_name: str, doc_name: str) -> bool:
    return primary_name.strip().lower() == doc_name.strip().lower()


@app.post("/api/v1/identity/verify")
def verify_identity(payload: IdentityRequest, db: Session = Depends(get_db)):
    
    final_aadhaar_status = payload.aadhaar_valid and verify_document_name(payload.name, payload.aadhaar_name)
    final_pan_status = payload.pan_valid and verify_document_name(payload.name, payload.pan_name)
    final_uan_status = payload.uan_valid and verify_document_name(payload.name, payload.uan_name)

    all_valid = final_aadhaar_status and final_pan_status and final_uan_status and payload.is_captured_image_valid
    overall_status = "VERIFIED" if all_valid else "FAILED"

    db_record = VerificationRecord(
        name=payload.name,
        dob=payload.dob,
        email=payload.email,
        aadhaar_number=payload.aadhaar_number,
        aadhaar_name=payload.aadhaar_name,
        aadhaar_valid=final_aadhaar_status,
        pan_number=payload.pan_number,
        pan_name=payload.pan_name,
        pan_valid=final_pan_status,
        uan_number=payload.uan_number,
        uan_name=payload.uan_name,
        uan_valid=final_uan_status,
        is_captured_image_valid=payload.is_captured_image_valid,
        overall_status=overall_status,
    )
    db.add(db_record)
    db.commit()
    db.refresh(db_record)

    return {
        "success": all_valid,
        "message": "Identity verification pipeline processed and saved.",
        "candidate": {
            "name": payload.name,
            "dob": str(payload.dob),
            "email": payload.email
        },
        "verification_results": {
            "aadhaar": {
                "number": payload.aadhaar_number,
                "name": payload.aadhaar_name,
                "is_valid": final_aadhaar_status
            },
            "pan": {
                "number": payload.pan_number,
                "name": payload.pan_name,
                "is_valid": final_pan_status
            },
            "uan": {
                "number": payload.uan_number,
                "name": payload.uan_name,
                "is_valid": final_uan_status
            },
            "captured_image": {
                "is_valid": payload.is_captured_image_valid
            }
        },
        "overall_identity_status": overall_status,
        "db_record_id": db_record.id
    }