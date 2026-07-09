import os
import re
from typing import Optional, List
from datetime import date
from pydantic import BaseModel, EmailStr, field_validator, Field
from sqlalchemy import create_engine, Column, Integer, String, Date, Boolean, Float, Text, JSON
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/identity_db")

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
    name_match_score = Column(Float, nullable=False)
    national_id_score = Column(Float, nullable=False)
    biometric_score = Column(Float, nullable=False)
    s_id_raw_100 = Column(Float, nullable=False)
    s_id_scaled_25 = Column(Float, nullable=False)
    overall_status = Column(String, nullable=False)

class IdentityRequest(BaseModel):
    name: str
    dob: date
    email: EmailStr
    aadhaar_number: str
    aadhaar_name: str
    aadhaar_valid: bool
    pan_number: str
    pan_name: str
    pan_valid: bool
    uan_number: str
    uan_name: str
    uan_valid: bool
    is_captured_image_valid: bool

    @field_validator('aadhaar_number', 'uan_number')
    @classmethod
    def validate_digits(cls, v: str) -> str:
        if not (v.isdigit() and len(v) == 12):
            raise ValueError('Must be exactly 12 numeric digits.')
        return v

    @field_validator('pan_number')
    @classmethod
    def validate_pan(cls, v: str) -> str:
        v = v.upper()
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$', v):
            raise ValueError('Invalid PAN format layout.')
        return v
    

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/identity_db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class AtsMatchRecord(Base):
    __tablename__ = "ats_match_records"

    id = Column(Integer, primary_key=True, index=True)
    verification_id = Column(Integer, unique=True, nullable=False)
    candidate_name = Column(String, nullable=True)
    total_years_of_experience = Column(Float, nullable=True)
    parsed_resume_data = Column(JSON, nullable=False)
    ats_match_analysis = Column(JSON, nullable=False)
    delta_overlap = Column(Float, nullable=False, default=0.0)
    delta_gap = Column(Float, nullable=False, default=0.0)
    delta_title_inflation = Column(Float, nullable=False, default=0.0)
    delta_corp_registry = Column(Float, nullable=False, default=0.0)
    delta_jd_disparity = Column(Float, nullable=False, default=0.0)
    s_emp_raw_100 = Column(Float, nullable=False)
    s_emp_scaled_30 = Column(Float, nullable=False)
    employment_explanation = Column(Text, nullable=True)
    delta_overlap_degree = Column(Float, nullable=False, default=0.0)
    delta_geo_mismatch = Column(Float, nullable=False, default=0.0)
    delta_title_standard = Column(Float, nullable=False, default=0.0)
    s_edu_raw_100 = Column(Float, nullable=False)
    s_edu_scaled_20 = Column(Float, nullable=False)
    education_explanation = Column(Text, nullable=True)

class EmploymentIntegritySchema(BaseModel):
    delta_overlap: float = Field(..., description="(Check Employment Section Only) Penalty score (0 to 30) for concurrent full-time roles.")
    delta_gap: float = Field(..., description="(Check Employment Section Only) Penalty score (0 to 20) for active gaps in employments without footprints.")
    delta_title_inflation: float = Field(..., description="(Check Employment Section Only) Penalty score (0 to 20) for chronologically implausible leaps in title.")
    delta_corp_registry: float = Field(..., description="(Check Employment Section Only) Penalty score (0 to 15) if employers fail registration checks.")
    delta_jd_disparity: float = Field(..., description="(Check Employment Section Only) Penalty score (0 to 15) if total YOE fails JD baselines.")
    employment_raw_score_out_of_100: float = Field(..., description="Calculate: 100 - sum of above penalties.")
    employment_scaled_score_out_of_30: float = Field(..., description="Calculate: employment_raw_score_out_of_100 * 0.30.")
    explanation: str = Field(..., description="Justification trail explaining details for applied penalties.")

class EducationIntegritySchema(BaseModel):
    delta_overlap_degree: float = Field(..., description="(Check Education Section Only) Penalty score (0 to 40) for concurrent full-time degrees.")
    delta_geo_mismatch: float = Field(..., description="(Check Education Section Only) Penalty score (0 to 30) if campus location conflicts with work records.")
    delta_title_standard: float = Field(..., description="(Check Education Section Only) Penalty score (0 to 30) if institution fails registries.")
    education_raw_score_out_of_100: float = Field(..., description="Calculate: 100 - sum of above penalties.")
    education_scaled_score_out_of_20: float = Field(..., description="Calculate: education_raw_score_out_of_100 * 0.20.")
    explanation: str = Field(..., description="Justification trail explaining details for applied penalties.")

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
    employment_integrity: EmploymentIntegritySchema
    education_integrity: EducationIntegritySchema
    semantic_match_percentage: float
    gap_analysis_summary: str