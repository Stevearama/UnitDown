import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go
import pandas as pd

from data_import import load_offline_events
from chart_data import build_seasonality_data
from data_import_capacity import load_units
from chart_data_capacity import build_capacity_data

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# High-contrast palette — all clearly visible on a white background
PALETTE = [
    "#0047AB",  # cobalt blue
    "#CC0000",  # red
    "#00827F",  # teal
    "#E65C00",  # orange
    "#5C2D91",  # purple
    "#2E7D32",  # dark green
    "#8B4513",  # saddle brown
    "#1A237E",  # navy
]

COLUMN_LABELS = {
    "UNIT_ID":            "Unit ID",
    "OWNER_NAME":         "Owner",
    "PLANT_ID":           "Plant ID",
    "PLANT_NAME":         "Plant",
    "COUNTRY":            "Country",
    "MARKET_REG":         "Market Region",
    "WORLD_REG":          "World Region",
    "U_STATUS":           "Status",
    "U_CAPACITY":         "Unit Capacity",
    "CAP_OFFLINE":        "Capacity Offline",
    "CAP_UOM":            "Unit of Measure",
    "DERATE":             "Derate (%)",
    "START_DATE":         "Start Date",
    "END_DATE":           "End Date",
    "EVENT_TYPE":         "Event Type",
    "E_CAUSE":            "Cause",
    "E_STATUS_RESEARCH":  "Research Status",
    "UTYPE_DESC":         "Unit Type",
    "PADD_REG":           "Region",
    "LATITUDE":           "Latitude",
    "LONGITUDE":          "Longitude",
}

# Columns kept in the DataFrame but hidden from every display table
DISPLAY_HIDDEN = {"UNIT_ID", "PLANT_ID", "U_STATUS", "LATITUDE", "LONGITUDE"}

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def check_password() -> bool:
    """Show a password prompt and return True once the correct password is entered."""
    if st.session_state.get("authenticated"):
        return True

    st.markdown(
        """
        <h1 style='font-family:"Arial Black",Arial,sans-serif;
                   color:#000000; margin-bottom:2px; font-size:2rem;'>
            Offline Capacity Monitor
        </h1>
        <hr style='border:none; border-top:3px solid #E3120B; margin-bottom:24px;'>
        """,
        unsafe_allow_html=True,
    )
    pwd = st.text_input("Password", type="password")
    if pwd:
        if pwd == st.secrets["password"]:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@st.cache_data(ttl=21600)
def get_capacity_data() -> pd.DataFrame:
    """Load and cache the units dataset (total capacity).

    On Streamlit Cloud, downloads from Google Drive using gdrive_units_file_id secret.
    Locally, falls back to reading 'units.csv'.
    """
    file_id = st.secrets.get("gdrive_units_file_id", None)
    if file_id:
        import gdown, os, tempfile
        tmp_path = os.path.join(tempfile.gettempdir(), "units.csv")
        gdown.download(f"https://drive.google.com/uc?id={file_id}", tmp_path, quiet=True)
        return load_units(tmp_path)
    return load_units()


@st.cache_data(ttl=21600)
def get_data() -> pd.DataFrame:
    """Load and cache the offline events dataset.

    On Streamlit Cloud, downloads the CSV from Google Drive using the file ID
    stored in secrets. Locally, falls back to reading 'Offline Event.csv'.
    """
    file_id = st.secrets.get("gdrive_file_id", None)
    if file_id:
        import gdown, os, tempfile
        tmp_path = os.path.join(tempfile.gettempdir(), "offline_event.csv")
        gdown.download(f"https://drive.google.com/uc?id={file_id}", tmp_path, quiet=True)
        return load_offline_events(tmp_path)
    return load_offline_events()

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

def render_multiselect(label: str, options: list, key: str, default: list = None) -> list:
    """Render a sidebar multiselect; an empty selection means 'include all'."""
    sorted_opts = sorted([o for o in options if o])
    valid_default = [d for d in (default or []) if d in sorted_opts]
    return st.sidebar.multiselect(label, sorted_opts, default=valid_default, key=key)


def collect_filters(df: pd.DataFrame) -> dict:
    """Render all sidebar filter widgets and return {column: selected_values}."""
    st.sidebar.header("Filters")
    st.sidebar.caption("Leave a multiselect empty to include all values.")

    event_choice = st.sidebar.radio(
        "Event type", ["Planned", "Unplanned", "Both"], horizontal=True, index=2
    )
    st.sidebar.divider()

    available_years = sorted([y for y in df["START_DATE"].dropna().dt.year.unique().astype(int) if y >= 2021])
    cur = pd.Timestamp.today().year
    default_years = [cur - 3, cur - 2, cur - 1, cur, cur + 1]

    year = render_multiselect("Year", available_years, "year", default=default_years)
    df1 = df[df["START_DATE"].dt.year.isin(year)] if year else df

    world_reg = render_multiselect("World Region", df1["WORLD_REG"].dropna().unique(), "world_reg", default=["North America"])
    df2 = df1[df1["WORLD_REG"].isin(world_reg)] if world_reg else df1

    country = render_multiselect("Country", df2["COUNTRY"].dropna().unique(), "country", default=["U.S.A."])
    df3 = df2[df2["COUNTRY"].isin(country)] if country else df2

    padd_reg = render_multiselect("Region", df3["PADD_REG"].dropna().unique(), "padd")
    df4 = df3[df3["PADD_REG"].isin(padd_reg)] if padd_reg else df3

    utype = render_multiselect("Unit Type", df4["UTYPE_DESC"].dropna().unique(), "utype", default=["CDU"])
    df5 = df4[df4["UTYPE_DESC"].isin(utype)] if utype else df4

    owner = render_multiselect("Owner", df5["OWNER_NAME"].dropna().unique(), "owner")

    return {
        "EVENT_TYPE": [] if event_choice == "Both" else [event_choice],
        "YEAR":       year,
        "WORLD_REG":  world_reg,
        "COUNTRY":    country,
        "PADD_REG":   padd_reg,
        "UTYPE_DESC": utype,
        "OWNER_NAME": owner,
    }


def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """Apply only the non-empty filter selections to the DataFrame.

    YEAR is a derived filter — matched against START_DATE.dt.year rather than a column directly.
    """
    for col, selected in filters.items():
        if not selected:
            continue
        if col == "YEAR":
            mask = pd.Series(False, index=df.index)
            start_year = df["START_DATE"].dt.year
            end_year = df["END_DATE"].dt.year
            for y in selected:
                started = (start_year <= y) | df["START_DATE"].isna()
                still_running = (end_year >= y) | df["END_DATE"].isna()
                mask |= started & still_running
            df = df[mask]
        else:
            df = df[df[col].isin(selected)]
    return df

# ---------------------------------------------------------------------------
# Chart title
# ---------------------------------------------------------------------------

def _describe_filter(selected: list, plural: str) -> str:
    """Return a short label for one filter — the value(s) selected, or 'All <plural>'."""
    if not selected:
        return f"All {plural}"
    if len(selected) == 1:
        return selected[0]
    return f"{selected[0]} & {len(selected) - 1} more"


def build_chart_title(filters: dict, prefix: str = "Offline Capacity for") -> str:
    """Construct a human-readable chart title that reflects the active filter selections."""
    unit    = _describe_filter(filters["UTYPE_DESC"], "unit types")
    country = _describe_filter(filters["COUNTRY"],    "countries")
    owner   = _describe_filter(filters["OWNER_NAME"], "owners")
    region  = _describe_filter(filters["PADD_REG"],   "regions")
    parts = [p.rstrip(".") for p in [unit, country, owner, region]]
    return prefix + "  ·  ".join(parts)

# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------

def _add_today_marker(fig: go.Figure) -> None:
    """Add a vertical dashed line and 'Today' label at the current day-of-year position."""
    today_plot = pd.Timestamp.today().replace(year=2000).normalize().strftime("%Y-%m-%d")
    fig.add_vline(
        x=today_plot,
        line_dash="dash",
        line_color="#555555",
        line_width=1.5,
    )
    fig.add_annotation(
        x=today_plot,
        y=1.05,
        yref="paper",
        text="Today",
        showarrow=False,
        font=dict(size=11, color="#555555"),
        xanchor="center",
    )


def _dominant_uom(df: pd.DataFrame) -> str:
    """Return the most common unit of measure in the filtered dataset."""
    mode = df["CAP_UOM"].mode()
    return mode.iloc[0] if not mode.empty else ""


def build_chart(seasonality_df: pd.DataFrame, uom: str, y_label: str = "Capacity Offline") -> go.Figure:
    """Build an Economist-style seasonality line chart with one line per year."""
    fig = go.Figure()

    for i, year in enumerate(sorted(seasonality_df["year"].unique())):
        year_data = seasonality_df[seasonality_df["year"] == year].sort_values("plot_date")
        fig.add_trace(go.Scatter(
            x=year_data["plot_date"],
            y=year_data["CAP_OFFLINE"],
            mode="lines",
            name=str(year),
            line=dict(color=PALETTE[i % len(PALETTE)], width=2),
            hovertemplate="%{x|%d %b} · %{y:,.0f} " + uom + "<extra>" + str(year) + "</extra>",
        ))

    fig.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="white",
        # Black text throughout — avoids the light-grey-on-white readability problem
        font=dict(family="Arial", size=12, color="#000000"),
        xaxis=dict(
            tickformat="%b",
            dtick="M1",
            showgrid=False,
            showline=True,
            linecolor="#000000",
            linewidth=1.5,
            ticks="outside",
            ticklen=5,
            tickfont=dict(color="#000000", size=12),
        ),
        yaxis=dict(
            title=dict(
                text=f"{y_label} ({uom})" if uom else y_label,
                font=dict(color="#000000"),
            ),
            tickfont=dict(color="#000000"),
            showgrid=True,
            gridcolor="#E8E8E8",
            gridwidth=1,
            showline=False,
            zeroline=True,
            zerolinecolor="#BBBBBB",
            tickformat=",",
        ),
        legend=dict(
            orientation="h",
            y=-0.15,
            x=0,
            title_text="",
            font=dict(size=11, color="#000000"),
        ),
        margin=dict(l=70, r=20, t=40, b=90),
        hovermode="x",
    )
    _add_today_marker(fig)
    return fig

# ---------------------------------------------------------------------------
# Event subset helpers
# ---------------------------------------------------------------------------

def get_active_events(df: pd.DataFrame) -> pd.DataFrame:
    """Return events that are currently ongoing (started in past, ends in future)."""
    today = pd.Timestamp.today().normalize()
    return df[(df["START_DATE"] <= today) & (df["END_DATE"] >= today)]


def get_recent_starts(df: pd.DataFrame, days: int = 10) -> pd.DataFrame:
    """Return events whose start date falls within the last N days."""
    today = pd.Timestamp.today().normalize()
    cutoff = today - pd.Timedelta(days=days)
    return df[(df["START_DATE"] >= cutoff) & (df["START_DATE"] <= today)]


def get_recent_ends(df: pd.DataFrame, days: int = 10) -> pd.DataFrame:
    """Return events whose end date falls within the last N days."""
    today = pd.Timestamp.today().normalize()
    cutoff = today - pd.Timedelta(days=days)
    return df[(df["END_DATE"] >= cutoff) & (df["END_DATE"] <= today)]

# ---------------------------------------------------------------------------
# Capacity table helpers
# ---------------------------------------------------------------------------

CAPACITY_PLANT_COLS = ["OWNER_NAME", "PLANT_NAME", "COUNTRY", "MARKET_REG", "WORLD_REG", "PADD_REG"]

CAPACITY_PLANT_LABELS = {
    "OWNER_NAME": "Owner",
    "PLANT_NAME": "Plant",
    "COUNTRY":    "Country",
    "MARKET_REG": "Market Region",
    "WORLD_REG":  "World Region",
    "PADD_REG":   "Region",
}


def build_plant_pivot(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot units into a plant × unit-type capacity table, one row per plant."""
    if df.empty:
        return pd.DataFrame()
    pivot = pd.pivot_table(
        df,
        values="U_CAPACITY",
        index=CAPACITY_PLANT_COLS,
        columns="UTYPE_DESC",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    pivot.columns.name = None
    return pivot.rename(columns=CAPACITY_PLANT_LABELS)


def render_capacity_tables(filtered_units: pd.DataFrame, filters: dict) -> None:
    """Render the three capacity tabs: active plants, closures, openings."""
    today = pd.Timestamp.today().normalize()
    selected_years = filters.get("YEAR", [])
    if selected_years:
        year_start = pd.Timestamp(f"{min(selected_years)}-01-01")
        year_end   = pd.Timestamp(f"{max(selected_years)}-12-31")
    else:
        year_start = year_end = None

    active = filtered_units[
        filtered_units["END_DATE"].isna() | (filtered_units["END_DATE"] >= today)
    ]

    if year_start is not None:
        closed = filtered_units[
            filtered_units["END_DATE"].notna() &
            (filtered_units["END_DATE"] >= year_start) &
            (filtered_units["END_DATE"] <= year_end)
        ]
        opened = filtered_units[
            filtered_units["START_DATE"].notna() &
            (filtered_units["START_DATE"] >= year_start) &
            (filtered_units["START_DATE"] <= year_end)
        ]
    else:
        closed = filtered_units[filtered_units["END_DATE"].notna()]
        opened = filtered_units[filtered_units["START_DATE"].notna()]

    tab1, tab2, tab3 = st.tabs([
        "Active Plants",
        "Closed — Selected Years",
        "Opened — Selected Years",
    ])

    with tab1:
        pivot = build_plant_pivot(active)
        st.caption(f"{active['PLANT_NAME'].nunique():,} plants")
        if pivot.empty:
            st.info("No active plants for this selection.")
        else:
            st.dataframe(pivot, hide_index=True, height=400)

    with tab2:
        pivot = build_plant_pivot(closed)
        st.caption(f"{closed['PLANT_NAME'].nunique():,} plants with closures")
        if pivot.empty:
            st.info("No closures in the selected years.")
        else:
            st.dataframe(pivot, hide_index=True, height=400)

    with tab3:
        pivot = build_plant_pivot(opened)
        st.caption(f"{opened['PLANT_NAME'].nunique():,} plants with openings")
        if pivot.empty:
            st.info("No openings in the selected years.")
        else:
            st.dataframe(pivot, hide_index=True, height=400)


# ---------------------------------------------------------------------------
# Table helpers
# ---------------------------------------------------------------------------

def prepare_display_table(df: pd.DataFrame) -> pd.DataFrame:
    """Drop hidden columns, format dates, and rename to human-readable labels for display."""
    display = df.drop(columns=[c for c in DISPLAY_HIDDEN if c in df.columns]).copy()
    for col in ("START_DATE", "END_DATE"):
        if col in display.columns:
            display[col] = display[col].dt.strftime("%b %d %Y")
    return display.rename(columns=COLUMN_LABELS).reset_index(drop=True)


def render_table(df: pd.DataFrame, empty_msg: str = "No matching events.") -> None:
    """Render a labelled dataframe or a notice if it is empty."""
    st.caption(f"{len(df):,} events")
    if df.empty:
        st.info(empty_msg)
    else:
        st.dataframe(prepare_display_table(df), height=350, hide_index=True)

# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

def render_header(title: str, subtitle: str) -> None:
    """Render the page title and red rule in Economist style."""
    st.markdown(
        f"""
        <style>
        [data-testid="stToolbarActions"] {{display: none;}}
        </style>
        <h1 style='font-family:"Arial Black",Arial,sans-serif;
                   color:#000000; margin-bottom:2px; font-size:2rem;'>
            {title}
        </h1>
        <p style='color:#555555; font-size:15px; margin-top:0; margin-bottom:10px;'>
            {subtitle}
        </p>
        <hr style='border:none; border-top:3px solid #E3120B; margin-bottom:24px;'>
        """,
        unsafe_allow_html=True,
    )


def render_metrics(df: pd.DataFrame) -> None:
    """Show headline summary counts for the current filter selection."""
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Events",        f"{len(df):,}")
    c2.metric("Unique Plants", f"{df['PLANT_NAME'].nunique():,}")
    c3.metric("Unique Owners", f"{df['OWNER_NAME'].nunique():,}")
    c4.metric("Countries",     f"{df['COUNTRY'].nunique():,}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def inject_ga() -> None:
    """Inject the Google Analytics 4 tracking tag."""
    components.html(
        """
        <script async src="https://www.googletagmanager.com/gtag/js?id=G-Q31W8YZT78"></script>
        <script>
          window.dataLayer = window.dataLayer || [];
          function gtag(){dataLayer.push(arguments);}
          gtag('js', new Date());
          gtag('config', 'G-Q31W8YZT78');
        </script>
        """,
        height=0,
    )


def main() -> None:
    """Assemble and run the full Streamlit dashboard."""
    st.set_page_config(page_title="Offline Capacity Monitor", layout="wide")

    if not check_password():
        st.stop()

    inject_ga()

    chart_mode = st.radio("View", ["Offline Capacity", "Total Capacity"], horizontal=True, index=0)

    if chart_mode == "Offline Capacity":
        render_header("Offline Capacity Monitor", "Daily capacity offline by season and year")
    else:
        render_header("Total Capacity Monitor", "Total installed capacity by unit type and year")

    df = get_data()

    filters = collect_filters(df)
    filtered = apply_filters(df.copy(), filters)

    if chart_mode == "Offline Capacity":
        if filtered.empty:
            st.warning("No events match the selected filters.")
        else:
            title = build_chart_title(filters, prefix="Offline Capacity for ")
            st.markdown(
                f"<h3 style='font-family:\"Arial Black\",Arial,sans-serif; "
                f"color:#000000; font-size:1.1rem; margin-bottom:4px;'>{title}</h3>",
                unsafe_allow_html=True,
            )
            uom = _dominant_uom(filtered)
            seasonality = build_seasonality_data(filtered, years=filters["YEAR"] or None)
            fig = build_chart(seasonality, uom, y_label="Capacity Offline")
            chart_years = sorted(seasonality["year"].unique().tolist())
            event = st.plotly_chart(fig, on_select="rerun", key="offline_chart")
            if event and event.selection and event.selection.points:
                pt = event.selection.points[0]
                year = chart_years[pt["curve_number"]]
                plot_x = pd.Timestamp(pt["x"])
                st.session_state["selected_date"] = plot_x.replace(year=int(year))
    else:
        units_df = get_capacity_data()
        filtered_units = apply_filters(units_df.copy(), filters)
        if filtered_units.empty:
            st.warning("No units match the selected filters.")
        else:
            title = build_chart_title(filters, prefix="Total Capacity for ")
            st.markdown(
                f"<h3 style='font-family:\"Arial Black\",Arial,sans-serif; "
                f"color:#000000; font-size:1.1rem; margin-bottom:4px;'>{title}</h3>",
                unsafe_allow_html=True,
            )
            uom = _dominant_uom(filtered_units)
            seasonality = build_capacity_data(filtered_units, years=filters["YEAR"] or None)
            fig = build_chart(seasonality, uom, y_label="Total Capacity")
            st.plotly_chart(fig)

    st.markdown("---")

    if chart_mode == "Total Capacity":
        render_capacity_tables(filtered_units, filters)
    else:
        tab_active, tab_starts, tab_ends, tab_all, tab_selected = st.tabs([
            "Active Now",
            "Started — Last 10 Days",
            "Ended — Last 10 Days",
            "All Events",
            "Events on Selected Date",
        ])

        with tab_active:
            render_table(get_active_events(filtered), "No currently active events for this selection.")

        with tab_starts:
            render_table(get_recent_starts(filtered), "No events started in the last 10 days.")

        with tab_ends:
            render_table(get_recent_ends(filtered), "No events ended in the last 10 days.")

        with tab_all:
            render_table(filtered, "No events match the selected filters.")

        with tab_selected:
            sel_date = st.session_state.get("selected_date")
            if sel_date is None:
                st.info("Click a point on the chart to see active events for that date.")
            else:
                st.caption(f"Active events on {sel_date.strftime('%b %d %Y')}")
                events_on_date = filtered[
                    (filtered["START_DATE"] <= sel_date) & (filtered["END_DATE"] >= sel_date)
                ]
                render_table(events_on_date, "No active events for this date.")



if __name__ == "__main__":
    main()
