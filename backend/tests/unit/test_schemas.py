import pytest
from pydantic import ValidationError

from app.api.schemas import RecommendationRequest, Weights


def test_valid_request_parses(valid_request):
    assert RecommendationRequest.model_validate(valid_request).confidence == 0.95


def test_weights_renormalise_to_one():
    w = Weights(time=1, cost=1, carbon=0, accessibility=0).normalised()
    assert w.time == pytest.approx(0.5)
    assert w.time + w.cost + w.carbon + w.accessibility == pytest.approx(1.0)


def test_all_zero_weights_rejected():
    with pytest.raises(ValidationError):
        Weights(time=0, cost=0, carbon=0, accessibility=0)


@pytest.mark.parametrize("arrive_by", ["2026-10-17T11:00:00+01:00", "2026-11-30T09:00:00+00:00", "2026-10-19T09:00:00"])
def test_arrive_by_must_be_future_within_7_days_with_offset(valid_request, arrive_by):
    valid_request["arrive_by"] = arrive_by
    with pytest.raises(ValidationError):
        RecommendationRequest.model_validate(valid_request)


@pytest.mark.parametrize("c", [0.49, 1.0])
def test_confidence_bounds(valid_request, c):
    valid_request["confidence"] = c
    with pytest.raises(ValidationError):
        RecommendationRequest.model_validate(valid_request)


def test_unknown_fields_rejected(valid_request):
    valid_request["surprise"] = 1
    with pytest.raises(ValidationError):
        RecommendationRequest.model_validate(valid_request)
