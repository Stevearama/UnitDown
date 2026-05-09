import pandas as pd

MIN_CHART_DATE = pd.Timestamp("2021-01-01")


def build_capacity_data(df: pd.DataFrame, years: list = None) -> pd.DataFrame:
    """Build daily total operational capacity using a cumulative-sum approach.

    Each unit contributes its U_CAPACITY from START_DATE to END_DATE (or end of
    the selected window if no END_DATE). Returns a DataFrame with the same schema
    as build_seasonality_data so build_chart() can be reused unchanged:
    columns: date, CAP_OFFLINE, year, plot_date
    """
    if years:
        selected_years = sorted(y for y in years if y >= MIN_CHART_DATE.year)
    else:
        selected_years = sorted(
            y for y in df["START_DATE"].dropna().dt.year.unique() if y >= MIN_CHART_DATE.year
        )

    if not selected_years:
        return pd.DataFrame(columns=["date", "CAP_OFFLINE", "year", "plot_date"])

    max_date = pd.Timestamp(f"{max(selected_years)}-12-31")
    # Always compute from MIN_CHART_DATE so units operating before the first selected
    # year are correctly accumulated before their closure subtractions are applied.
    full_range = pd.date_range(MIN_CHART_DATE, max_date, freq="D")

    valid = df.dropna(subset=["U_CAPACITY"]).copy()
    valid = valid[valid["U_CAPACITY"] > 0]

    # Resolve raw date range per unit, defaulting unknowns to window boundaries
    valid["raw_start"] = valid["START_DATE"].fillna(MIN_CHART_DATE)
    valid["raw_end"] = valid["END_DATE"].fillna(max_date)

    # Drop units whose entire operating life falls outside the window
    valid = valid[(valid["raw_end"] >= MIN_CHART_DATE) & (valid["raw_start"] <= max_date)]

    if valid.empty:
        return pd.DataFrame(columns=["date", "CAP_OFFLINE", "year", "plot_date"])

    valid["eff_start"] = valid["raw_start"].clip(lower=MIN_CHART_DATE, upper=max_date)
    valid["eff_end"] = valid["raw_end"].clip(lower=MIN_CHART_DATE, upper=max_date)

    # Capacity delta events: +cap on first active day, -cap on day after last active day
    starts = valid.groupby("eff_start")["U_CAPACITY"].sum()
    ends = valid.groupby("eff_end")["U_CAPACITY"].sum()
    ends.index = ends.index + pd.Timedelta(days=1)

    all_deltas = pd.concat([starts, -ends]).groupby(level=0).sum()
    capacity = all_deltas.reindex(full_range, fill_value=0).cumsum()

    result = capacity.reset_index()
    result.columns = ["date", "CAP_OFFLINE"]
    result["year"] = result["date"].dt.year
    result["plot_date"] = result["date"].apply(lambda d: d.replace(year=2000))

    return result[result["date"].dt.year.isin(set(selected_years))]


def build_capacity_timeline_data(df: pd.DataFrame, years: list = None) -> pd.DataFrame:
    """Build daily total capacity by unit type for a timeline chart."""
    frames = []
    for utype in df["UTYPE_DESC"].unique():
        cap = build_capacity_data(df[df["UTYPE_DESC"] == utype], years)
        if not cap.empty:
            cap["UTYPE_DESC"] = utype
            frames.append(cap[["date", "UTYPE_DESC", "CAP_OFFLINE"]])
    if not frames:
        return pd.DataFrame(columns=["date", "UTYPE_DESC", "CAP_OFFLINE"])
    return pd.concat(frames, ignore_index=True)
