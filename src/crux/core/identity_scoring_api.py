from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from crux.io.db_and_models import SessionLocal, VerificationRecord, IdentityRequest

router = APIRouter(prefix="/api/v1/identity")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def check_name(p_name: str, d_name: str) -> bool:
    return p_name.strip().lower() == d_name.strip().lower()

@router.post("/verify")
def verify_identity(payload: IdentityRequest, db: Session = Depends(get_db)):
    f_aadhaar = payload.aadhaar_valid and check_name(payload.name, payload.aadhaar_name)
    f_pan = payload.pan_valid and check_name(payload.name, payload.pan_name)
    f_uan = payload.uan_valid and check_name(payload.name, payload.uan_name)
    
    all_valid = f_aadhaar and f_pan and f_uan and payload.is_captured_image_valid
    status = "VERIFIED" if all_valid else "FAILED"

    mismatches = sum([not check_name(payload.name, payload.aadhaar_name), 
                      not check_name(payload.name, payload.pan_name), 
                      not check_name(payload.name, payload.uan_name)])
    name_score = round(max(0.0, 100.0 - (mismatches * 33.3333)), 2)

    failures = sum([not payload.aadhaar_valid, not payload.pan_valid, not payload.uan_valid])
    national_score = round(max(0.0, 100.0 - (failures * 33.3333)), 2)

    bio_score = 100.0 if payload.is_captured_image_valid else 0.0
    raw_100 = round((name_score + national_score + bio_score) / 3, 2)
    scaled_25 = round(raw_100 * 0.25, 2)

    record = VerificationRecord(
        name=payload.name, dob=payload.dob, email=payload.email,
        aadhaar_number=payload.aadhaar_number, aadhaar_name=payload.aadhaar_name, aadhaar_valid=f_aadhaar,
        pan_number=payload.pan_number, pan_name=payload.pan_name, pan_valid=f_pan,
        uan_number=payload.uan_number, uan_name=payload.uan_name, uan_valid=f_uan,
        is_captured_image_valid=payload.is_captured_image_valid,
        name_match_score=name_score, national_id_score=national_score, biometric_score=bio_score,
        s_id_raw_100=raw_100, s_id_scaled_25=scaled_25, overall_status=status
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "success": all_valid,
        "message": "Identity verification pipeline processed and scored successfully.",
        "candidate": {"name": payload.name, "dob": str(payload.dob), "email": payload.email},
        "verification_results": {
            "aadhaar": {"number": payload.aadhaar_number, "name": payload.aadhaar_name, "is_valid": f_aadhaar},
            "pan": {"number": payload.pan_number, "name": payload.pan_name, "is_valid": f_pan},
            "uan": {"number": payload.uan_number, "name": payload.uan_name, "is_valid": f_uan},
            "captured_image": {"is_valid": payload.is_captured_image_valid}
        },
        "identity_scoring_matrix": {
            "component_scores_out_of_100": {"name_match_score": name_score, "national_id_score": national_score, "biometric_score": bio_score},
            "identity_raw_score_out_of_100": raw_100,
            "identity_scaled_score_out_of_25": scaled_25
        },
        "overall_identity_status": status,
        "db_record_id": record.id
    }