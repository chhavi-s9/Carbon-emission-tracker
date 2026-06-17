"""
Core calculation and recommendation engine for the Carbon Footprint Coach.

Emission factors are approximate, sourced from publicly published averages
(DEFRA 2023 conversion factors, IPCC AR6 dietary estimates, CEA India grid
emission factor). They are intended for awareness and behaviour change, not
for regulatory or accounting use — see README for assumptions.
"""

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Emission factors (kg CO2e)
# ---------------------------------------------------------------------------

TRANSPORT_FACTORS = {
    "car_petrol": 0.192,
    "car_diesel": 0.171,
    "car_cng": 0.118,
    "two_wheeler": 0.083,
    "bus": 0.105,
    "metro_train": 0.041,
    "ev_car": 0.053,
    "bicycle_walk": 0.0,
}

TRANSPORT_LABELS = {
    "car_petrol": "Petrol car",
    "car_diesel": "Diesel car",
    "car_cng": "CNG car",
    "two_wheeler": "Two-wheeler",
    "bus": "Bus",
    "metro_train": "Metro / train",
    "ev_car": "Electric car",
    "bicycle_walk": "Bicycle / walk",
}

ELECTRICITY_FACTOR = 0.82  # kg CO2e per kWh (India grid average)

DIET_FACTORS = {
    "meat_meal": 3.3,
    "veg_meal": 1.5,
}

FLIGHT_FACTOR = 0.15  # kg CO2e per passenger-km
RECYCLING_DAILY_SAVING = 0.6  # kg CO2e/day from active recycling & composting

BENCHMARKS_KG_PER_DAY = {
    "india_average": 5.0,
    "global_average": 11.0,
    "paris_aligned_2030": 6.8,  # ~2.5 t/year per capita target
}


@dataclass
class DailyEntry:
    date: str
    transport_mode: str
    transport_km: float
    electricity_kwh: float
    meat_meals: int
    veg_meals: int
    flight_km: float = 0.0
    recycled: bool = False


def calculate_emissions(entry: DailyEntry) -> dict:
    """Return a breakdown of kg CO2e by category plus a total for one day."""
    transport = entry.transport_km * TRANSPORT_FACTORS.get(entry.transport_mode, 0)
    electricity = entry.electricity_kwh * ELECTRICITY_FACTOR
    diet = (
        entry.meat_meals * DIET_FACTORS["meat_meal"]
        + entry.veg_meals * DIET_FACTORS["veg_meal"]
    )
    flights = entry.flight_km * FLIGHT_FACTOR
    saving = RECYCLING_DAILY_SAVING if entry.recycled else 0.0

    total = max(0.0, transport + electricity + diet + flights - saving)

    return {
        "transport": round(transport, 2),
        "electricity": round(electricity, 2),
        "diet": round(diet, 2),
        "flights": round(flights, 2),
        "recycling_saving": round(saving, 2),
        "total": round(total, 2),
    }


ACTION_LIBRARY = [
    {"id": "carpool", "label": "Carpool or use public transit twice a week",
     "category": "transport", "saving_kg_year": 250},
    {"id": "led", "label": "Switch to LED bulbs throughout the home",
     "category": "electricity", "saving_kg_year": 80},
    {"id": "solar_water", "label": "Use a solar water heater",
     "category": "electricity", "saving_kg_year": 300},
    {"id": "meatless_days", "label": "Have 2 meat-free days every week",
     "category": "diet", "saving_kg_year": 190},
    {"id": "compost", "label": "Compost kitchen waste and recycle dry waste daily",
     "category": "waste", "saving_kg_year": 220},
    {"id": "ac_temp", "label": "Set AC to 24-26C instead of 18-20C",
     "category": "electricity", "saving_kg_year": 140},
    {"id": "ev_switch", "label": "Switch your next vehicle to electric",
     "category": "transport", "saving_kg_year": 600},
    {"id": "unplug", "label": "Unplug devices and use smart power strips",
     "category": "electricity", "saving_kg_year": 45},
]


def generate_insights(history: list[dict]) -> list[dict]:
    """
    Generate prioritized, context-aware recommendations from logged history.

    Decision logic:
      - High average transport emissions -> suggest public transit / carpooling
      - High average electricity use -> suggest efficiency measures
      - Meat-heavy diet pattern -> suggest meat-free days
      - Any flights logged -> suggest trip consolidation / offsetting
      - Inconsistent recycling -> suggest making it a daily habit
      - If footprint already below national average and no issues -> positive reinforcement

    Recommendations are sorted by estimated annual savings, highest first.
    """
    if not history:
        return []

    n = len(history)
    avg = {
        "transport": sum(h["transport"] for h in history) / n,
        "electricity": sum(h["electricity"] for h in history) / n,
        "diet": sum(h["diet"] for h in history) / n,
        "flights": sum(h["flights"] for h in history) / n,
        "total": sum(h["total"] for h in history) / n,
    }

    recs = []

    if avg["transport"] > 2.0:
        recs.append({
            "category": "transport",
            "title": "High transport emissions",
            "message": (
                "Your daily commute is the biggest single contributor. "
                "Replacing two car trips a week with bus, metro, or carpooling "
                "can meaningfully cut this category."
            ),
            "saving_kg_year": 250,
        })

    if avg["electricity"] > 3.5:
        recs.append({
            "category": "electricity",
            "title": "Electricity use above average",
            "message": (
                "Your household electricity footprint is higher than typical. "
                "LED lighting, efficient appliances, and setting the AC to "
                "24-26C reduce this without much impact on comfort."
            ),
            "saving_kg_year": 220,
        })

    if avg["diet"] > 6.0:
        recs.append({
            "category": "diet",
            "title": "Meat-heavy diet pattern",
            "message": (
                "Most of your logged meals include meat. Swapping in two "
                "plant-based meals a week is one of the highest-impact, "
                "lowest-effort changes available."
            ),
            "saving_kg_year": 190,
        })

    if avg["flights"] > 0:
        recs.append({
            "category": "flights",
            "title": "Air travel detected",
            "message": (
                "Flights logged in your history contribute a large amount per "
                "trip. Consider combining trips, choosing direct routes, or "
                "offsetting through a verified program."
            ),
            "saving_kg_year": 150,
        })

    recycling_days = sum(1 for h in history if h.get("recycling_saving", 0) > 0)
    if recycling_days / n < 0.5:
        recs.append({
            "category": "waste",
            "title": "Low recycling consistency",
            "message": (
                "You're recycling or composting on less than half the days "
                "you've logged. Making it a daily habit adds up significantly "
                "over a year."
            ),
            "saving_kg_year": 220,
        })

    if avg["total"] < BENCHMARKS_KG_PER_DAY["india_average"] and not recs:
        recs.append({
            "category": "general",
            "title": "You're doing great",
            "message": (
                "Your footprint is already below the national average. "
                "Keep up your current habits, and check the Action Tracker "
                "for your next stretch goal."
            ),
            "saving_kg_year": 0,
        })

    recs.sort(key=lambda r: r["saving_kg_year"], reverse=True)
    return recs


def yearly_projection(avg_daily_kg: float) -> float:
    """Project a daily average (kg CO2e) to an annual figure."""
    return round(avg_daily_kg * 365, 1)