from typing import Optional

from pydantic import BaseModel, Field



class MHRScreeningCreate(BaseModel):
    patient_id: int = Field(..., description="Unique study ID")
    centre_id: int = Field(..., description="NADI Centre ID")

    # Demographics
    age: int = Field(..., ge=18, le=120)
    sex: str = Field(..., pattern="^(Male|Female)$")
    ethnicity: str = Field(...)
    postcode: str = Field(...)

    # Comoridities
    has_diabetes: bool
    has_hypertension: bool
    has_dyslipidaemia: bool
    prior_cvd: bool

    # Medications
    on_bp_meds: bool
    on_diabetes_meds: bool
    on_statin: bool
    on_antiplatelet: bool

    # Vitals & Lifestyle
    is_smoker: bool
    systolic_bp: int = Field(..., ge=70, le=250)
    diastolic_bp: int = Field(..., ge=40, le=150)
    heart_rate: int = Field(..., ge=30, le=200)
    bmi: float = Field(..., ge=10, le=60)

    # Optional Labs
    cholesterol_total: Optional[float] = None
    glucose_fasting: Optional[float] = None

    # Consents
    nudge_consent: bool = True
    chatbot_consent: bool = True
