import os
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from pypdf import PdfReader
from google import genai
from google.genai import types
from crux.io.db_and_models import SessionLocal, AtsMatchRecord, CruxAtsAnalysisSchema

router = APIRouter(prefix="/api/v1/recruitment")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def extract_text_from_pdf(pdf_file: UploadFile) -> str:
    try:
        reader = PdfReader(pdf_file.file)
        text = ""
        for page in reader.pages:
            content = page.extract_text()
            if content: text += content + "\n"
        return text
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process PDF text: {str(e)}")

@router.post("/parse-match")
async def parse_and_match_candidate(
    verification_id: int = Form(...),
    resume: UploadFile = File(...),
    job_description: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    existing_analysis = db.query(AtsMatchRecord).filter(AtsMatchRecord.verification_id == verification_id).first()
    if existing_analysis:
        raise HTTPException(status_code=400, detail=f"An ATS scoring record is already registered to candidate index: {verification_id}")

    if not (resume.filename.endswith('.pdf') and job_description.filename.endswith('.pdf')):
        raise HTTPException(status_code=400, detail="Both uploaded files must be PDF formats.")

    resume_text = extract_text_from_pdf(resume)
    jd_text = extract_text_from_pdf(job_description)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Gemini API token environment variable is missing.")

    try:
        client = genai.Client(api_key=api_key)
        prompt = f"""
        Extract variables matching the output json schema from the raw candidate data streams.
        
        CRITICAL EVALUATION SYSTEM DIRECTIVES:
        1. Calculate precise employment risk penalties (deltas) out of their max bounds, compute 'employment_raw_score_out_of_100' by subtracting them from 100, and scale to 30% for 'employment_scaled_score_out_of_30'.
        2. Calculate education risk penalties (deltas) out of their max bounds, compute 'education_raw_score_out_of_100' by subtracting them from 100, and scale to 20% for 'education_scaled_score_out_of_20'.
        
        ⚠️ CRITICAL TRANSITION EXEMPTION RULE FOR EMPLOYMENT OVERLAP (delta_overlap):
        If the month and year of leaving one company matches the month and year of joining another company (e.g., Company A ends in 'October 2025' and Company B starts in 'October 2025'), this is a standard career transition. 
        DO NOT treat this single-month overlap as a 'Parallel Contract Overlap' and DO NOT apply a penalty for it under delta_overlap. Only penalize true, ongoing concurrent full-time employment roles.
        
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
        raise HTTPException(status_code=502, detail=f"LLM processing failure: {str(e)}")

    parsed_candidate = structured_analysis.get("parsed_resume", {})
    emp_data = structured_analysis.get("employment_integrity", {})
    edu_data = structured_analysis.get("education_integrity", {})

    db_record = AtsMatchRecord(
        verification_id=verification_id,
        candidate_name=parsed_candidate.get("name"),
        total_years_of_experience=parsed_candidate.get("years_of_experience"),
        parsed_resume_data=parsed_candidate,
        delta_overlap=float(emp_data.get("delta_overlap", 0.0)),
        delta_gap=float(emp_data.get("delta_gap", 0.0)),
        delta_title_inflation=float(emp_data.get("delta_title_inflation", 0.0)),
        delta_corp_registry=float(emp_data.get("delta_corp_registry", 0.0)),
        delta_jd_disparity=float(emp_data.get("delta_jd_disparity", 0.0)),
        s_emp_raw_100=float(emp_data.get("employment_raw_score_out_of_100", 100.0)),
        s_emp_scaled_30=float(emp_data.get("employment_scaled_score_out_of_30", 30.0)),
        employment_explanation=emp_data.get("explanation"),
        delta_overlap_degree=float(edu_data.get("delta_overlap_degree", 0.0)),
        delta_geo_mismatch=float(edu_data.get("delta_geo_mismatch", 0.0)),
        delta_title_standard=float(edu_data.get("delta_title_standard", 0.0)),
        s_edu_raw_100=float(edu_data.get("education_raw_score_out_of_100", 100.0)),
        s_edu_scaled_20=float(edu_data.get("education_scaled_score_out_of_20", 20.0)),
        education_explanation=edu_data.get("explanation"),
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
        "message": "Resume and Job Description processed, scored, and saved to database columns.",
        "db_record_id": db_record.id,
        "ats_analysis_metrics": structured_analysis
    }