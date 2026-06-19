# myheartrisk_router.py

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import database as db
from dependencies import get_db

router = APIRouter(prefix="/api/v1/mhr", tags=["MyHeartRisk"])


# The schema now requires the upstream system to provide the calculated risk
class MHRScreeningCreate(BaseModel):
    patient_id: str = Field(..., description="Unique study ID")
    centre_id: str = Field(..., description="NADI Centre ID")

    # Basic Demographics & Vitals for context
    age: int
    systolic_bp: int
    diastolic_bp: int
    heart_rate: int
    bmi: float
    is_smoker: bool

    # --- PRE-CALCULATED RISK FIELDS ---
    calculated_risk_category: str = Field(
        ..., description="LOW, MODERATE, HIGH, or VERY_HIGH"
    )
    frs_score: Optional[float] = None
    rediscover_score: Optional[float] = None
    referral_triggered: bool = False
    referral_destination: Optional[str] = None


@router.post("/screen", status_code=status.HTTP_201_CREATED)
def process_screening(
    payload: MHRScreeningCreate, db_session: Session = Depends(get_db)
):
    """
    Receives pre-calculated clinical risk datasets and commits them to the database
    so the MyHeartCoach LLM can interpret them later.
    """
    input_data = payload.model_dump()

    try:
        # Save directly to the database using the CRUD function from Phase 1
        record = db.create_mhr_screening(db_session, input_data)

        return {
            "status": "success",
            "screening_id": record.id,
            "message": "Pre-calculated risk securely logged for MyHeartCoach interpretation.",
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database operational failure: {str(e)}",
        )
