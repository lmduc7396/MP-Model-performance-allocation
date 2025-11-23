from pathlib import Path
from typing import List, Tuple

import altair as alt
import pandas as pd
import streamlit as st

# Streamlit app that visualizes the precomputed model portfolio performance
# (stored under analysis/) and provides attribution tables.

BASE_DIR = Path(__file__).resolve().parent
EXCEL_PATH = BASE_DIR / "ModelPort - demo allocation.xlsx"
SERIES_PATH = BASE_DIR / "analysis/mp_model_daily_series.csv"
ATTRIBUTION_PATH = BASE_DIR / "analysis/mp_model_daily_attribution.csv"
ANALYST_PATH = BASE_DIR / "Analyst in charge.xlsx"


def _parse_rebalance_date(label) -> pd.Timestamp:
    if isinstance(label, pd.Timestamp):
        return label.normalize()
    return pd.to_datetime(str(label), dayfirst=True).normalize()


@st.cache_data(show_spinner=False)
def load_rebalance_weights(path: Path = EXCEL_PATH) -> Tuple[pd.DataFrame, List[str]]:
    df = pd.read_excel(path)
    if "Ticker" not in df.columns:
        raise ValueError("Excel file must contain a 'Ticker' column.")
    df = df[~df["Ticker"].astype(str).str.contains("total", case=False, na=False)]
    value_cols = [c for c in df.columns if c != "Ticker"]
    date_map = {col: _parse_rebalance_date(col) for col in value_cols}

    melted = df.melt(
        id_vars="Ticker",
        value_vars=value_cols,
        var_name="RebalanceRaw",
        value_name="Weight",
    )
    melted["RebalanceDate"] = melted["RebalanceRaw"].map(date_map)
    melted["Ticker"] = melted["Ticker"].astype(str)

    ticker_mask = melted["Ticker"].str.fullmatch(r"[A-Z]{3}", na=False)
    melted.loc[ticker_mask, "Ticker"] = melted.loc[ticker_mask, "Ticker"].str.upper()
    cash_mask = melted["Ticker"].str.contains("cash", case=False, na=False)

    ticker_weights = (
        melted[ticker_mask]
        .pivot_table(index="RebalanceDate", columns="Ticker", values="Weight", aggfunc="first")
        .fillna(0.0)
    )
    cash_weights = (
        melted[cash_mask]
        .groupby("RebalanceDate")["Weight"]
        .sum()
        .rename("CASH")
    )
    weights = ticker_weights.copy()
    weights["CASH"] = cash_weights
    weights = weights.fillna(0.0).sort_index()
    weights.index = pd.to_datetime(weights.index)
    weights = weights[weights.index.notnull()]
    weights = weights.div(weights.sum(axis=1), axis=0)
    active_tickers = [c for c in weights.columns if c != "CASH"]
    return weights, active_tickers


@st.cache_data(show_spinner=False)
def load_series_data(path: Path, cache_bust: float) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["TRADE_DATE"])
    rename_map = {
        "ModelPortfolioIndex": "Model Portfolio",
        "OriginalPortfolioIndex": "Original Portfolio",
        "VNINDEX": "VNINDEX",
    }
    df = df.rename(columns=rename_map)
    expected_cols = ["TRADE_DATE", "Model Portfolio", "Original Portfolio", "VNINDEX"]
    missing = [col for col in expected_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Series CSV missing columns: {missing}")
    return df.sort_values("TRADE_DATE")


@st.cache_data(show_spinner=False)
def load_attribution_data(path: Path, cache_bust: float) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["TRADE_DATE"])
    df["Ticker"] = df["Ticker"].astype(str)
    return df


@st.cache_data(show_spinner=False)
def load_analyst_mapping(path: Path = ANALYST_PATH) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["Ticker", "Analyst"])
    df = pd.read_excel(path)
    df = df.rename(columns={"Analyst in charge": "Analyst"})
    df["Ticker"] = df["Ticker"].astype(str).str.upper()
    df["Analyst"] = df["Analyst"].fillna("No assignment")
    return df[["Ticker", "Analyst"]]


def format_attribution_table(df: pd.DataFrame) -> pd.DataFrame:
    display_cols = [
        "Ticker",
        "AvgPortfolioWeightYTD",
        "AvgBenchmarkWeightYTD",
        "ActiveWeightYTD",
        "TickerReturn",
        "ActiveReturn",
        "Attribution",
    ]
    table = df[display_cols].copy()
    weight_cols = [
        "AvgPortfolioWeightYTD",
        "AvgBenchmarkWeightYTD",
        "ActiveWeightYTD",
    ]
    return_cols = ["TickerReturn", "ActiveReturn"]
    for col in weight_cols:
        if col in table.columns:
            table[col] = (table[col] * 100).round(2)
    for col in return_cols:
        if col in table.columns:
            table[col] = (table[col] * 100).round(2)
    table = table.rename(
        columns={
            "AvgPortfolioWeightYTD": "Avg Port Weight (%)",
            "AvgBenchmarkWeightYTD": "Avg Bench Weight (%)",
            "ActiveWeightYTD": "Active Weight (%)",
            "TickerReturn": "Return (%)",
            "ActiveReturn": "Active Return (%)",
        }
    )
    table["Attribution"] = (table["Attribution"] * 10000).round(2)
    table = table.rename(columns={"Attribution": "Attribution (bps)"})
    return table


def main() -> None:
    st.set_page_config(page_title="MP Model Portfolio Tracker", layout="wide")
    st.title("MP Model Portfolio vs Benchmarks")

    try:
        weights, _ = load_rebalance_weights()
    except Exception as exc:
        st.error(f"Failed to load allocation file: {exc}")
        return

    series_cache = SERIES_PATH.stat().st_mtime if SERIES_PATH.exists() else 0.0
    chart_df = load_series_data(SERIES_PATH, series_cache)
    if chart_df.empty:
        st.error("Series data CSV not found or empty. Run calc_daily_attribution.py locally to refresh.")
        return
    chart_df = chart_df.set_index("TRADE_DATE")

    last_date = chart_df.index.max().date()
    st.write(f"Data through **{last_date}** (rebalance dates: {', '.join(d.strftime('%d-%b-%Y') for d in weights.index)})")

    col1, col2, col3 = st.columns(3)
    model_series = chart_df["Model Portfolio"]
    vn_series = chart_df["VNINDEX"]
    baseline_series = chart_df["Original Portfolio"]
    with col1:
        st.metric(
            "Model Portfolio",
            f"{model_series.iloc[-1]:.2f}",
            f"{(model_series.iloc[-1] / model_series.iloc[0] - 1) * 100:.2f}% YTD",
        )
    with col2:
        st.metric(
            "Original Portfolio",
            f"{baseline_series.iloc[-1]:.2f}",
            f"{(baseline_series.iloc[-1] / baseline_series.iloc[0] - 1) * 100:.2f}% YTD",
        )
    with col3:
        st.metric(
            "VNINDEX",
            f"{vn_series.iloc[-1]:.2f}",
            f"{(vn_series.iloc[-1] / vn_series.iloc[0] - 1) * 100:.2f}% YTD",
        )

    chart_source = (
        chart_df.reset_index()
        .melt(id_vars="TRADE_DATE", var_name="Series", value_name="Value")
    )
    y_max = float(chart_source["Value"].max())
    chart = (
        alt.Chart(chart_source)
        .mark_line(strokeWidth=2)
        .encode(
            x=alt.X("TRADE_DATE:T", title="Date"),
            y=alt.Y(
                "Value:Q",
                title="Index (Base = 100)",
                scale=alt.Scale(domain=[80, max(80, y_max * 1.05)]),
            ),
            color=alt.Color(
                "Series:N",
                scale=alt.Scale(
                    domain=["Model Portfolio", "Original Portfolio", "VNINDEX"],
                    range=["#2ecc71", "#e67e22", "#1f77b4"],
                ),
            ),
            tooltip=["TRADE_DATE:T", "Series:N", alt.Tooltip("Value:Q", format=".2f")],
        )
    )
    rebalance_source = pd.DataFrame({"RebalanceDate": weights.index})
    rebalance_chart = (
        alt.Chart(rebalance_source)
        .mark_rule(color="#7f8c8d", strokeDash=[6, 4])
        .encode(x=alt.X("RebalanceDate:T", title="Date"))
    )
    st.altair_chart(chart + rebalance_chart, use_container_width=True)
    st.caption(
        f"Dashed vertical lines mark portfolio rebalances: {', '.join(d.strftime('%d-%b-%Y') for d in weights.index)}."
    )

    csv_data = chart_df.reset_index().to_csv(index=False).encode()
    st.download_button("Download Chart Data (CSV)", csv_data, file_name="mp_model_series.csv")

    st.header("Attribution Snapshot")
    attr_cache = ATTRIBUTION_PATH.stat().st_mtime if ATTRIBUTION_PATH.exists() else 0.0
    attr_df = load_attribution_data(ATTRIBUTION_PATH, attr_cache)
    if attr_df.empty:
        st.info(
            "Attribution data not found. Run `python calc_daily_attribution.py` locally to refresh"
            " `analysis/mp_model_daily_attribution.csv`."
        )
        return

    available_dates = sorted(attr_df["TRADE_DATE"].dt.date.unique())
    default_start = available_dates[0]
    default_end = available_dates[-1]

    col_from, col_to = st.columns(2)
    with col_from:
        from_date = st.date_input(
            "From date",
            value=default_start,
            min_value=available_dates[0],
            max_value=available_dates[-1],
        )
    with col_to:
        to_date = st.date_input(
            "To date",
            value=default_end,
            min_value=available_dates[0],
            max_value=available_dates[-1],
        )

    if from_date > to_date:
        st.warning("`From date` must be earlier than or equal to `To date`.")
        return

    mask = (attr_df["TRADE_DATE"].dt.date >= from_date) & (attr_df["TRADE_DATE"].dt.date <= to_date)
    selected_df = attr_df[mask]
    if selected_df.empty:
        st.warning("No attribution data in the selected range.")
        return

    grouped = selected_df.groupby("Ticker")
    agg_spec = {
        "AvgPortfolioWeightYTD": ("AvgPortfolioWeightYTD", "mean"),
        "AvgBenchmarkWeightYTD": ("AvgBenchmarkWeightYTD", "mean"),
        "ActiveWeightYTD": ("ActiveWeightYTD", "mean"),
        "TickerReturn": ("TickerReturn", "mean"),
        "ActiveReturn": ("ActiveReturn", "mean"),
        "Attribution": ("Attribution", "sum"),
    }
    optional_specs = {
        "AvgBaselineWeightYTD": ("AvgBaselineWeightYTD", "mean"),
        "ActiveWeightVsOriginal": ("ActiveWeightVsOriginal", "mean"),
        "ActiveReturnVsOriginal": ("ActiveReturnVsOriginal", "mean"),
        "AttributionVsOriginal": ("AttributionVsOriginal", "sum"),
    }
    for col_name, spec in optional_specs.items():
        if col_name in selected_df.columns:
            agg_spec[col_name] = spec
    agg = grouped.agg(**agg_spec).reset_index()

    def _cumulative_return(series: pd.Series) -> float:
        return (1 + series).prod() - 1

    if "TickerReturn" in selected_df.columns:
        agg["TickerReturn"] = (
            grouped["TickerReturn"].apply(_cumulative_return).reindex(agg["Ticker"]).to_numpy()
        )
    if "ActiveReturn" in selected_df.columns:
        agg["ActiveReturn"] = (
            grouped["ActiveReturn"].apply(_cumulative_return).reindex(agg["Ticker"]).to_numpy()
        )

    for col_name in optional_specs:
        if col_name not in agg.columns:
            agg[col_name] = 0.0

    agg = agg.sort_values("Attribution", ascending=False)
    positive = agg.head(10)
    negative = agg.tail(10).sort_values("Attribution", ascending=True)

    st.subheader("Top Positive Contributors")
    st.dataframe(
        format_attribution_table(positive),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Top Negative Contributors")
    st.dataframe(
        format_attribution_table(negative),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("All Tickers")
    st.dataframe(
        format_attribution_table(agg),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Analyst Leaderboard")
    analyst_map = load_analyst_mapping()
    if analyst_map.empty:
        st.info("Analyst mapping file not found or empty.")
    else:
        merged = agg.merge(analyst_map, on="Ticker", how="left").fillna({"Analyst": "No assignment"})
        leaderboard = (
            merged.groupby("Analyst", as_index=False)[["Attribution", "AttributionVsOriginal"]]
            .sum()
            .sort_values("Attribution", ascending=False)
        )
        leaderboard["Attribution vs VNINDEX (bps)"] = (
            leaderboard["Attribution"] * 10000
        ).round(2)
        leaderboard["Attribution vs Original (bps)"] = (
            leaderboard["AttributionVsOriginal"] * 10000
        ).round(2)
        leaderboard = leaderboard.drop(columns=["Attribution", "AttributionVsOriginal"])
        st.dataframe(
            leaderboard,
            use_container_width=True,
            hide_index=True,
        )


if __name__ == "__main__":
    main()
