## Workflow Overview

### 1. Prep References First
- Decide whether to run inline Python or create a script: default to inline python - <<'PY' for quick, one-off analyses; only create standalone files when the workflow will be reused. (Keeps repo clean and matches the scripts-guidance doc.)
- Open dclab_schema.md (Access Notes + relevant tables) and skim MCP_SQL_QUERY_BEST_PRACTICES.md before every job. That keeps SQL rules (no CTEs, TRY_CAST/NULLIF, join limits) fresh.
- Confirm any scope nuances there (e.g., data only available back to 2018) so expectations are set up front.

### 2. Connect & Query
- Keep the repo-root .env populated with SQL_SERVER, SQL_DATABASE, SQL_USERNAME, SQL_PASSWORD.
- Always use the Anaconda interpreter so dependencies (e.g., python-dotenv) are available without reinstalling: invoke /opt/anaconda3/bin/python or conda run -n base python for every DB/MCP script, and keep MPLCONFIGDIR=/tmp/matplotlib.
- Launch /opt/anaconda3/bin/python (or the wrapper if provided) from /Users/ducle/Coding-Chat, set MPLCONFIGDIR=/tmp/matplotlib, and load credentials explicitly:  
  
python
  from pathlib import Path
  from dotenv import load_dotenv
  load_dotenv(Path('/Users/ducle/Coding-Chat/.env'))

- Point the connection string at the bundled driver directly: DRIVER=/Users/ducle/Coding-Chat/libmsodbcsql.18.dylib. Still export ODBCINSTINI=/Users/ducle/Coding-Chat/odbcinst.ini (and optionally ODBCINI) so unixODBC stays aligned, but skip the {ODBC Driver 18 for SQL Server} alias entirely—using the absolute path avoids the intermittent lookup failures.
- Follow the test.py pattern: build the connection string, pyodbc.connect, and pd.read_sql. Always include TRY_CAST(... AS FLOAT) and guard divisions with NULLIF(...,0).
- Keep everything in-memory: query → DataFrame → analysis. Avoid MCP “export to CSV” flows unless a final deliverable needs to be saved.
- Use vectorized pandas operations (see q4_2025_qoq_analysis.py or calculate_ma200_direct.py if you need a template) and assume data arrives in the expected format; only add error handling when absolutely required.
- Persist interim tables or exports under analysis/ so artifacts are easy to find.

### 3. Communicate Results
- Summaries should cite which schema sections/tables were used, mention the query approach, and reference any saved files with line numbers.
- Keep outputs concise, highlight drivers/limitations, and note follow-up steps (e.g., need older data, further joins).

This is my agent.md file, can you read throughout first