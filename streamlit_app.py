import os
from pathlib import Path
from typing import List, Tuple

import altair as alt
import numpy as np
import pandas as pd
import pyodbc
import streamlit as st
from dotenv import load_dotenv

# Streamlit app that recalculates the MP model portfolio performance on the fly
# and plots it against VNINDEX with a YTD (base 100) view.

BASE_DIR = Path(__file__).resolve().parent
EXCEL_PATH = BASE_DIR / "ModelPort - demo allocation.xlsx"
ENV_PATH = BASE_DIR / ".env"
ATTRIBUTION_PATH = BASE_DIR / "analysis/mp_model_daily_attribution.csv"
ANALYST_PATH = BASE_DIR / "Analyst in charge.xlsx"
ODBC_DRIVER = "/Users/ducle/Coding-Chat/libmsodbcsql.18.dylib"
ODBCINST_PATH = "/Users/ducle/Coding-Chat/odbcinst.ini"


def _ensure_env_loaded() -> None:
    """Load SQL credentials once per process."""
    if all(key in st.secrets for key in ["SQL_SERVER", "SQL_DATABASE", "SQL_USERNAME", "SQL_PASSWORD"]):
        os.environ.setdefault("SQL_SERVER", st.secrets["SQL_SERVER"])
        os.environ.setdefault("SQL_DATABASE", st.secrets["SQL_DATABASE"])
        os.environ.setdefault("SQL_USERNAME", st.secrets["SQL_USERNAME"])
        os.environ.setdefault("SQL_PASSWORD", st.secrets["SQL_PASSWORD"])
    elif "SQL_SERVER" not in os.environ:
        load_dotenv(ENV_PATH)
    os.environ.setdefault("ODBCINSTINI", ODBCINST_PATH)


def _get_connection() -> pyodbc.Connection:
    """Create a pyodbc connection using the bundled driver."""
    _ensure_env_loaded()
    connection_string = (
        f"DRIVER={ODBC_DRIVER};"
        f"SERVER={os.environ['SQL_SERVER']};"
        f"DATABASE={os.environ['SQL_DATABASE']};"
        f"UID={os.environ['SQL_USERNAME']};"
        f"PWD={os.environ['SQL_PASSWORD']};"
        "Encrypt=yes;TrustServerCertificate=no;"
    )
    return pyodbc.connect(connection_string)


def _parse_rebalance_date(label) -> pd.Timestamp:
    """Normalize Excel column headers into midnight timestamps."""
    if isinstance(label, pd.Timestamp):
        return label.normalize()
    return pd.to_datetime(str(label), dayfirst=True).normalize()


@st.cache_data(show_spinner=False)
def load_rebalance_weights(path: Path = EXCEL_PATH) -> Tuple[pd.DataFrame, List[str]]:
    """Load weights from Excel, keep 3-letter tickers + cash, normalize to 1."""
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
            .pivot_table(
                index="RebalanceDate",
                columns="Ticker",
                values="Weight",
                aggfunc="first",
            )
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
def fetch_price_history(tickers: List[str], start_date: pd.Timestamp) -> pd.DataFrame:
    """Fetch PX_LAST history for the requested tickers from Market_Data."""
    if not tickers:
        return pd.DataFrame()
    query = f"""
        SELECT TICKER, TRADE_DATE, PX_LAST
        FROM dbo.Market_Data
        WHERE TICKER IN ({",".join("?" for _ in tickers)})
          AND TRADE_DATE >= ?
        ORDER BY TRADE_DATE ASC
    """
    params = tickers + [start_date.date()]
    with _get_connection() as conn:
        df = pd.read_sql(query, conn, params=params, parse_dates=["TRADE_DATE"])
    pivot = (
        df.pivot_table(index="TRADE_DATE", columns="TICKER", values="PX_LAST")
        .sort_index()
        .ffill()
    )
    return pivot


@st.cache_data(show_spinner=False)
def fetch_vnindex(start_date: pd.Timestamp) -> pd.DataFrame:
    """Fetch VNINDEX levels from MarketIndex table."""
    query = """
        SELECT TRADINGDATE, INDEXVALUE
        FROM dbo.MarketIndex
        WHERE COMGROUPCODE = 'VNINDEX'
          AND TRADINGDATE >= ?
        ORDER BY TRADINGDATE ASC;
    """
    with _get_connection() as conn:
        df = pd.read_sql(
            query,
            conn,
            params=[start_date.date()],
            parse_dates=["TRADINGDATE"],
        )
    df = df.rename(columns={"TRADINGDATE": "TRADE_DATE"})
    df = df.set_index("TRADE_DATE").sort_index()
    return df


@st.cache_data(show_spinner=False)
def load_attribution_data(path: Path, cache_bust: float) -> pd.DataFrame:
    """Load attribution results saved by calc_daily_attribution.py."""
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


def simulate_portfolio(weights: pd.DataFrame, price_history: pd.DataFrame) -> pd.DataFrame:
    """Apply the rebalance rules to produce a daily portfolio index."""
    if weights.empty or price_history.empty:
        return pd.DataFrame()
    active_tickers = [c for c in weights.columns if c != "CASH"]
    common_cols = [t for t in active_tickers if t in price_history.columns]
    if not common_cols:
        raise ValueError("No overlap between weights and available price history.")
    prices = price_history[common_cols].loc[price_history.index >= weights.index.min()]

    units = pd.Series(0.0, index=common_cols)
    cash_balance = 0.0
    records = []
    rebalance_dates = list(weights.index)
    rebalance_idx = 0

    for date, px in prices.iterrows():
        while rebalance_idx < len(rebalance_dates) and date >= rebalance_dates[rebalance_idx]:
            target_date = rebalance_dates[rebalance_idx]
            portfolio_value = float((units * px).sum() + cash_balance)
            if rebalance_idx == 0:
                portfolio_value = 100.0
            target_weights = weights.loc[target_date]
            cash_balance = portfolio_value * target_weights.get("CASH", 0.0)
            for ticker in common_cols:
                weight = target_weights.get(ticker, 0.0)
                allocation = portfolio_value * weight
                price = px[ticker]
                units[ticker] = allocation / price if price and not np.isnan(price) else 0.0
            rebalance_idx += 1
        portfolio_value = float((units * px).sum() + cash_balance)
        records.append((date, portfolio_value, cash_balance))

    portfolio = pd.DataFrame(
        records,
        columns=["TRADE_DATE", "PortfolioValue", "CashBalance"],
    ).set_index("TRADE_DATE")
    portfolio["PortfolioIndex"] = (
        portfolio["PortfolioValue"] / portfolio["PortfolioValue"].iloc[0] * 100
    )
    portfolio["DailyReturn"] = portfolio["PortfolioValue"].pct_change()
    return portfolio


def simulate_static_portfolio(weights: pd.DataFrame, price_history: pd.DataFrame) -> pd.DataFrame:
    """Simulate the initial portfolio without any future rebalancing."""
    if weights.empty:
        return pd.DataFrame()
    initial_weights = weights.iloc[0]
    start_date = weights.index.min()
    tickers = [c for c in initial_weights.index if c != "CASH"]
    common_cols = [t for t in tickers if t in price_history.columns]
    if not common_cols or start_date not in price_history.index:
        return pd.DataFrame()
    prices = price_history[common_cols].loc[price_history.index >= start_date]
    units = pd.Series(0.0, index=common_cols)
    start_prices = prices.loc[start_date]
    portfolio_value = 100.0
    cash_balance = portfolio_value * initial_weights.get("CASH", 0.0)
    for ticker in common_cols:
        weight = initial_weights.get(ticker, 0.0)
        allocation = portfolio_value * weight
        price = start_prices[ticker]
        units[ticker] = allocation / price if price and not np.isnan(price) else 0.0

    records = []
    for date, px in prices.iterrows():
        portfolio_value = float((units * px).sum() + cash_balance)
        records.append((date, portfolio_value, cash_balance))

    portfolio = pd.DataFrame(
        records,
        columns=["TRADE_DATE", "PortfolioValue", "CashBalance"],
    ).set_index("TRADE_DATE")
    portfolio["PortfolioIndex"] = (
        portfolio["PortfolioValue"] / portfolio["PortfolioValue"].iloc[0] * 100
    )
    portfolio["DailyReturn"] = portfolio["PortfolioValue"].pct_change()
    return portfolio


def format_chart_data(
    portfolio: pd.DataFrame, vnindex: pd.DataFrame, baseline: pd.DataFrame
) -> pd.DataFrame:
    """Align the three series on shared dates and rebase to 100."""
    columns = {
        "Model Portfolio": portfolio["PortfolioIndex"],
        "VNINDEX": (vnindex["INDEXVALUE"] / vnindex["INDEXVALUE"].iloc[0] * 100),
    }
    if baseline is not None and not baseline.empty:
        columns["Original Portfolio"] = baseline["PortfolioIndex"]
    combined = pd.DataFrame(columns).dropna()
    return combined


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
    st.title("MP Model Portfolio vs VNINDEX (YTD Base = 100)")

    try:
        weights, tickers = load_rebalance_weights()
    except Exception as exc:
        st.error(f"Failed to load allocation file: {exc}")
        st.stop()

    start_date = weights.index.min()
    price_history = fetch_price_history(tickers, start_date)
    portfolio = simulate_portfolio(weights, price_history)
    baseline_portfolio = simulate_static_portfolio(weights, price_history)
    vnindex = fetch_vnindex(start_date)
    chart_df = format_chart_data(portfolio, vnindex, baseline_portfolio)

    if chart_df.empty:
        st.warning("No overlapping data between the model portfolio and VNINDEX.")
        st.stop()

    last_date = chart_df.index.max().date()
    st.write(f"Data through **{last_date}** (rebalance dates: {', '.join(d.strftime('%d-%b-%Y') for d in weights.index)})")

    col1, col2 = st.columns(2)
    with col1:
        st.metric(
            "Model Portfolio",
            f"{chart_df['Model Portfolio'].iloc[-1]:.2f}",
            f"{(chart_df['Model Portfolio'].iloc[-1] / chart_df['Model Portfolio'].iloc[0] - 1) * 100:.2f}% YTD",
        )
    with col2:
        st.metric(
            "VNINDEX",
            f"{chart_df['VNINDEX'].iloc[-1]:.2f}",
            f"{(chart_df['VNINDEX'].iloc[-1] / chart_df['VNINDEX'].iloc[0] - 1) * 100:.2f}% YTD",
        )

    chart_source = (
        chart_df.reset_index()
        .rename(columns={"index": "TRADE_DATE"})
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
                title="Index (Base 100)",
                scale=alt.Scale(domain=[80, max(80, y_max * 1.05)]),
            ),
            color=alt.Color(
                "Series:N",
                scale=alt.Scale(
                    domain=["Model Portfolio", "VNINDEX", "Original Portfolio"],
                    range=["#2ecc71", "#1f77b4", "#e67e22"],
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
    rebalance_list = ", ".join(d.strftime("%d-%b-%Y") for d in weights.index)
    st.caption(f"Dashed vertical lines mark portfolio rebalances: {rebalance_list}.")

    csv_data = chart_df.reset_index().rename(columns={"index": "TRADE_DATE"}).to_csv(index=False).encode()
    st.download_button("Download Chart Data (CSV)", csv_data, file_name="mp_model_vs_vni.csv")

    st.header("Attribution Snapshot")
    cache_bust = ATTRIBUTION_PATH.stat().st_mtime if ATTRIBUTION_PATH.exists() else 0.0
    attr_df = load_attribution_data(ATTRIBUTION_PATH, cache_bust)
    if attr_df.empty:
        st.info(
            "Attribution data not found. Run `python calc_daily_attribution.py` to refresh "
            "`analysis/mp_model_daily_attribution.csv`."
        )
    else:
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
        else:
            mask = (attr_df["TRADE_DATE"].dt.date >= from_date) & (
                attr_df["TRADE_DATE"].dt.date <= to_date
            )
            selected_df = attr_df[mask]
            if selected_df.empty:
                st.warning("No attribution data in the selected range.")
            else:
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

                # Replace return columns with cumulative returns over the window
                def _cumulative_return(series: pd.Series) -> float:
                    return (1 + series).prod() - 1

                if "TickerReturn" in selected_df.columns:
                    cum_ret = (
                        grouped["TickerReturn"]
                        .apply(_cumulative_return)
                        .reindex(agg["Ticker"])
                        .to_numpy()
                    )
                    agg["TickerReturn"] = cum_ret
                if "ActiveReturn" in selected_df.columns:
                    cum_active = (
                        grouped["ActiveReturn"]
                        .apply(_cumulative_return)
                        .reindex(agg["Ticker"])
                        .to_numpy()
                    )
                    agg["ActiveReturn"] = cum_active

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
                    merged = agg.merge(
                        analyst_map, on="Ticker", how="left"
                    ).fillna({"Analyst": "No assignment"})
                    if "AttributionVsOriginal" not in merged.columns:
                        merged["AttributionVsOriginal"] = 0.0
                    else:
                        merged["AttributionVsOriginal"] = merged[
                            "AttributionVsOriginal"
                        ].fillna(0.0)
                    leaderboard = (
                        merged.groupby("Analyst", as_index=False)[
                            ["Attribution", "AttributionVsOriginal"]
                        ]
                        .sum()
                        .sort_values("Attribution", ascending=False)
                    )
                    leaderboard["Attribution vs VNINDEX (bps)"] = (
                        leaderboard["Attribution"] * 10000
                    ).round(2)
                    leaderboard["Attribution vs Original (bps)"] = (
                        leaderboard["AttributionVsOriginal"] * 10000
                    ).round(2)
                    leaderboard = leaderboard.drop(
                        columns=["Attribution", "AttributionVsOriginal"]
                    )
                    st.dataframe(
                        leaderboard,
                        use_container_width=True,
                        hide_index=True,
                    )


if __name__ == "__main__":
    main()
