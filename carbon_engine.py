"""
Core calculation and recommendation engine for the Carbon Footprint Coach.

Emission factors are approximate, sourced from publicly published averages
(DEFRA 2023 conversion factors, IPCC AR6 dietary estimates, CEA India grid
emission factor). They are intended for awareness and behaviour change, not
for regulatory or accounting use — see README for assumptions.

Module layout (constants first so every function can safely reference them):
  1. Constants & emission factors
  2. DailyEntry dataclass
  3. calculate_emissions()
  4. generate_insights()        ← rule-based, instant, no API call
  5. build_history_summary()    ← formats data for the Claude prompt
  6. generate_ai_insights()     ← calls Claude API, returns text
  7. ACTION_LIBRARY
  8. yearly_projection()
"""

from dataclasses import dataclass
import anthropic


# ---------------------------------------------------------------------------
# 1. Constants & emission factors (kg CO2e)
# ---------------------------------------------------------------------------
# Defined first so every function below can safely reference them.

TRANSPORT_FACTORS = {
    "car_petrol":   0.192,
    "car_diesel":   0.171,
    "car_cng":      0.118,
    "two_wheeler":  0.083,
    "bus":          0.105,
    "metro_train":  0.041,
    "ev_car":       0.053,
    "bicycle_walk": 0.0,
}

TRANSPORT_LABELS = {
    "car_petrol":   "Petrol car",
    "car_diesel":   "Diesel car",
    "car_cng":      "CNG car",
    "two_wheeler":  "Two-wheeler",
    "bus":          "Bus",
    "metro_train":  "Metro / train",
    "ev_car":       "Electric car",
    "bicycle_walk": "Bicycle / walk",
}

ELECTRICITY_FACTOR     = 0.82  # kg CO2e per kWh (India CEA grid average)
FLIGHT_FACTOR          = 0.15  # kg CO2e per passenger-km
RECYCLING_DAILY_SAVING = 0.60  # kg CO2e saved per day by recycling/composting

DIET_FACTORS = {
    "meat_meal": 3.3,
    "veg_meal":  1.5,
}

BENCHMARKS_KG_PER_DAY = {
    "india_average":       5.0,
    "global_average":     11.0,
    "paris_aligned_2030":  6.8,   # ≈ 2.5 t CO2e/year per capita
}

# AI coaching (section 6) configuration, kept separate from physical
# emission factors above for clarity.
AI_MODEL      = "claude-sonnet-4-6"
AI_MAX_TOKENS = 512


# ---------------------------------------------------------------------------
# 2. DailyEntry dataclass
# ---------------------------------------------------------------------------

@dataclass
class DailyEntry:
    date:            str
    transport_mode:  str
    transport_km:    float
    electricity_kwh: float
    meat_meals:      int
    veg_meals:       int
    flight_km:       float = 0.0
    recycled:        bool  = False


# ---------------------------------------------------------------------------
# 3. calculate_emissions
# ---------------------------------------------------------------------------

def calculate_emissions(entry: DailyEntry) -> dict:
    """Return a per-category and total kg CO2e breakdown for one logged day."""
    transport   = entry.transport_km * TRANSPORT_FACTORS.get(entry.transport_mode, 0)
    electricity = entry.electricity_kwh * ELECTRICITY_FACTOR
    diet        = (entry.meat_meals * DIET_FACTORS["meat_meal"]
                   + entry.veg_meals * DIET_FACTORS["veg_meal"])
    flights     = entry.flight_km * FLIGHT_FACTOR
    saving      = RECYCLING_DAILY_SAVING if entry.recycled else 0.0
    total       = max(0.0, transport + electricity + diet + flights - saving)

    return {
        "transport":        round(transport,   2),
        "electricity":      round(electricity, 2),
        "diet":             round(diet,        2),
        "flights":          round(flights,     2),
        "recycling_saving": round(saving,      2),
        "total":            round(total,       2),
    }


# ---------------------------------------------------------------------------
# 4. generate_insights  ← rule-based quick analysis (no API call)
# ---------------------------------------------------------------------------

def generate_insights(history: list[dict]) -> list[dict]:
    """
    Generate prioritized recommendations from logged history using
    rule-based thresholds. Runs instantly with no API call, so the
    Insights page always has something to show even without a key.

    Sorted by estimated annual CO2e saving, highest first.
    """
    if not history:
        return []

    n = len(history)
    avg = {
        "transport":   sum(h["transport"]   for h in history) / n,
        "electricity": sum(h["electricity"] for h in history) / n,
        "diet":        sum(h["diet"]        for h in history) / n,
        "flights":     sum(h["flights"]     for h in history) / n,
        "total":       sum(h["total"]       for h in history) / n,
    }

    recs = []

    if avg["transport"] > 2.0:
        recs.append({
            "category": "transport",
            "title":    "High transport emissions",
            "message":  (
                "Your daily commute is the biggest single contributor. "
                "Replacing two car trips a week with bus, metro, or carpooling "
                "can meaningfully cut this category."
            ),
            "saving_kg_year": 250,
        })

    if avg["electricity"] > 3.5:
        recs.append({
            "category": "electricity",
            "title":    "Electricity use above average",
            "message":  (
                "Your household electricity footprint is higher than typical. "
                "LED lighting, efficient appliances, and setting the AC to "
                "24–26 °C reduce this without much impact on comfort."
            ),
            "saving_kg_year": 220,
        })

    if avg["diet"] > 6.0:
        recs.append({
            "category": "diet",
            "title":    "Meat-heavy diet pattern",
            "message":  (
                "Most of your logged meals include meat. Swapping in two "
                "plant-based meals a week is one of the highest-impact, "
                "lowest-effort changes available."
            ),
            "saving_kg_year": 190,
        })

    if avg["flights"] > 0:
        recs.append({
            "category": "flights",
            "title":    "Air travel detected",
            "message":  (
                "Flights logged in your history contribute a large amount per "
                "trip. Consider combining trips, choosing direct routes, or "
                "offsetting through a verified programme."
            ),
            "saving_kg_year": 150,
        })

    recycle_days = sum(1 for h in history if h.get("recycling_saving", 0) > 0)
    if recycle_days / n < 0.5:
        recs.append({
            "category": "waste",
            "title":    "Low recycling consistency",
            "message":  (
                "You're recycling or composting on fewer than half the days "
                "you've logged. Making it a daily habit adds up significantly "
                "over a year."
            ),
            "saving_kg_year": 220,
        })

    # Positive reinforcement when no issues are found
    if not recs and avg["total"] < BENCHMARKS_KG_PER_DAY["india_average"]:
        recs.append({
            "category": "general",
            "title":    "You're doing great",
            "message":  (
                "Your footprint is already below the national average. "
                "Keep up your current habits, and check the Action Tracker "
                "for your next stretch goal."
            ),
            "saving_kg_year": 0,
        })

    recs.sort(key=lambda r: r["saving_kg_year"], reverse=True)
    return recs


# ---------------------------------------------------------------------------
# 5. build_history_summary  ← formats user data for the Claude prompt
# ---------------------------------------------------------------------------

def build_history_summary(history: list[dict]) -> str:
    """
    Convert raw history records into a concise plain-English paragraph
    to send as the user message in the Claude API call.

    Keeping this as a separate, pure function means it can be unit-tested
    without making any real API calls.
    """
    if not history:
        return ""

    n = len(history)

    avg_transport   = sum(h["transport"]   for h in history) / n
    avg_electricity = sum(h["electricity"] for h in history) / n
    avg_diet        = sum(h["diet"]        for h in history) / n
    avg_flights     = sum(h["flights"]     for h in history) / n
    avg_total       = sum(h["total"]       for h in history) / n
    avg_meat        = sum(h["meat_meals"]  for h in history) / n
    avg_veg         = sum(h["veg_meals"]   for h in history) / n

    modes         = [h["transport_mode"] for h in history]
    dominant_mode = max(set(modes), key=modes.count)
    dominant_label = TRANSPORT_LABELS.get(dominant_mode, dominant_mode)

    recycle_days = sum(1 for h in history if h.get("recycling_saving", 0) > 0)

    gap      = avg_total - BENCHMARKS_KG_PER_DAY["india_average"]
    gap_text = (
        f"{gap:.1f} kg/day ABOVE" if gap > 0 else f"{abs(gap):.1f} kg/day BELOW"
    )

    return f"""
The user has logged {n} day(s) of carbon footprint activity.

Average daily footprint: {avg_total:.2f} kg CO2e

Breakdown:
- Transport:   {avg_transport:.2f} kg/day (dominant mode: {dominant_label})
- Electricity: {avg_electricity:.2f} kg/day
- Diet:        {avg_diet:.2f} kg/day \
({avg_meat:.1f} meat meals/day, {avg_veg:.1f} plant-based meals/day)
- Flights:     {avg_flights:.2f} kg/day
- Recycles or composts: {recycle_days} out of {n} days

Benchmarks (kg CO2e/day):
- India national average:   {BENCHMARKS_KG_PER_DAY['india_average']}
- Global average:           {BENCHMARKS_KG_PER_DAY['global_average']}
- Paris-aligned 2030 target:{BENCHMARKS_KG_PER_DAY['paris_aligned_2030']}

User is {gap_text} the India national average.
""".strip()


# ---------------------------------------------------------------------------
# 6. generate_ai_insights  ← calls Claude, returns personalized coaching text
# ---------------------------------------------------------------------------

def generate_ai_insights(history: list[dict], api_key: str | None) -> str:
    """
    Send the user's history summary to Claude and return personalized,
    prioritized recommendations as a formatted string.

    - Accepts api_key as a parameter (never reads it from a global) so
      the caller (app.py) controls where the key comes from — typically
      Streamlit secrets, never hardcoded or logged.
    - Returns a user-friendly string in every case (empty history, missing
      key, or any API failure) so the UI never has to special-case errors
      or crash. Internal exception details are never shown to the user.
    """
    if not history:
        return ""

    if not api_key:
        return (
            "⚠️ No Anthropic API key is configured, so AI-powered coaching "
            "is unavailable right now. The recommendations above are still "
            "generated from your data."
        )

    summary = build_history_summary(history)

    system_prompt = """
You are a friendly, practical carbon footprint coach helping people in India
reduce their everyday emissions.

When given a user's footprint summary, respond with exactly 3 recommendations.
Format your response like this:

1. [Category] Title of recommendation
   Why it matters for this user (1-2 sentences referencing their specific numbers).
   What to do: one concrete, actionable step they can take this week.
   Estimated saving: X kg CO2e/year.

2. ...

3. ...

Be specific to their numbers. Do not give generic advice that ignores their data.
Keep the total response under 250 words.
""".strip()

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=AI_MODEL,
            max_tokens=AI_MAX_TOKENS,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Here is my carbon footprint data:\n\n{summary}\n\n"
                        "Please give me 3 personalized recommendations."
                    ),
                }
            ],
        )
        text = "\n".join(block.text for block in message.content if block.type == "text")
        return text or "⚠️ The AI coach didn't return any text. Please try again."

    except anthropic.AuthenticationError:
        return "⚠️ The configured API key was rejected. Please check your Streamlit secrets."
    except anthropic.RateLimitError:
        return "⚠️ Rate limit reached. Please wait a moment and try again."
    except anthropic.APIConnectionError:
        return "⚠️ Couldn't reach the AI service. Check your connection and try again."
    except Exception:
        # Deliberately generic: never surface raw exception details (which
        # could include request internals) directly to end users.
        return "⚠️ Something went wrong generating AI insights. Please try again shortly."


# ---------------------------------------------------------------------------
# 7. ACTION_LIBRARY
# ---------------------------------------------------------------------------

ACTION_LIBRARY = [
    {"id": "carpool",       "label": "Carpool or use public transit twice a week",
     "category": "transport",   "saving_kg_year": 250},
    {"id": "led",           "label": "Switch to LED bulbs throughout the home",
     "category": "electricity", "saving_kg_year": 80},
    {"id": "solar_water",   "label": "Use a solar water heater",
     "category": "electricity", "saving_kg_year": 300},
    {"id": "meatless_days", "label": "Have 2 meat-free days every week",
     "category": "diet",        "saving_kg_year": 190},
    {"id": "compost",       "label": "Compost kitchen waste and recycle dry waste daily",
     "category": "waste",       "saving_kg_year": 220},
    {"id": "ac_temp",       "label": "Set AC to 24–26 °C instead of 18–20 °C",
     "category": "electricity", "saving_kg_year": 140},
    {"id": "ev_switch",     "label": "Switch your next vehicle to electric",
     "category": "transport",   "saving_kg_year": 600},
    {"id": "unplug",        "label": "Unplug devices and use smart power strips",
     "category": "electricity", "saving_kg_year": 45},
]


# ---------------------------------------------------------------------------
# 8. yearly_projection
# ---------------------------------------------------------------------------

def yearly_projection(avg_daily_kg: float) -> float:
    """Project a daily average (kg CO2e) to an annual figure."""
    return round(avg_daily_kg * 365, 1)