import os
import re
import json
from datetime import date
from typing import List, Optional
from fastapi import FastAPI, Request, Depends, HTTPException, UploadFile, File, Form
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import create_engine, Column, Integer, String, Date, Boolean, Float, Text, JSON, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
from pypdf import PdfReader
from google import genai
from google.genai import types

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/identity_db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- 1. IDENTITY VERIFICATION TABLE ---
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
    
    name_match_score = Column(Float, nullable=False)
    national_id_score = Column(Float, nullable=False)
    biometric_score = Column(Float, nullable=False)
    s_id_raw_100 = Column(Float, nullable=False)
    s_id_scaled_25 = Column(Float, nullable=False)
    
    overall_status = Column(String, nullable=False)
    
    # Established Relationship link back to the resume analysis data
    resume_analysis = relationship("AtsMatchRecord", back_populates="identity_profile", uselist=False)


# --- 2. RESUME PARSING TABLE (Linked via Foreign Key) ---
class AtsMatchRecord(Base):
    __tablename__ = "ats_match_records"

    id = Column(Integer, primary_key=True, index=True)
    
    # The glue connecting both APIs: Links strictly to an existing identity record ID
    verification_id = Column(Integer, ForeignKey("identity_verifications.id"), unique=True, nullable=False)
    
    candidate_name = Column(String, nullable=True)
    total_years_of_experience = Column(Float, nullable=True)
    parsed_resume_data = Column(JSON, nullable=False)
    ats_match_analysis = Column(JSON, nullable=False)
    
    identity_profile = relationship("VerificationRecord", back_populates="resume_analysis")


Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app = FastAPI(title="CRUX Unified Identity & Recruitment Pipeline")

# --- PYDANTIC STRUCURED SCHEMAS ---
class IdentityRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, example="Navaneethan GN")
    dob: date = Field(..., example="2000-05-21")
    email: EmailStr = Field(..., example="nav@example.com")
    aadhaar_number: str = Field(..., example="123456789012")
    aadhaar_name: str = Field(..., example="Navaneethan GN")
    aadhaar_valid: bool = Field(..., example=True)
    pan_number: str = Field(..., example="ABCDE1234F")
    pan_name: str = Field(..., example="Navaneethan GN")
    pan_valid: bool = Field(..., example=True)
    uan_number: str = Field(..., example="100200300400")
    uan_name: str = Field(..., example="Navaneethan GN")
    uan_valid: bool = Field(..., example=True)
    is_captured_image_valid: bool = Field(..., example=True)

    @field_validator('aadhaar_number', 'uan_number')
    @classmethod
    def validate_twelve_digit_strings(cls, v: str) -> str:
        if not (v.isdigit() and len(v) == 12):
            raise ValueError('Must be exactly 12 numeric digits.')
        return v

    @field_validator('pan_number')
    @classmethod
    def validate_pan(cls, v: str) -> str:
        v = v.upper()
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$', v):
            raise ValueError('Invalid PAN structural syntax.')
        return v

class WorkExperienceItem(BaseModel):
    employer_name: str
    experience_title: str
    duration: str
    experience_description: str

class EducationItem(BaseModel):
    education_institution_name: str
    degree_title: str
    education_completed_year: str

class ResumeSchema(BaseModel):
    name: str
    years_of_experience: float
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    experience: List[WorkExperienceItem]
    education: List[EducationItem]

class JobDescriptionSchema(BaseModel):
    required_skills: List[str]
    minimum_years_of_experience: float
    role_summary: str

class CruxAtsAnalysisSchema(BaseModel):
    parsed_resume: ResumeSchema
    parsed_jd: JobDescriptionSchema
    semantic_match_percentage: float
    gap_analysis_summary: str


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    field_errors = {}
    for error in exc.errors():
        field_name = error["loc"][-1]
        field_errors[field_name] = {"required": error["type"] == "missing", "message": error["msg"]}
    return JSONResponse(status_code=422, content={"success": False, "errors": field_errors})

def verify_document_name(primary_name: str, doc_name: str) -> bool:
    return primary_name.strip().lower() == doc_name.strip().lower()

def extract_text_from_pdf(pdf_file: UploadFile) -> str:
    try:
        reader = PdfReader(pdf_file.file)
        text = ""
        for page in reader.pages:
            content = page.extract_text()
            if content: text += content + "\n"
        return text
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process text streams from PDF: {str(e)}")


@app.post("/api/v1/identity/verify")
def verify_identity(payload: IdentityRequest, db: Session = Depends(get_db)):
    final_aadhaar_status = payload.aadhaar_valid and verify_document_name(payload.name, payload.aadhaar_name)
    final_pan_status = payload.pan_valid and verify_document_name(payload.name, payload.pan_name)
    final_uan_status = payload.uan_valid and verify_document_name(payload.name, payload.uan_name)

    all_valid = final_aadhaar_status and final_pan_status and final_uan_status and payload.is_captured_image_valid
    overall_status = "VERIFIED" if all_valid else "FAILED"

    name_mismatches = 0
    if not verify_document_name(payload.name, payload.aadhaar_name): name_mismatches += 1
    if not verify_document_name(payload.name, payload.pan_name): name_mismatches += 1
    if not verify_document_name(payload.name, payload.uan_name): name_mismatches += 1
    name_match_score = max(0.0, 100.0 - (name_mismatches * 33.3333))

    registry_failures = 0
    if not payload.aadhaar_valid: registry_failures += 1
    if not payload.pan_valid: registry_failures += 1
    if not payload.uan_valid: registry_failures += 1
    national_id_score = max(0.0, 100.0 - (registry_failures * 33.3333))

    biometric_score = 100.0 if payload.is_captured_image_valid else 0.0

    s_id_raw_100 = round((name_match_score + national_id_score + biometric_score) / 3, 2)
    s_id_scaled_25 = round(s_id_raw_100 * 0.25, 2)

    db_record = VerificationRecord(
        name=payload.name, dob=payload.dob, email=payload.email,
        aadhaar_number=payload.aadhaar_number, aadhaar_name=payload.aadhaar_name, aadhaar_valid=final_aadhaar_status,
        pan_number=payload.pan_number, pan_name=payload.pan_name, pan_valid=final_pan_status,
        uan_number=payload.uan_number, uan_name=payload.uan_name, uan_valid=final_uan_status,
        is_captured_image_valid=payload.is_captured_image_valid,
        name_match_score=round(name_match_score, 2), national_id_score=round(national_id_score, 2),
        biometric_score=biometric_score, s_id_raw_100=s_id_raw_100, s_id_scaled_25=s_id_scaled_25,
        overall_status=overall_status
    )
    db.add(db_record)
    db.commit()
    db.refresh(db_record)

    return {
        "success": all_valid,
        "message": "Identity verification pipeline calculated and saved.",
        "db_record_id": db_record.id,  # <--- CRITICAL ID TO BE PASSED TO NEXT API
        "identity_scoring_matrix": {
            "identity_raw_score_out_of_100": s_id_raw_100,
            "identity_scaled_score_out_of_25": s_id_scaled_25
        }
    }


@app.post("/api/v1/recruitment/parse-match")
async def parse_and_match_candidate(
    verification_id: int = Form(..., description="The db_record_id returned by the Identity Verification API"),
    resume: UploadFile = File(...),
    job_description: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    identity_profile = db.query(VerificationRecord).filter(VerificationRecord.id == verification_id).first()
    if not identity_profile:
        raise HTTPException(status_code=404, detail=f"No verified identity records found tracking ID: {verification_id}. You must verify identity first.")

    existing_analysis = db.query(AtsMatchRecord).filter(AtsMatchRecord.verification_id == verification_id).first()
    if existing_analysis:
        raise HTTPException(status_code=400, detail=f"A resume matching entry is already registered to user profile index: {verification_id}")

    if not (resume.filename.endswith('.pdf') and job_description.filename.endswith('.pdf')):
        raise HTTPException(status_code=400, detail="Both uploaded files must be standard PDF formats.")

    resume_text = extract_text_from_pdf(resume)
    jd_text = extract_text_from_pdf(job_description)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Gemini API token key environment setup variable is missing.")

    try:
        client = genai.Client(api_key=api_key)
        prompt = f"""
        Extract variables matching the output json schema from the raw candidate data streams.
        Ensure to return full links if professional platforms like LinkedIn or open source networks like GitHub are present in the text, otherwise map to null.
        
        [RAW RESUME INPUT]
        {resume_text}
        
        [RAW JD INPUT]
        {jd_text}
        """

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CruxAtsAnalysisSchema,
                temperature=0.0
            ),
        )
        structured_analysis = json.loads(response.text)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM data processing pipeline failure: {str(e)}")

    parsed_candidate = structured_analysis.get("parsed_resume", {})
    db_record = AtsMatchRecord(
        verification_id=verification_id,  # Maps relationship directly
        candidate_name=parsed_candidate.get("name"),
        total_years_of_experience=parsed_candidate.get("years_of_experience"),
        parsed_resume_data=parsed_candidate,
        ats_match_analysis={
            "parsed_jd": structured_analysis.get("parsed_jd"),
            "semantic_match_percentage": structured_analysis.get("semantic_match_percentage"),
            "gap_analysis_summary": structured_analysis.get("gap_analysis_summary")
        }
    )
    db.add(db_record)
    db.commit()
    db.refresh(db_record)

    return {
        "success": True,
        "linked_identity_profile": {
            "profile_id": identity_profile.id,
            "registered_legal_name": identity_profile.name,
            "identity_score_out_of_25": identity_profile.s_id_scaled_25
        },
        "ats_analysis_metrics": structured_analysis
    }