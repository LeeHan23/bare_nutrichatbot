"""Unit test for database.get_effective_personalization_level() — the shared
helper that lets a dietitian-set Patient.personalization_level win, falling
back to the My Heart Coach staging DB's users.risk_level (see myheart_db.py
and docs/state_machine_contract.md) only when unset. Mocks myheart_db so it
runs offline, no live DB needed."""
from unittest.mock import patch

import database as db


class _FakePatient:
    def __init__(self, personalization_level=None, phone_number=None, onboarding_stage=None):
        self.personalization_level = personalization_level
        self.phone_number = phone_number
        self.onboarding_stage = onboarding_stage


def test_dietitian_set_value_wins_no_staging_lookup():
    with patch("myheart_db.get_myheart_risk_level") as mocked:
        result = db.get_effective_personalization_level(
            _FakePatient(personalization_level="L3", phone_number="+60170000001")
        )
        assert result == "L3"
        mocked.assert_not_called()


def test_falls_back_to_staging_db_when_unset():
    with patch("myheart_db.get_myheart_risk_level", return_value="L2") as mocked:
        result = db.get_effective_personalization_level(
            _FakePatient(personalization_level=None, phone_number="+60170000001")
        )
        assert result == "L2"
        mocked.assert_called_once_with("+60170000001")


def test_no_match_returns_none():
    with patch("myheart_db.get_myheart_risk_level", return_value=None):
        result = db.get_effective_personalization_level(
            _FakePatient(personalization_level=None, phone_number=None)
        )
        assert result is None


def test_hand_set_onboarding_stage_wins_no_staging_lookup():
    with patch("myheart_db.get_myheart_onboarding_stage") as mocked:
        result = db.get_effective_onboarding_stage(
            _FakePatient(onboarding_stage="OB2", phone_number="+60170000001")
        )
        assert result == "OB2"
        mocked.assert_not_called()


def test_onboarding_stage_falls_back_to_staging_db_when_unset():
    with patch("myheart_db.get_myheart_onboarding_stage", return_value="OB3") as mocked:
        result = db.get_effective_onboarding_stage(
            _FakePatient(onboarding_stage=None, phone_number="+60170000001")
        )
        assert result == "OB3"
        mocked.assert_called_once_with("+60170000001")
