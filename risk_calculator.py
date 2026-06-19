import math
from typing import Any, Dict, Optional

# =====================================================================
# CORE ALGORITHMS
# Note: The precise coefficients for REDISCOVER and the local NCVD
# Registry calibrations must be injected here by your biostats team.
# =====================================================================


def calculate_framingham_risk(
    age: int,
    sex: str,
    systolic_bp: int,
    is_smoker: bool,
    has_diabetes: bool,
    on_bp_meds: bool,
    bmi: float,
    cholesterol_total: Optional[float] = None,
) -> float:
    """
    Calculates the Framingham 10-Year General Cardiovascular Disease Risk.
    Utilizes the BMI-based lipid-independent model if cholesterol is not provided.
    """
    # Baseline survival and coefficient sums (Example structure for 2008 General CVD BMI model)
    risk_score = 0.0

    if sex.lower() == "female":
        # Female Coefficients
        terms = (
            2.72107 * math.log(age)
            + 0.51125 * math.log(bmi)
            + (
                2.81291 * math.log(systolic_bp)
                if not on_bp_meds
                else 2.88267 * math.log(systolic_bp)
            )
            + (0.61868 if is_smoker else 0.0)
            + (0.77763 if has_diabetes else 0.0)
        )
        baseline_survival = 0.94833
        mean_terms = 26.0145
    else:
        # Male Coefficients
        terms = (
            3.11296 * math.log(age)
            + 0.79277 * math.log(bmi)
            + (
                1.85508 * math.log(systolic_bp)
                if not on_bp_meds
                else 1.92672 * math.log(systolic_bp)
            )
            + (0.70953 if is_smoker else 0.0)
            + (0.53160 if has_diabetes else 0.0)
        )
        baseline_survival = 0.88431
        mean_terms = 23.9388

    # Calculate final percentage
    risk_prob = 1.0 - math.pow(baseline_survival, math.exp(terms - mean_terms))
    return round(risk_prob * 100, 2)


def calculate_rediscover_risk(
    age: int, sex: str, systolic_bp: int, is_smoker: bool, has_diabetes: bool
) -> float:
    """
    Calculates the Malaysian REDISCOVER risk score.
    (Placeholder algorithmic structure: Inject exact REDISCOVER primary cohort coefficients here)
    """
    # A structural stub representing the REDISCOVER cohort weighting
    base_weight = 0.15 * age
    if is_smoker:
        base_weight += 3.5
    if has_diabetes:
        base_weight += 5.2
    if systolic_bp > 140:
        base_weight += 4.0

    return round(min(base_weight, 100.0), 2)


# =====================================================================
# PROTOCOL CLASSIFICATION & ROUTING
# Implements the MyHeartRisk-NADI Project Workflow flowchart.
# =====================================================================


def evaluate_mhr_protocol(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes the structural logic paths mandated by the NADI Protocol Workflow.
    Returns the calculated scores, risk category, and referral triggers.
    """

    # Layer 1: ACS Pathway Interception
    # Protocol Workflow: Heart Attack History? YES -> ACS Pathway -> High Risk
    if data.get("prior_cvd"):
        return {
            "frs_score": None,
            "rediscover_score": None,
            "acs_risk_score": 99.9,  # Arbitrary flag for ACS bypass
            "calculated_risk_category": "VERY_HIGH",
            "referral_triggered": True,
            "referral_destination": "Hospital Outpatient Clinic / Emergency Department",
        }

    # Layer 2: Compute FRS & REDISCOVER (Heart Attack History? NO)
    frs_score = calculate_framingham_risk(
        age=data["age"],
        sex=data["sex"],
        systolic_bp=data["systolic_bp"],
        is_smoker=data["is_smoker"],
        has_diabetes=data["has_diabetes"],
        on_bp_meds=data["on_bp_meds"],
        bmi=data["bmi"],
        cholesterol_total=data.get("cholesterol_total"),
    )

    rediscover_score = calculate_rediscover_risk(
        age=data["age"],
        sex=data["sex"],
        systolic_bp=data["systolic_bp"],
        is_smoker=data["is_smoker"],
        has_diabetes=data["has_diabetes"],
    )

    # Layer 3: Highest-Risk Referral Rule
    # Referral should be triggered if participant has high MyHeartRisk OR high FRS category

    # Define arbitrary clinical cutoffs for the trial (Adjust these to match exact clinical definitions)
    frs_high_cutoff = 20.0
    rediscover_high_cutoff = 15.0

    is_high_frs = frs_score >= frs_high_cutoff
    is_high_rediscover = rediscover_score >= rediscover_high_cutoff

    if is_high_frs or is_high_rediscover or data["systolic_bp"] >= 180:
        category = (
            "HIGH" if (frs_score < 30.0 and rediscover_score < 25.0) else "VERY_HIGH"
        )
        referral = True
        destination = "Klinik Kesihatan / GP Clinic"
    elif frs_score >= 10.0 or rediscover_score >= 8.0:
        category = "MODERATE"
        referral = False
        destination = None
    else:
        category = "LOW"
        referral = False
        destination = None

    return {
        "frs_score": frs_score,
        "rediscover_score": rediscover_score,
        "acs_risk_score": None,
        "calculated_risk_category": category,
        "referral_triggered": referral,
        "referral_destination": destination,
    }
