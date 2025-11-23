# dclab Database Schema

Banking and Brokerage data live in their own curated tables, while every other sector pulls from the shared fundamentals/forecast source set (`FA_Annual`, `Forecast`, etc.).

## Access Notes (Codex CLI)

- The repo root `.env` (gitignored) must contain the discrete credentials below so every MCP agent or script can hydrate them via `python-dotenv`:
  ```
  SQL_SERVER=sqls-dclab.database.windows.net
  SQL_DATABASE=dclab
  SQL_USERNAME=dclab_readonly
  SQL_PASSWORD=DHS#@vGESADdf!
  ```
- `test.py` shows the canonical connection/query pattern. Every other script should follow the exact same flow:
  ```python
  from dotenv import load_dotenv
  import os
  import pandas as pd
  import pyodbc

  load_dotenv()
  connection_string = (
      "DRIVER={ODBC Driver 18 for SQL Server};"
      f"SERVER={os.environ['SQL_SERVER']};"
      f"DATABASE={os.environ['SQL_DATABASE']};"
      f"UID={os.environ['SQL_USERNAME']};"
      f"PWD={os.environ['SQL_PASSWORD']};"
      "Encrypt=yes;TrustServerCertificate=no;"
  )

  with pyodbc.connect(connection_string) as conn:
      df = pd.read_sql(
          "SELECT TOP 5 * FROM Market_Data ORDER BY TRADE_DATE DESC",
          conn,
      )
      print(df)
  ```
- Keep the environment pointed at **ODBC Driver 18 for SQL Server**: export `ODBCINSTINI=/opt/homebrew/etc/odbcinst.ini` (and optionally `ODBCINI=/opt/homebrew/etc/odbc.ini`) so unixODBC can find the driver definition.
- If Driver 18 still cannot be opened, reference the dylib directly, e.g. `DRIVER=/opt/homebrew/lib/libmsodbcsql.18.dylib` or the bundled `./libmsodbcsql.18.dylib`.
- Make sure SQL commands run from the repo root with network access enabled; outbound connections usually require Codex escalation.

## Table Summary by Domain

### Reference & Mapping

_Lightweight lookup tables shared by every module._

| Table | Type | Columns | Primary Key | Purpose |
| --- | --- | --- | --- | --- |
| `dbo.Sector_Map` | BASE TABLE | 14 | — | Maps stock ticker to sector hierarchy and export classifications. |
| `dbo.Ticker_Reference` | BASE TABLE | 5 | Ticker | Ticker list for commodities data. |

### Aviation Metrics

_Commercial aviation KPIs across fares, market metrics, operating stats, and revenue mix._

| Table | Type | Columns | Primary Key | Purpose |
| --- | --- | --- | --- | --- |
| `dbo.Aviation_Airfare` | BASE TABLE | 7 | Date, Airline, Route, Flight_time, Booking_period | Fare quotes sliced by airline, route, and booking/flight window. |
| `dbo.Aviation_Market` | BASE TABLE | 6 | Date, Metric_type, Metric_name | High-level market indicators (capacity, demand, yield) per day. |
| `dbo.Aviation_Operations` | BASE TABLE | 8 | Date, Period_type, Airline, Metric_type, Traffic_type | Operational stats (traffic type, period) to read volume & efficiency. |
| `dbo.Aviation_Revenue` | BASE TABLE | 8 | Year, Quarter, Airline, Revenue_type | Quarterly revenue mix per airline and revenue stream. |

### Banking Sector

_Dedicated banking warehouse: structured metrics, qualitative commentary, and supporting drivers._

| Table | Type | Columns | Primary Key | Purpose |
| --- | --- | --- | --- | --- |
| `dbo.Bank_Rates` | BASE TABLE | 7 | Bank, Date | Posted deposit-rate ladder per bank/date. |
| `dbo.BankingMetrics` | BASE TABLE | 50 | — | Banking metrics snapshot (TOI, PBT, asset quality, ratios) per reporting period. |
| `dbo.Banking_Drivers` | BASE TABLE | 107 | — | Detailed input file with >100 driver columns feeding banking models. |
| `dbo.Banking_Comments` | BASE TABLE | 4 | — | Detailed analyst commentary quarterly for banking tickers |

### Brokerage Sector

_Separate brokerage dataset capturing commentary, prop-book metrics, and KPIs._

| Table | Type | Columns | Primary Key | Purpose |
| --- | --- | --- | --- | --- |
| `dbo.BrokerageMetrics` | BASE TABLE | 12 | — | Brokerage metrics (volumes, revenue lines, capital metrics). |
| `dbo.Brokerage_Propbook` | BASE TABLE | 5 | Broker, Quarter, Ticker, Keycode | Exposure per broker/ticker/quarter for proprietary books. |
| `dbo.Brokerage_Comments` | BASE TABLE | 4 | — | Detailed analyst commentary quarterly for brokerage tickers |

### Commodities & Industrial Prices

_Daily spot/benchmark prices across core export sectors, all sharing the common ingestion feed._

| Table | Type | Columns | Primary Key | Purpose |
| --- | --- | --- | --- | --- |
| `dbo.Agricultural` | BASE TABLE | 3 | Ticker, Date | Agricultural commodity prices by ticker/date. |
| `dbo.Chemicals` | BASE TABLE | 3 | Ticker, Date | Chemical product benchmarks tracked by ticker/date. |
| `dbo.Energy` | BASE TABLE | 3 | Ticker, Date | Energy commodity quotes (e.g., coal, gas) by ticker/date. |
| `dbo.Fertilizer` | BASE TABLE | 3 | Ticker, Date | Fertiliser price curves per product. |
| `dbo.Fishery` | BASE TABLE | 7 | Date, Company, Market | Fishery KPIs (production, market) captured alongside prices. |
| `dbo.Livestock` | BASE TABLE | 3 | Ticker, Date | Livestock pricing feed. |
| `dbo.Metals` | BASE TABLE | 3 | Ticker, Date | Industrial metal prices. |
| `dbo.Shipping_Freight` | BASE TABLE | 3 | Ticker, Date | Freight rate indexes (BDI, containers). |
| `dbo.Steel` | BASE TABLE | 3 | Ticker, Date | Steel benchmark prices. |
| `dbo.Textile` | BASE TABLE | 3 | Ticker, Date | Textile/fabric price monitors. |
| `dbo.Container_volume` | BASE TABLE | 5 | — | Trade proxy measuring container throughput. |
| `dbo.Monthly_Income` | BASE TABLE | 5 | — | Macro survey of income levels (urban/rural/national). |



### Shared Forecasting & Fundamentals

_Common source tables feeding every non-bank/brokerage sector (financials, forecasts, uploads)._

| Table | Type | Columns | Primary Key | Purpose |
| --- | --- | --- | --- | --- |
| `dbo.FA_Annual` | BASE TABLE | 6 | — | Model-ready annual financial statements per ticker. |
| `dbo.FA_Quarterly` | BASE TABLE | 7 | — | Quarterly financials with the same schema as annual table. |
| `dbo.Forecast` | BASE TABLE | 9 | — | Internal forecast outputs (base/hi/lo) for tracked tickers. |
| `dbo.Forecast_Consensus` | BASE TABLE | 8 | — | Consensus datapoints captured alongside internal forecast. |

### Market Data & Valuation

_Market tape joins plus reference helpers used across dashboards._

| Table | Type | Columns | Primary Key | Purpose |
| --- | --- | --- | --- | --- |
| `dbo.Market_Data` | BASE TABLE | 14 | TICKER, TRADE_DATE | Daily market metrics (price, ratios, liquidity) per ticker. |
| `dbo.MarketIndex` | BASE TABLE | 30 | — | Index-level stats including breadth and foreign flow. |
| `dbo.MarketCap` | BASE TABLE | 3 | — | Point-in-time market cap snapshots. |
| `dbo.Valuation` | BASE TABLE | 6 | — | Quick reference of valuation multiples (string form). |


## Detailed Table Definitions

### `dbo.Agricultural`

Type: BASE TABLE  
Primary key: Ticker, Date

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `Ticker` | varchar(50) | NO |  |
| `Date` | date | NO |  |
| `Price` | decimal(18,6) | YES |  |

### `dbo.Aviation_Airfare`

Type: BASE TABLE  
Primary key: Date, Airline, Route, Flight_time, Booking_period

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `Date` | date | NO |  |
| `Airline` | varchar(50) | NO |  |
| `Route` | varchar(20) | NO |  |
| `Flight_time` | varchar(10) | NO |  |
| `Booking_period` | varchar(10) | NO |  |
| `Fare` | decimal(12,2) | NO |  |
| `Created_date` | datetime | YES |  |

### `dbo.Aviation_Market`

Type: BASE TABLE  
Primary key: Date, Metric_type, Metric_name

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `Date` | date | NO |  |
| `Metric_type` | varchar(50) | NO |  |
| `Metric_name` | varchar(100) | NO |  |
| `Metric_value` | decimal(18,3) | YES |  |
| `Unit` | varchar(20) | YES |  |
| `Created_date` | datetime | YES |  |

### `dbo.Aviation_Operations`

Type: BASE TABLE  
Primary key: Date, Period_type, Airline, Metric_type, Traffic_type

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `Date` | date | NO |  |
| `Period_type` | varchar(20) | NO |  |
| `Airline` | varchar(50) | NO |  |
| `Metric_type` | varchar(50) | NO |  |
| `Traffic_type` | varchar(20) | NO |  |
| `Metric_value` | decimal(18,3) | YES |  |
| `Unit` | varchar(20) | YES |  |
| `Created_date` | datetime | YES |  |

### `dbo.Aviation_Revenue`

Type: BASE TABLE  
Primary key: Year, Quarter, Airline, Revenue_type

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `Date` | date | NO |  |
| `Year` | int | NO |  |
| `Quarter` | int | NO |  |
| `Airline` | varchar(50) | NO |  |
| `Revenue_type` | varchar(50) | NO |  |
| `Revenue_amount` | decimal(18,2) | YES |  |
| `Currency` | varchar(10) | YES |  |
| `Created_date` | datetime | YES |  |

### `dbo.Bank_Rates`

Type: BASE TABLE  
Primary key: Bank, Date

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `Bank` | nvarchar(50) | NO |  |
| `Date` | datetime | NO |  |
| `rate_1` | nvarchar(50) | YES |  |
| `rate_3` | nvarchar(50) | YES |  |
| `rate_6` | nvarchar(50) | YES |  |
| `rate_9` | nvarchar(50) | YES |  |
| `rate_12` | nvarchar(50) | YES |  |

### `dbo.Banking_Comments`

Type: BASE TABLE  
Primary key: —

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `TICKER` | nvarchar(50) | YES |  |
| `SECTOR` | nvarchar(50) | YES |  |
| `DATE` | nvarchar(50) | YES |  |
| `COMMENT` | nvarchar(max) | YES |  |

### `dbo.Banking_Drivers`

Type: BASE TABLE  
Primary key: —

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `TICKER` | nvarchar(50) | YES |  |
| `Type` | nvarchar(50) | YES |  |
| `DATE` | nvarchar(50) | YES |  |
| `TOI` | nvarchar(50) | YES |  |
| `Net Interest Income` | nvarchar(50) | YES |  |
| `Fees Income` | nvarchar(50) | YES |  |
| `OPEX` | nvarchar(50) | YES |  |
| `Provision expense` | nvarchar(50) | YES |  |
| `PBT` | nvarchar(50) | YES |  |
| `Loan` | nvarchar(50) | YES |  |
| `NIM` | nvarchar(50) | YES |  |
| `Core TOI` | nvarchar(50) | YES |  |
| `Core PBT` | nvarchar(50) | YES |  |
| `Non-recurring income` | nvarchar(50) | YES |  |
| `Core TOI_T12M` | nvarchar(50) | YES |  |
| `PBT_T12M` | nvarchar(50) | YES |  |
| `OPEX_T12M` | nvarchar(50) | YES |  |
| `Provision expense_T12M` | nvarchar(50) | YES |  |
| `Non-recurring income_T12M` | nvarchar(50) | YES |  |
| `Net Interest Income_T12M` | nvarchar(50) | YES |  |
| `Fees Income_T12M` | nvarchar(50) | YES |  |
| `Loan_T12M` | nvarchar(50) | YES |  |
| `NIM_T12M` | nvarchar(50) | YES |  |
| `Core_TOI_Change` | nvarchar(50) | YES |  |
| `PBT_Change` | nvarchar(50) | YES |  |
| `OPEX_Change` | nvarchar(50) | YES |  |
| `Provision_Change` | nvarchar(50) | YES |  |
| `Non_Recurring_Change` | nvarchar(50) | YES |  |
| `NII_Change` | nvarchar(50) | YES |  |
| `Fee_Change` | nvarchar(50) | YES |  |
| `Loan_Growth_%` | nvarchar(50) | YES |  |
| `Small_PBT_Flag` | bit | YES |  |
| `PBT_Growth_%_T12M` | nvarchar(50) | YES |  |
| `Top_Line_Impact_T12M` | nvarchar(50) | YES |  |
| `Cost_Cutting_Impact_T12M` | nvarchar(50) | YES |  |
| `Non_Recurring_Impact_T12M` | nvarchar(50) | YES |  |
| `NII_Impact_T12M` | nvarchar(50) | YES |  |
| `Fee_Impact_T12M` | nvarchar(50) | YES |  |
| `OPEX_Impact_T12M` | nvarchar(50) | YES |  |
| `Provision_Impact_T12M` | nvarchar(50) | YES |  |
| `Loan_Impact_T12M` | nvarchar(50) | YES |  |
| `NIM_Impact_T12M` | nvarchar(50) | YES |  |
| `Total_Impact_T12M` | nvarchar(50) | YES |  |
| `Top_Line_Impact` | nvarchar(50) | YES |  |
| `Cost_Cutting_Impact` | nvarchar(50) | YES |  |
| `Non_Recurring_Impact` | nvarchar(50) | YES |  |
| `Total_Impact` | nvarchar(50) | YES |  |
| `NII_Impact` | nvarchar(50) | YES |  |
| `Fee_Impact` | nvarchar(50) | YES |  |
| `OPEX_Impact` | nvarchar(50) | YES |  |
| `Provision_Impact` | nvarchar(50) | YES |  |
| `Loan_Impact` | nvarchar(50) | YES |  |
| `NIM_Impact` | nvarchar(50) | YES |  |
| `PBT_Growth_%` | nvarchar(50) | YES |  |
| `Core TOI_QoQ` | nvarchar(50) | YES |  |
| `PBT_QoQ` | nvarchar(50) | YES |  |
| `OPEX_QoQ` | nvarchar(50) | YES |  |
| `Provision expense_QoQ` | nvarchar(50) | YES |  |
| `Non-recurring income_QoQ` | nvarchar(50) | YES |  |
| `Net Interest Income_QoQ` | nvarchar(50) | YES |  |
| `Fees Income_QoQ` | nvarchar(50) | YES |  |
| `Loan_QoQ` | nvarchar(50) | YES |  |
| `NIM_QoQ` | nvarchar(50) | YES |  |
| `PBT_Growth_%_QoQ` | nvarchar(50) | YES |  |
| `Top_Line_Impact_QoQ` | nvarchar(50) | YES |  |
| `Cost_Cutting_Impact_QoQ` | nvarchar(50) | YES |  |
| `Non_Recurring_Impact_QoQ` | nvarchar(50) | YES |  |
| `NII_Impact_QoQ` | nvarchar(50) | YES |  |
| `Fee_Impact_QoQ` | nvarchar(50) | YES |  |
| `OPEX_Impact_QoQ` | nvarchar(50) | YES |  |
| `Provision_Impact_QoQ` | nvarchar(50) | YES |  |
| `Loan_Impact_QoQ` | nvarchar(50) | YES |  |
| `NIM_Impact_QoQ` | nvarchar(50) | YES |  |
| `Total_Impact_QoQ` | nvarchar(50) | YES |  |
| `Core TOI_YoY` | nvarchar(50) | YES |  |
| `PBT_YoY` | nvarchar(50) | YES |  |
| `OPEX_YoY` | nvarchar(50) | YES |  |
| `Provision expense_YoY` | nvarchar(50) | YES |  |
| `Non-recurring income_YoY` | nvarchar(50) | YES |  |
| `Net Interest Income_YoY` | nvarchar(50) | YES |  |
| `Fees Income_YoY` | nvarchar(50) | YES |  |
| `Loan_YoY` | nvarchar(50) | YES |  |
| `NIM_YoY` | nvarchar(50) | YES |  |
| `PBT_Growth_%_YoY` | nvarchar(50) | YES |  |
| `Top_Line_Impact_YoY` | nvarchar(50) | YES |  |
| `Cost_Cutting_Impact_YoY` | nvarchar(50) | YES |  |
| `Non_Recurring_Impact_YoY` | nvarchar(50) | YES |  |
| `NII_Impact_YoY` | nvarchar(50) | YES |  |
| `Fee_Impact_YoY` | nvarchar(50) | YES |  |
| `OPEX_Impact_YoY` | nvarchar(50) | YES |  |
| `Provision_Impact_YoY` | nvarchar(50) | YES |  |
| `Loan_Impact_YoY` | nvarchar(50) | YES |  |
| `NIM_Impact_YoY` | nvarchar(50) | YES |  |
| `Total_Impact_YoY` | nvarchar(50) | YES |  |
| `Impacts_Capped` | nvarchar(50) | YES |  |
| `PERIOD_TYPE` | nvarchar(50) | YES |  |
| `Core TOI_Prior_Year` | nvarchar(50) | YES |  |
| `PBT_Prior_Year` | nvarchar(50) | YES |  |
| `OPEX_Prior_Year` | nvarchar(50) | YES |  |
| `Provision expense_Prior_Year` | nvarchar(50) | YES |  |
| `Non-recurring income_Prior_Year` | nvarchar(50) | YES |  |
| `Net Interest Income_Prior_Year` | nvarchar(50) | YES |  |
| `Fees Income_Prior_Year` | nvarchar(50) | YES |  |
| `Loan_Prior_Year` | nvarchar(50) | YES |  |
| `NIM_Prior_Year` | nvarchar(50) | YES |  |
| `Scores_Capped` | nvarchar(50) | YES |  |
| `_content_hash` | nvarchar(50) | YES |  |

### `dbo.BankingMetrics`

Type: BASE TABLE  
Primary key: —

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `TICKER` | nvarchar(50) | YES |  |
| `YEARREPORT` | bigint | YES |  |
| `LENGTHREPORT` | bigint | YES |  |
| `ACTUAL` | bit | YES |  |
| `DATE` | datetime2 | YES |  |
| `DATE_STRING` | nvarchar(50) | YES |  |
| `BANK_TYPE` | nvarchar(50) | YES |  |
| `PERIOD_TYPE` | nvarchar(50) | YES |  |
| `TOI` | nvarchar(50) | YES |  |
| `PBT` | nvarchar(50) | YES |  |
| `Net Interest Income` | nvarchar(50) | YES |  |
| `OPEX` | nvarchar(50) | YES |  |
| `PPOP` | nvarchar(50) | YES |  |
| `Provision expense` | nvarchar(50) | YES |  |
| `NPATMI` | nvarchar(50) | YES |  |
| `Fees Income` | nvarchar(50) | YES |  |
| `Net Profit` | nvarchar(50) | YES |  |
| `Loan` | nvarchar(50) | YES |  |
| `Deposit` | nvarchar(50) | YES |  |
| `Total Assets` | nvarchar(50) | YES |  |
| `Total Equity` | nvarchar(50) | YES |  |
| `Provision on Balance Sheet` | nvarchar(50) | YES |  |
| `Write-off` | nvarchar(50) | YES |  |
| `LDR` | nvarchar(50) | YES |  |
| `CASA` | nvarchar(50) | YES |  |
| `NPL` | nvarchar(50) | YES |  |
| `ABS NPL` | nvarchar(50) | YES |  |
| `GROUP 2` | nvarchar(50) | YES |  |
| `CIR` | nvarchar(50) | YES |  |
| `NPL Coverage ratio` | nvarchar(50) | YES |  |
| `Total Credit Balance` | nvarchar(50) | YES |  |
| `Provision/ Total Loan` | nvarchar(50) | YES |  |
| `Leverage Multiple` | nvarchar(50) | YES |  |
| `Interest Earnings Asset` | nvarchar(50) | YES |  |
| `Interest Bearing Liabilities` | nvarchar(50) | YES |  |
| `NIM` | nvarchar(50) | YES |  |
| `Customer loans` | nvarchar(50) | YES |  |
| `Loan yield` | nvarchar(50) | YES |  |
| `ROA` | nvarchar(50) | YES |  |
| `ROE` | nvarchar(50) | YES |  |
| `Deposit balance` | nvarchar(50) | YES |  |
| `Deposit yield` | nvarchar(50) | YES |  |
| `Fees/ Total asset` | nvarchar(50) | YES |  |
| `Individual %` | nvarchar(50) | YES |  |
| `NPL Formation Amount` | nvarchar(50) | YES |  |
| `New NPL` | nvarchar(50) | YES |  |
| `Group 2 Formation` | nvarchar(50) | YES |  |
| `New G2` | nvarchar(50) | YES |  |
| `Overdue_loan` | nvarchar(50) | YES |  |
| `_content_hash` | nvarchar(50) | YES |  |

### `dbo.BankingMetrics_old`

Type: BASE TABLE  
Primary key: —

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `TICKER` | nvarchar(50) | YES |  |
| `YEARREPORT` | bigint | YES |  |
| `LENGTHREPORT` | bigint | YES |  |
| `ACTUAL` | bit | YES |  |
| `DATE` | datetime2 | YES |  |
| `DATE_STRING` | nvarchar(50) | YES |  |
| `BANK_TYPE` | nvarchar(50) | YES |  |
| `PERIOD_TYPE` | nvarchar(50) | YES |  |
| `TOI` | nvarchar(50) | YES |  |
| `PBT` | nvarchar(50) | YES |  |
| `Net Interest Income` | nvarchar(50) | YES |  |
| `OPEX` | nvarchar(50) | YES |  |
| `PPOP` | nvarchar(50) | YES |  |
| `Provision expense` | nvarchar(50) | YES |  |
| `NPATMI` | nvarchar(50) | YES |  |
| `Fees Income` | nvarchar(50) | YES |  |
| `Net Profit` | nvarchar(50) | YES |  |
| `Loan` | nvarchar(50) | YES |  |
| `Deposit` | nvarchar(50) | YES |  |
| `Total Assets` | nvarchar(50) | YES |  |
| `Total Equity` | nvarchar(50) | YES |  |
| `Provision on Balance Sheet` | nvarchar(50) | YES |  |
| `Write-off` | nvarchar(50) | YES |  |
| `LDR` | nvarchar(50) | YES |  |
| `CASA` | nvarchar(50) | YES |  |
| `NPL` | nvarchar(50) | YES |  |
| `ABS NPL` | nvarchar(50) | YES |  |
| `GROUP 2` | nvarchar(50) | YES |  |
| `CIR` | nvarchar(50) | YES |  |
| `NPL Coverage ratio` | nvarchar(50) | YES |  |
| `Total Credit Balance` | nvarchar(50) | YES |  |
| `Provision/ Total Loan` | nvarchar(50) | YES |  |
| `Leverage Multiple` | nvarchar(50) | YES |  |
| `Interest Earnings Asset` | nvarchar(50) | YES |  |
| `Interest Bearing Liabilities` | nvarchar(50) | YES |  |
| `NIM` | nvarchar(50) | YES |  |
| `Customer loans` | nvarchar(50) | YES |  |
| `Loan yield` | nvarchar(50) | YES |  |
| `ROA` | nvarchar(50) | YES |  |
| `ROE` | nvarchar(50) | YES |  |
| `Deposit balance` | nvarchar(50) | YES |  |
| `Deposit yield` | nvarchar(50) | YES |  |
| `Fees/ Total asset` | nvarchar(50) | YES |  |
| `Individual %` | nvarchar(50) | YES |  |
| `NPL Formation Amount` | nvarchar(50) | YES |  |
| `New NPL` | nvarchar(50) | YES |  |
| `Group 2 Formation` | nvarchar(50) | YES |  |
| `New G2` | nvarchar(50) | YES |  |
| `Overdue_loan` | nvarchar(50) | YES |  |

### `dbo.Brokerage_Comments`

Type: BASE TABLE  
Primary key: —

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `TICKER` | nvarchar(50) | YES |  |
| `QUARTER` | nvarchar(50) | YES |  |
| `COMMENTARY` | nvarchar(max) | YES |  |
| `GENERATED_AT` | datetime2 | YES |  |

### `dbo.Brokerage_Propbook`

Type: BASE TABLE  
Primary key: Broker, Quarter, Ticker, Keycode

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `Broker` | varchar(20) | NO |  |
| `Quarter` | varchar(10) | NO |  |
| `Ticker` | varchar(50) | NO |  |
| `Keycode` | varchar(20) | NO |  |
| `Value` | float | YES |  |

### `dbo.BrokerageMetrics`

Type: BASE TABLE  
Primary key: —

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `TICKER` | nvarchar(50) | YES |  |
| `ORGANCODE` | nvarchar(50) | YES |  |
| `YEARREPORT` | bigint | YES |  |
| `LENGTHREPORT` | bigint | YES |  |
| `ACTUAL` | bit | YES |  |
| `QUARTER_LABEL` | nvarchar(50) | YES |  |
| `STARTDATE` | nvarchar(50) | YES |  |
| `ENDDATE` | nvarchar(50) | YES |  |
| `KEYCODE` | nvarchar(255) | YES |  |
| `KEYCODE_NAME` | nvarchar(255) | YES |  |
| `VALUE` | nvarchar(50) | YES |  |
| `_content_hash` | nvarchar(50) | YES |  |

### `dbo.Chemicals`

Type: BASE TABLE  
Primary key: Ticker, Date

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `Ticker` | varchar(50) | NO |  |
| `Date` | date | NO |  |
| `Price` | decimal(18,6) | YES |  |

### `dbo.Container_volume`

Type: BASE TABLE  
Primary key: —

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `Date` | datetime2 | YES |  |
| `Region` | nvarchar(50) | YES |  |
| `Company` | nvarchar(50) | YES |  |
| `Port` | nvarchar(50) | YES |  |
| `Total throughput` | float | YES |  |

### `dbo.Energy`

Type: BASE TABLE  
Primary key: Ticker, Date

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `Ticker` | varchar(50) | NO |  |
| `Date` | date | NO |  |
| `Price` | decimal(18,6) | YES |  |

### `dbo.FA_Annual`

Type: BASE TABLE  
Primary key: —

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `KEYCODE` | nvarchar(50) | YES |  |
| `TICKER` | nvarchar(50) | YES |  |
| `DATE` | nvarchar(50) | YES |  |
| `VALUE` | nvarchar(50) | YES |  |
| `YEAR` | bigint | YES |  |
| `YoY` | nvarchar(50) | YES |  |

### `dbo.FA_Quarterly`

Type: BASE TABLE  
Primary key: —

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `KEYCODE` | nvarchar(50) | YES |  |
| `TICKER` | nvarchar(50) | YES |  |
| `DATE` | nvarchar(50) | YES |  |
| `VALUE` | nvarchar(50) | YES |  |
| `YEAR` | bigint | YES |  |
| `YoY` | nvarchar(50) | YES |  |
| `_content_hash` | nvarchar(50) | YES |  |

### `dbo.Fertilizer`

Type: BASE TABLE  
Primary key: Ticker, Date

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `Ticker` | varchar(100) | NO |  |
| `Date` | date | NO |  |
| `Price` | decimal(18,6) | YES |  |

### `dbo.Fishery`

Type: BASE TABLE  
Primary key: Date, Company, Market

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `Date` | date | NO |  |
| `Company` | varchar(20) | NO |  |
| `Market` | varchar(20) | NO |  |
| `Volume` | decimal(18,6) | YES |  |
| `Value` | decimal(18,6) | YES |  |
| `Selling_Price` | decimal(18,6) | YES |  |
| `Input_Price` | decimal(18,6) | YES |  |

### `dbo.Forecast`

Type: BASE TABLE  
Primary key: —

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `TICKER` | nvarchar(50) | YES |  |
| `KEYCODE` | nvarchar(50) | YES |  |
| `KEYCODENAME` | nvarchar(255) | YES |  |
| `ORGANCODE` | nvarchar(50) | YES |  |
| `DATE` | nvarchar(50) | YES |  |
| `VALUE` | float | YES |  |
| `RATING` | nvarchar(50) | YES |  |
| `FORECASTDATE` | nvarchar(50) | YES |  |
| `_content_hash` | nvarchar(50) | YES |  |

### `dbo.Forecast_Consensus`

Type: BASE TABLE  
Primary key: —

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `KEYCODE` | varchar(max) | YES |  |
| `KEYCODENAME` | varchar(max) | YES |  |
| `ORGANCODE` | varchar(max) | YES |  |
| `TICKER` | varchar(max) | YES |  |
| `DATE` | varchar(max) | YES |  |
| `VALUE` | float | YES |  |
| `RATING` | varchar(max) | YES |  |
| `FORECASTDATE` | varchar(max) | YES |  |

### `dbo.Import_History`

Type: BASE TABLE  
Primary key: upload_time, user_name, sector

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `upload_time` | datetime | NO |  |
| `sector` | varchar(100) | NO |  |
| `records_added` | int | YES |  |
| `records_updated` | int | YES |  |
| `user_name` | varchar(100) | NO |  |
| `file_size_mb` | decimal(10,2) | YES |  |
| `total_rows` | int | YES |  |

### `dbo.Livestock`

Type: BASE TABLE  
Primary key: Ticker, Date

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `Ticker` | varchar(100) | NO |  |
| `Date` | date | NO |  |
| `Price` | decimal(18,6) | YES |  |

### `dbo.Market_Data`

Type: BASE TABLE  
Primary key: TICKER, TRADE_DATE

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `TICKER` | varchar(10) | NO |  |
| `TRADE_DATE` | date | NO |  |
| `PE` | float | YES |  |
| `PB` | float | YES |  |
| `PS` | float | YES |  |
| `PX_OPEN` | float | YES |  |
| `PX_HIGH` | float | YES |  |
| `PX_LOW` | float | YES |  |
| `PX_LAST` | float | YES |  |
| `MKT_CAP` | float | YES |  |
| `EV_EBITDA` | float | YES |  |
| `UPDATE_TIMESTAMP` | datetime | YES |  |
| `VOLUME` | float | YES |  |
| `VALUE` | float | YES |  |

### `dbo.MarketCap`

Type: BASE TABLE  
Primary key: —

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `TICKER` | nvarchar(50) | YES |  |
| `CUR_MKT_CAP` | nvarchar(50) | YES |  |
| `TRADE_DATE` | datetime2 | YES |  |

### `dbo.MarketIndex`

Type: BASE TABLE  
Primary key: —

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `COMGROUPCODE` | nvarchar(50) | YES |  |
| `INDEXVALUE` | float | YES |  |
| `TRADINGDATE` | datetime2 | YES |  |
| `INDEXCHANGE` | float | YES |  |
| `PERCENTINDEXCHANGE` | float | YES |  |
| `REFERENCEINDEX` | float | YES |  |
| `OPENINDEX` | float | YES |  |
| `CLOSEINDEX` | float | YES |  |
| `HIGHESTINDEX` | float | YES |  |
| `LOWESTINDEX` | float | YES |  |
| `TOTALMATCHVOLUME` | float | YES |  |
| `TOTALMATCHVALUE` | float | YES |  |
| `TOTALDEALVOLUME` | float | YES |  |
| `TOTALDEALVALUE` | float | YES |  |
| `TOTALVOLUME` | float | YES |  |
| `TOTALVALUE` | float | YES |  |
| `TOTALSTOCKUPPRICE` | bigint | YES |  |
| `TOTALSTOCKDOWNPRICE` | bigint | YES |  |
| `TOTALSTOCKNOCHANGEPRICE` | bigint | YES |  |
| `TOTALUPVOLUME` | float | YES |  |
| `TOTALDOWNVOLUME` | float | YES |  |
| `TOTALNOCHANGEVOLUME` | float | YES |  |
| `FOREIGNBUYVALUEMATCHED` | float | YES |  |
| `FOREIGNBUYVOLUMEMATCHED` | float | YES |  |
| `FOREIGNSELLVALUEMATCHED` | float | YES |  |
| `FOREIGNSELLVOLUMEMATCHED` | float | YES |  |
| `FOREIGNBUYVALUETOTAL` | float | YES |  |
| `FOREIGNBUYVOLUMETOTAL` | float | YES |  |
| `FOREIGNSELLVALUETOTAL` | float | YES |  |
| `FOREIGNSELLVOLUMETOTAL` | float | YES |  |

### `dbo.Metals`

Type: BASE TABLE  
Primary key: Ticker, Date

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `Ticker` | varchar(50) | NO |  |
| `Date` | date | NO |  |
| `Price` | decimal(18,6) | YES |  |

### `dbo.Monthly_Income`

Type: BASE TABLE  
Primary key: —

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `Year` | int | YES |  |
| `Quarter` | int | YES |  |
| `Urban` | float | YES |  |
| `Rural` | float | YES |  |
| `Nationwide` | float | YES |  |

### `dbo.Sector_Map`

Type: BASE TABLE  
Primary key: —

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `ReportFormat` | nvarchar(50) | YES |  |
| `OrganCode` | nvarchar(50) | YES |  |
| `Ticker` | nvarchar(50) | YES |  |
| `ExportClassification` | nvarchar(50) | YES |  |
| `Sector` | nvarchar(50) | YES |  |
| `L1` | nvarchar(50) | YES |  |
| `L2` | nvarchar(50) | YES |  |
| `L3` | nvarchar(50) | YES |  |
| `Top80` | nvarchar(50) | YES |  |
| `McapClassification` | nvarchar(50) | YES |  |
| `VNI` | nvarchar(50) | YES |  |
| `MC($USm)` | nvarchar(50) | YES |  |
| `IndexWeight` | nvarchar(50) | YES |  |
| `Status` | nvarchar(50) | YES |  |

### `dbo.Shipping_Freight`

Type: BASE TABLE  
Primary key: Ticker, Date

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `Ticker` | varchar(50) | NO |  |
| `Date` | date | NO |  |
| `Price` | decimal(18,6) | YES |  |

### `dbo.Steel`

Type: BASE TABLE  
Primary key: Ticker, Date

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `Ticker` | varchar(50) | NO |  |
| `Date` | date | NO |  |
| `Price` | decimal(18,6) | YES |  |

### `dbo.Textile`

Type: BASE TABLE  
Primary key: Ticker, Date

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `Ticker` | varchar(100) | NO |  |
| `Date` | date | NO |  |
| `Price` | decimal(18,6) | YES |  |

### `dbo.Ticker_Reference`

Type: BASE TABLE  
Primary key: Ticker

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `Ticker` | varchar(100) | NO |  |
| `Name` | varchar(255) | YES |  |
| `Sector` | varchar(50) | YES |  |
| `Data_Source` | varchar(100) | YES |  |
| `Active` | bit | YES |  |

### `dbo.v_AI_Active_Cache`

Type: VIEW  
Primary key: —

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `Commodity` | varchar(50) | NO |  |
| `Query_Date` | date | NO |  |
| `Timeframe` | varchar(20) | NO |  |
| `Cache_Hit_Count` | int | YES |  |
| `Hours_Old` | int | YES |  |
| `Hours_Until_Expiry` | int | YES |  |

### `dbo.v_AI_Latest_Intelligence`

Type: VIEW  
Primary key: —

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `Commodity` | varchar(50) | NO |  |
| `Analysis_Date` | date | NO |  |
| `Trend` | varchar(20) | YES |  |
| `Key_Drivers` | nvarchar(max) | YES |  |
| `Current_Price` | decimal(18,6) | YES |  |
| `Price_Unit` | varchar(20) | YES |  |
| `Price_Change_Pct` | decimal(18,6) | YES |  |
| `Confidence_Score` | decimal(18,6) | YES |  |
| `Created_At` | datetime2 | YES |  |
| `Days_Old` | int | YES |  |

### `dbo.Valuation`

Type: BASE TABLE  
Primary key: —

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `TICKER` | nvarchar(50) | YES |  |
| `TRADE_DATE` | datetime2 | YES |  |
| `P/E` | nvarchar(50) | YES |  |
| `P/B` | nvarchar(50) | YES |  |
| `P/S` | nvarchar(50) | YES |  |
| `EV/EBITDA` | nvarchar(50) | YES |  |

### `sys.database_firewall_rules`

Type: VIEW  
Primary key: —

| Column | Data Type | Nullable | Default |
| --- | --- | --- | --- |
| `id` | int | NO |  |
| `name` | nvarchar(128) | NO |  |
| `start_ip_address` | varchar(45) | NO |  |
| `end_ip_address` | varchar(45) | NO |  |
| `create_date` | datetime | NO |  |
| `modify_date` | datetime | NO |  |
