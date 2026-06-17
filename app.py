"""
Carbon Footprint Coach
=======================
A Streamlit app that helps individuals understand, track, and reduce their
everyday carbon footprint through simple daily logging, visual dashboards,
and personalized, context-aware recommendations.

Data lives in the browser session (st.session_state) so that, on a shared
public deployment, one visitor's data is never mixed with another's. Users
can export their history to CSV and re-import it in a future session.

Run locally:
    streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date

from carbon_engine import (
    DailyEntry,
    calculate_emissions,
    generate_insights,
    yearly_projection,
    TRANSPORT_FACTORS,
    TRANSPORT_LABELS,
    BENCHMARKS_KG_PER_DAY,
    ACTION_LIBRARY,
)
from data_manager import (
    get_history,
    add_entry,
    export_history_csv,
    import_history_csv,
    get_actions,
    set_actions,
)

# Colorblind-safe categorical palette (ColorBrewer "Safe")
PALETTE = px.colors.qualitative.Safe

st.set_page_config(page_title="Carbon Footprint Coach", page_icon="🌍", layout="wide")

st.title("🌍 Carbon Footprint Coach")
st.caption("Understand, track, and reduce your everyday carbon footprint — one day at a time.")

page = st.sidebar.radio("Navigate", ["Log today", "Dashboard", "Insights", "Action tracker"])

st.sidebar.markdown("---")
st.sidebar.subheader("Your data")
st.sidebar.caption(
    "Your entries are kept only in this browser session and are not shared "
    "with other users. Download a copy to keep your history, and re-upload "
    "it next time to continue where you left off."
)

history_df = get_history()

st.sidebar.download_button(
    "Download my data (CSV)",
    data=export_history_csv(),
    file_name="carbon_footprint_history.csv",
    mime="text/csv",
    disabled=history_df.empty,
    use_container_width=True,
)

uploaded = st.sidebar.file_uploader(
    "Restore previous data (CSV)", type="csv",
    help="Upload a CSV previously downloaded from this app.",
)
if uploaded is not None:
    ok, message = import_history_csv(uploaded)
    if ok:
        st.sidebar.success(message)
        history_df = get_history()
    else:
        st.sidebar.error(message)


# ---------------------------------------------------------------------------
# PAGE: Log today
# ---------------------------------------------------------------------------
if page == "Log today":
    st.header("Log today's activities")
    st.write("Fill in your activities for the day. It only takes a minute.")

    with st.form("daily_log"):
        col1, col2 = st.columns(2)

        with col1:
            entry_date = st.date_input("Date", value=date.today())
            mode_key = st.selectbox(
                "Main transport mode today",
                options=list(TRANSPORT_FACTORS.keys()),
                format_func=lambda k: TRANSPORT_LABELS[k],
                help="Choose the mode you used for most of your travel today.",
            )
            transport_km = st.number_input(
                "Distance travelled (km)", min_value=0.0, max_value=1000.0,
                value=10.0, step=1.0,
            )
            electricity_kwh = st.number_input(
                "Electricity used today (kWh)", min_value=0.0, max_value=200.0,
                value=5.0, step=0.5,
                help="Tip: divide your last electricity bill's units by the number of days in the cycle.",
            )

        with col2:
            meat_meals = st.number_input("Meat-based meals today", min_value=0, max_value=6, value=1)
            veg_meals = st.number_input("Plant-based meals today", min_value=0, max_value=6, value=2)
            flight_km = st.number_input(
                "Flight distance today, if any (km)", min_value=0.0, max_value=20000.0,
                value=0.0, step=50.0,
            )
            recycled = st.checkbox("Did you recycle or compost today?")

        submitted = st.form_submit_button("Save entry", use_container_width=True)

    if submitted:
        entry = DailyEntry(
            date=str(entry_date),
            transport_mode=mode_key,
            transport_km=transport_km,
            electricity_kwh=electricity_kwh,
            meat_meals=int(meat_meals),
            veg_meals=int(veg_meals),
            flight_km=flight_km,
            recycled=recycled,
        )
        breakdown = calculate_emissions(entry)

        row = {
            "date": entry.date,
            "transport_mode": entry.transport_mode,
            "transport_km": entry.transport_km,
            "electricity_kwh": entry.electricity_kwh,
            "meat_meals": entry.meat_meals,
            "veg_meals": entry.veg_meals,
            "flight_km": entry.flight_km,
            "recycled": entry.recycled,
            **breakdown,
        }
        add_entry(row)
        history_df = get_history()

        st.success(f"Saved! Today's footprint: **{breakdown['total']} kg CO2e**")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Transport", f"{breakdown['transport']} kg")
        m2.metric("Electricity", f"{breakdown['electricity']} kg")
        m3.metric("Diet", f"{breakdown['diet']} kg")
        m4.metric("Flights", f"{breakdown['flights']} kg")

        if breakdown["recycling_saving"] > 0:
            st.info(f"Recycling/composting saved you {breakdown['recycling_saving']} kg CO2e today.")


# ---------------------------------------------------------------------------
# PAGE: Dashboard
# ---------------------------------------------------------------------------
elif page == "Dashboard":
    st.header("Your footprint dashboard")

    if history_df.empty:
        st.info("No entries yet. Go to **Log today** to add your first entry.")
    else:
        avg_daily = history_df["total"].mean()
        projected_year = yearly_projection(avg_daily)

        c1, c2, c3 = st.columns(3)
        c1.metric("Average daily footprint", f"{avg_daily:.1f} kg CO2e")
        c2.metric("Projected yearly footprint", f"{projected_year:,.0f} kg CO2e")
        c3.metric("Days logged", len(history_df))

        # --- Category breakdown ---
        st.subheader("Where your emissions come from")
        category_totals = history_df[["transport", "electricity", "diet", "flights"]].sum()
        pie_df = category_totals.reset_index()
        pie_df.columns = ["category", "kg_co2e"]
        pie_df = pie_df[pie_df["kg_co2e"] > 0]

        if pie_df.empty:
            st.write("Not enough data yet to show a breakdown.")
        else:
            fig_pie = px.pie(
                pie_df, names="category", values="kg_co2e", hole=0.4,
                color_discrete_sequence=PALETTE,
            )
            st.plotly_chart(fig_pie, use_container_width=True)

            summary = ", ".join(
                f"{row['category']} {row['kg_co2e']:.1f} kg" for _, row in pie_df.iterrows()
            )
            st.caption(f"Total emissions by category (kg CO2e): {summary}.")

            with st.expander("View as table"):
                st.dataframe(pie_df.rename(columns={"kg_co2e": "kg CO2e"}), hide_index=True)

        # --- Trend over time ---
        st.subheader("Trend over time")
        trend_df = history_df.copy()
        trend_df["date"] = pd.to_datetime(trend_df["date"])
        trend_df = trend_df.sort_values("date")
        fig_line = px.line(
            trend_df, x="date", y="total", markers=True,
            labels={"total": "kg CO2e", "date": "Date"},
            color_discrete_sequence=PALETTE,
        )
        st.plotly_chart(fig_line, use_container_width=True)
        st.caption(
            f"Daily total emissions ranged from {trend_df['total'].min():.1f} to "
            f"{trend_df['total'].max():.1f} kg CO2e across {len(trend_df)} logged days."
        )

        with st.expander("View as table"):
            st.dataframe(
                trend_df[["date", "transport", "electricity", "diet", "flights", "total"]],
                hide_index=True,
            )

        # --- Benchmarks ---
        st.subheader("How you compare")
        bench_df = pd.DataFrame({
            "label": ["You", "India average", "Global average", "Paris-aligned target"],
            "kg_per_day": [
                round(avg_daily, 2),
                BENCHMARKS_KG_PER_DAY["india_average"],
                BENCHMARKS_KG_PER_DAY["global_average"],
                BENCHMARKS_KG_PER_DAY["paris_aligned_2030"],
            ],
        })
        fig_bar = px.bar(
            bench_df, x="label", y="kg_per_day", color="label",
            labels={"kg_per_day": "kg CO2e / day", "label": ""},
            color_discrete_sequence=PALETTE,
        )
        fig_bar.update_layout(showlegend=False)
        st.plotly_chart(fig_bar, use_container_width=True)
        st.caption(
            "Comparison (kg CO2e per day): "
            + ", ".join(f"{row['label']} {row['kg_per_day']}" for _, row in bench_df.iterrows())
            + "."
        )


# ---------------------------------------------------------------------------
# PAGE: Insights
# ---------------------------------------------------------------------------
elif page == "Insights":
    st.header("Personalized insights")
    st.write(
        "These recommendations are generated dynamically based on the patterns "
        "in your logged data — not generic advice."
    )

    if history_df.empty:
        st.info("Log a few days of activity to unlock personalized insights.")
    else:
        records = history_df.to_dict("records")
        insights = generate_insights(records)

        if not insights:
            st.success("No specific concerns detected yet. Keep logging for richer insights.")

        for rec in insights:
            with st.container(border=True):
                st.markdown(f"**{rec['title']}**")
                st.write(rec["message"])
                if rec["saving_kg_year"] > 0:
                    st.caption(f"Potential saving: ~{rec['saving_kg_year']} kg CO2e/year")


# ---------------------------------------------------------------------------
# PAGE: Action tracker
# ---------------------------------------------------------------------------
elif page == "Action tracker":
    st.header("Action tracker")
    st.write("Commit to small, concrete actions and see their combined yearly impact.")

    saved_actions = get_actions()
    selections = {}
    total_saving = 0

    for action in ACTION_LIBRARY:
        checked = st.checkbox(
            f"{action['label']}  (~{action['saving_kg_year']} kg CO2e/year)",
            value=bool(saved_actions.get(action["id"], False)),
            key=action["id"],
        )
        selections[action["id"]] = checked
        if checked:
            total_saving += action["saving_kg_year"]

    if st.button("Save my commitments", use_container_width=True):
        set_actions(selections)
        st.success("Saved!")

    st.subheader("Combined impact")
    st.metric("Potential yearly reduction", f"{total_saving:,} kg CO2e")
    if total_saving > 0:
        st.caption(
            f"Roughly equivalent to {total_saving / 21:.1f} mature trees' "
            "worth of annual CO2 absorption."
        )