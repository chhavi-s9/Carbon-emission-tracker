"""Unit tests for the carbon calculation and recommendation engine."""

import pytest
from carbon_engine import (
    DailyEntry,
    calculate_emissions,
    generate_insights,
    generate_ai_insights,
    yearly_projection,
)


def test_calculate_emissions_basic():
    entry = DailyEntry(
        date="2026-06-15",
        transport_mode="car_petrol",
        transport_km=10,
        electricity_kwh=5,
        meat_meals=1,
        veg_meals=2,
        flight_km=0,
        recycled=False,
    )
    result = calculate_emissions(entry)

    assert result["transport"] == pytest.approx(1.92, rel=1e-3)
    assert result["electricity"] == pytest.approx(4.1, rel=1e-3)
    assert result["diet"] == pytest.approx(6.3, rel=1e-3)
    assert result["flights"] == 0
    assert result["recycling_saving"] == 0
    assert result["total"] == pytest.approx(12.32, rel=1e-3)


def test_recycling_reduces_total():
    base = DailyEntry(
        date="2026-06-15", transport_mode="bicycle_walk", transport_km=0,
        electricity_kwh=1, meat_meals=0, veg_meals=1, recycled=False,
    )
    recycled = DailyEntry(
        date="2026-06-15", transport_mode="bicycle_walk", transport_km=0,
        electricity_kwh=1, meat_meals=0, veg_meals=1, recycled=True,
    )
    assert calculate_emissions(recycled)["total"] < calculate_emissions(base)["total"]


def test_total_never_negative():
    entry = DailyEntry(
        date="2026-06-15", transport_mode="bicycle_walk", transport_km=0,
        electricity_kwh=0, meat_meals=0, veg_meals=0, recycled=True,
    )
    assert calculate_emissions(entry)["total"] == 0


def test_generate_insights_empty_history():
    assert generate_insights([]) == []


def test_generate_insights_flags_high_transport():
    history = [{
        "transport": 5.0, "electricity": 1.0, "diet": 2.0,
        "flights": 0.0, "total": 8.0, "recycling_saving": 0.6,
    }]
    insights = generate_insights(history)
    categories = [r["category"] for r in insights]
    assert "transport" in categories


def test_generate_insights_positive_reinforcement():
    history = [{
        "transport": 0.5, "electricity": 1.0, "diet": 2.0,
        "flights": 0.0, "total": 3.5, "recycling_saving": 0.6,
    }]
    insights = generate_insights(history)
    assert insights[0]["category"] == "general"


def test_yearly_projection():
    assert yearly_projection(5.0) == pytest.approx(1825.0)


def test_generate_ai_insights_empty_history_returns_empty_string():
    # No network call: the function short-circuits before touching the API.
    assert generate_ai_insights([], "fake-key") == ""


def test_generate_ai_insights_without_api_key_is_graceful():
    # No network call: missing key is checked before any API client is built.
    message = generate_ai_insights([{"total": 5}], None)
    assert message.startswith("⚠️")
    assert "API key" in message