"""
Carbon Footprint Coach
=======================
A Streamlit app that helps individuals understand, track, and reduce their
everyday carbon footprint through simple daily logging, visual dashboards,
rule-based recommendations, and optional AI-powered personalized coaching.

Guests can log entries and see current-session analysis only — nothing is
ever written to disk for them. Logged-in users get their entries persisted
to SQLite under their own user_id (see database.py), and only their own
rows are ever read back, so accounts can never see each other's data.

Run locally:
    streamlit run app.py
"""

import os
import hashlib

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date

from carbon_engine import (
    DailyEntry,
    calculate_emissions,
    generate_insights,
    generate_ai_insights,
    yearly_projection,
    TRANSPORT_FACTORS,
    TRANSPORT_LABELS,
    BENCHMARKS_KG_PER_DAY,
    ACTION_LIBRARY,
)
from data_manager import (
    get_history,
    export_history_csv,
    import_history_csv,
    get_actions,
    set_actions,
    get_current_history,
    add_current_entry,
)
import database as db
import auth

# Colorblind-safe categorical palette (ColorBrewer "Safe")
PALETTE = px.colors.qualitative.Safe

ASSETS_DIR = "assets"
LOGO_PATH = os.path.join(ASSETS_DIR, "logo.png")          # green carbon footprint icon
HERO_PATH = os.path.join(ASSETS_DIR, "hero_hand_tree.jpg")  # hand-touching-tree image

db.init_db()


def get_api_key() -> str | None:
    """Read the Anthropic API key from Streamlit secrets, if configured."""
    try:
        return st.secrets.get("ANTHROPIC_API_KEY")
    except Exception:
        return None


def inject_styles() -> None:
    """Soft ecological theme: warm off-white background, cream cards,
    sage/olive + soft green accents, charcoal text, beige/brown borders,
    rounded cards, gentle shadows."""
    st.markdown(
        """
        <style>
        .stApp {
            background-color: #FAF7F0;
            color: #3B3A36;
        }
        [data-testid="stSidebar"] {
            background-color: #F3EEE2;
            border-right: 1px solid #D9CBB4;
        }
        [data-testid="stMetric"] {
            background-color: #FFFDF8;
            border: 1px solid #D9CBB4;
            border-radius: 14px;
            padding: 14px 16px;
            box-shadow: 0 2px 8px rgba(91, 110, 76, 0.08);
        }
        [data-testid="stForm"] {
            background-color: #FFFDF8;
            border-radius: 14px;
            border: 1px solid #D9CBB4;
            padding: 1.2rem;
            box-shadow: 0 2px 10px rgba(91, 110, 76, 0.08);
        }
        div.stButton > button, div.stDownloadButton > button {
            border-radius: 10px;
            font-weight: 600;
            background-color: #7C9070;
            color: #FFFDF8;
            border: 1px solid #5B6E4C;
        }
        div.stButton > button:hover, div.stDownloadButton > button:hover {
            background-color: #5B6E4C;
            border-color: #5B6E4C;
        }
        .hero-card {
            background-color: #FFFDF8;
            border: 1px solid #D9CBB4;
            border-radius: 18px;
            padding: 1.8rem;
            box-shadow: 0 4px 16px rgba(91, 110, 76, 0.10);
        }
        .shortcut-card {
            background-color: #FFFDF8;
            border: 1px solid #D9CBB4;
            border-radius: 14px;
            padding: 1rem 1.2rem;
            box-shadow: 0 2px 8px rgba(91, 110, 76, 0.08);
            margin-bottom: 0.6rem;
        }
        h1, h2, h3 {
            color: #3B3A36;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def history_fingerprint(df: pd.DataFrame) -> str:
    if df.empty:
        return "empty"
    return hashlib.sha256(
        pd.util.hash_pandas_object(df, index=False).values.tobytes()
    ).hexdigest()


def render_login_wall(feature_name: str) -> None:
    """Shown instead of a restricted page's content when logged out."""
    st.info(f"🔒 {feature_name} is available to registered users. Log in or create a free account below.")
    render_auth_forms()


def render_auth_forms() -> None:
    tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

    with tab_login:
        with st.form("login_form"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in", use_container_width=True)
        if submitted:
            ok, message = auth.login(u, p)
            if ok:
                st.success(message)
                st.session_state["page_override"] = "Dashboard"
                st.rerun()
            else:
                st.error(message)

    with tab_signup:
        with st.form("signup_form"):
            su = st.text_input("Choose a username")
            se = st.text_input("Email")
            sp = st.text_input("Choose a password", type="password")
            submitted2 = st.form_submit_button("Create account", use_container_width=True)
        if submitted2:
            ok, message = auth.signup(su, se, sp)
            if ok:
                st.success(message)
                st.session_state["page_override"] = "Dashboard"
                st.rerun()
            else:
                st.error(message)


# ---------------------------------------------------------------------------
# Page config / favicon
# ---------------------------------------------------------------------------
page_icon = LOGO_PATH if os.path.exists(LOGO_PATH) else "🌍"

st.set_page_config(
    page_title="Carbon Footprint Coach",
    page_icon=page_icon,
    layout="wide",
    menu_items={
        "About": (
            "Carbon Footprint Coach helps you log daily activities, "
            "see where your emissions come from, and get personalized "
            "recommendations to reduce them."
        )
    },
)
inject_styles()

# ---------------------------------------------------------------------------
# Header (logo + title)
# ---------------------------------------------------------------------------
header_col1, header_col2 = st.columns([1, 8])
with header_col1:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=64)
    else:
        st.markdown("### 🌍")
with header_col2:
    st.title("Carbon Footprint Coach")
    st.caption("Understand, track, and reduce your everyday carbon footprint — one day at a time.")

logged_in = auth.is_logged_in()
user_id = auth.current_user_id()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
if logged_in:
    st.sidebar.success(f"Logged in as **{auth.current_username()}**")
    if st.sidebar.button("Log out", use_container_width=True):
        auth.logout()
        st.rerun()
else:
    st.sidebar.caption("You're browsing as a guest. Log in to save your history.")

nav_options = ["Home", "Log today", "Dashboard", "Insights", "Action tracker"]
default_page = st.session_state.pop("page_override", "Home")
page = st.sidebar.radio(
    "Navigate", nav_options,
    index=nav_options.index(default_page) if default_page in nav_options else 0,
)

st.sidebar.markdown("---")
st.sidebar.subheader("Your data")

if logged_in:
    st.sidebar.caption("Your entries are saved to your account and visible only to you.")
    history_df = get_current_history(user_id=user_id)
    st.sidebar.download_button(
        "Download my data (CSV)",
        data=history_df.to_csv(index=False).encode("utf-8"),
        file_name="carbon_footprint_history.csv",
        mime="text/csv",
        disabled=history_df.empty,
        use_container_width=True,
    )
else:
    st.sidebar.caption(
        "Guest mode: entries are kept only for this browser session and "
        "are never saved permanently. Log in to keep your history and "
        "export it as CSV."
    )
    history_df = get_current_history(user_id=None)


# ---------------------------------------------------------------------------
# PAGE: Home (landing intro)
# ---------------------------------------------------------------------------
if page == "Home":
    hero_left, hero_right = st.columns([1.2, 1])
    with hero_left:
        st.markdown('<div class="hero-card">', unsafe_allow_html=True)
        st.markdown("## 🌱 Small daily choices, real climate impact")
        st.write(
            "Carbon Footprint Coach helps you log your everyday activities — "
            "commuting, electricity, meals, and travel — and turns that data "
            "into a clear picture of your footprint. Get rule-based and "
            "AI-powered coaching, track your progress over time, and commit "
            "to concrete actions that add up."
        )
        st.write(
            "Start logging right away as a guest, or create a free account "
            "to save your history, unlock your personal dashboard, and track "
            "long-term progress."
        )
        cta1, cta2 = st.columns(2)
        with cta1:
            if st.button("Log today's activity", use_container_width=True):
                st.session_state["page_override"] = "Log today"
                st.rerun()
        with cta2:
            if not logged_in:
                if st.button("Create a free account", use_container_width=True):
                    st.session_state["page_override"] = "Dashboard"
                    st.rerun()
            else:
                if st.button("Go to my dashboard", use_container_width=True):
                    st.session_state["page_override"] = "Dashboard"
                    st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with hero_right:
        if os.path.exists(HERO_PATH):
            st.image(HERO_PATH, use_container_width=True)
        else:
            st.markdown(
                '<div class="hero-card" style="text-align:center;">'
                "🌳<br><br>Add your hero image at "
                f"<code>{HERO_PATH}</code> to display it here."
                "</div>",
                unsafe_allow_html=True,
            )

    if not logged_in:
        st.divider()
        st.subheader("Get started")
        render_auth_forms()


# ---------------------------------------------------------------------------
# PAGE: Log today  (public — guests get session-only analysis)
# ---------------------------------------------------------------------------
elif page == "Log today":
    st.header("Log today's activities")
    st.write("Fill in your activities for the day. It only takes a minute.")
    if not logged_in:
        st.caption(
            "You're logging as a guest — this entry will only be visible for "
            "this browser session and won't be saved permanently. "
            "Log in or sign up to keep your history."
        )

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
        add_current_entry(row, user_id=user_id)
        history_df = get_current_history(user_id=user_id)

        st.toast("Entry saved!", icon="✅")
        st.success(f"Saved! Today's footprint: **{breakdown['total']} kg CO2e**")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Transport", f"{breakdown['transport']} kg")
        m2.metric("Electricity", f"{breakdown['electricity']} kg")
        m3.metric("Diet", f"{breakdown['diet']} kg")
        m4.metric("Flights", f"{breakdown['flights']} kg")

        if breakdown["recycling_saving"] > 0:
            st.info(f"Recycling/composting saved you {breakdown['recycling_saving']} kg CO2e today.")


# ---------------------------------------------------------------------------
# PAGE: Dashboard  (requires login)
# ---------------------------------------------------------------------------
elif page == "Dashboard":
    st.header("Your footprint dashboard")

    if not logged_in:
        render_login_wall("The personal dashboard")
    elif history_df.empty:
        st.info("No entries yet. Go to **Log today** to add your first entry.")
    else:
        df = history_df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")

        today = pd.Timestamp(date.today())
        daily_emission = df[df["date"].dt.date == date.today()]["total"].sum()
        monthly_emission = df[
            (df["date"].dt.month == today.month) & (df["date"].dt.year == today.year)
        ]["total"].sum()
        avg_emission = df["total"].mean()
        total_emission = df["total"].sum()
        logged_days = len(df)

        r1c1, r1c2, r1c3, r1c4, r1c5 = st.columns(5)
        r1c1.metric("Today's emission", f"{daily_emission:.1f} kg")
        r1c2.metric("This month", f"{monthly_emission:.1f} kg")
        r1c3.metric("Average daily", f"{avg_emission:.1f} kg")
        r1c4.metric("Total logged", f"{total_emission:.1f} kg")
        r1c5.metric("Days logged", logged_days)

        st.subheader("Shortcuts")
        s1, s2, s3 = st.columns(3)
        with s1:
            st.markdown('<div class="shortcut-card">', unsafe_allow_html=True)
            st.markdown("**📝 Log today**")
            if st.button("Add today's entry", key="shortcut_log"):
                st.session_state["page_override"] = "Log today"
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
        with s2:
            st.markdown('<div class="shortcut-card">', unsafe_allow_html=True)
            st.markdown("**💡 Insights**")
            if st.button("View personalized insights", key="shortcut_insights"):
                st.session_state["page_override"] = "Insights"
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
        with s3:
            st.markdown('<div class="shortcut-card">', unsafe_allow_html=True)
            st.markdown("**🎯 Action tracker**")
            if st.button("Review your goals", key="shortcut_actions"):
                st.session_state["page_override"] = "Action tracker"
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        st.subheader("Where your emissions come from")
        category_totals = df[["transport", "electricity", "diet", "flights"]].sum()
        pie_df = category_totals.reset_index()
        pie_df.columns = ["category", "kg_co2e"]
        pie_df = pie_df[pie_df["kg_co2e"] > 0]
        if not pie_df.empty:
            fig_pie = px.pie(
                pie_df, names="category", values="kg_co2e", hole=0.4,
                color_discrete_sequence=PALETTE,
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        st.subheader("Trend over time")
        fig_line = px.line(
            df, x="date", y="total", markers=True,
            labels={"total": "kg CO2e", "date": "Date"},
            color_discrete_sequence=PALETTE,
        )
        st.plotly_chart(fig_line, use_container_width=True)

        st.subheader("Recent logs")
        st.dataframe(
            df.sort_values("date", ascending=False)[
                ["date", "transport_mode", "transport_km", "electricity_kwh",
                 "meat_meals", "veg_meals", "flight_km", "recycled", "total"]
            ].head(10),
            hide_index=True,
            use_container_width=True,
        )


# ---------------------------------------------------------------------------
# PAGE: Insights  (requires login — personalized analytics)
# ---------------------------------------------------------------------------
elif page == "Insights":
    st.header("Personalized insights")

    if not logged_in:
        render_login_wall("Personalized insights")
    elif history_df.empty:
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

        st.divider()
        st.subheader("🤖 AI-powered coaching")
        api_key = get_api_key()
        current_hash = history_fingerprint(history_df)

        if not api_key:
            st.caption(
                "Add `ANTHROPIC_API_KEY` to your Streamlit secrets "
                "(`.streamlit/secrets.toml`) to enable this feature."
            )

        if st.button("Generate AI insights", use_container_width=True, disabled=not api_key):
            with st.spinner("Your AI coach is reviewing your data..."):
                st.session_state["ai_insights_text"] = generate_ai_insights(records, api_key)
                st.session_state["ai_insights_hash"] = current_hash

        cached_text = st.session_state.get("ai_insights_text")
        if cached_text:
            if st.session_state.get("ai_insights_hash") != current_hash:
                st.info("Your data has changed since this was generated — click above to refresh it.")
            st.markdown(cached_text)


# ---------------------------------------------------------------------------
# PAGE: Action tracker  (requires login — goals)
# ---------------------------------------------------------------------------
elif page == "Action tracker":
    st.header("Action tracker")

    if not logged_in:
        render_login_wall("The action tracker")
    else:
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
            st.toast("Commitments saved!", icon="✅")

        st.subheader("Combined impact")
        st.metric("Potential yearly reduction", f"{total_saving:,} kg CO2e")
        if total_saving > 0:
            st.caption(
                f"Roughly equivalent to {total_saving / 21:.1f} mature trees' "
                "worth of annual CO2 absorption."
            )
