"""
Step 7: Analytics Dashboard
Built with Plotly Dash – no Grafana server required.
Panels:
  1. Real-time meter readings (last hour)
  2. Daily consumption: today vs yesterday
  3. Weekly trend
  4. Monthly energy by region
  5. Performance metrics: raw vs aggregated query times
  6. Compression before/after
  7. Chunk strategy comparison
Run: python dashboard.py
"""

import time
import logging
from datetime import datetime, timedelta, timezone

import dash
from dash import dcc, html, Input, Output, dash_table
import plotly.graph_objects as go
import plotly.express as px
import psycopg2
import psycopg2.extras
import pandas as pd

# ── Configuration ───────────────────────────────────────────────────────────────
DB_CONFIG = dict(
    host="localhost", port=5432,
    dbname="energy_db", user="postgres", password="postgres"
)
REFRESH_INTERVAL_MS = 30_000   # 30 s live refresh
# ────────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


# ── DB helpers ──────────────────────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def query_df(sql: str, params=None) -> pd.DataFrame:
    try:
        with get_conn() as conn:
            return pd.read_sql_query(sql, conn, params=params)
    except Exception as exc:
        log.error("Query failed: %s\n%s", exc, sql[:200])
        return pd.DataFrame()


def timed_query(sql: str, params=None):
    """Return (DataFrame, elapsed_ms)."""
    t0 = time.perf_counter()
    df = query_df(sql, params)
    elapsed = (time.perf_counter() - t0) * 1000
    return df, elapsed


# ── Query library ───────────────────────────────────────────────────────────────

SQL_REALTIME = """
    SELECT time_bucket('5 minutes', timestamp) AS bucket,
           AVG(power)    AS avg_power,
           MAX(power)    AS max_power,
           MIN(power)    AS min_power
    FROM   energy_readings
    WHERE  timestamp >= NOW() - INTERVAL '1 hour'
    GROUP  BY bucket
    ORDER  BY bucket;
"""

SQL_TODAY = """
    SELECT time_bucket('1 hour', timestamp) AS hour,
           AVG(power) AS avg_power
    FROM   energy_readings
    WHERE  timestamp >= DATE_TRUNC('day', NOW())
    GROUP  BY hour ORDER BY hour;
"""

SQL_YESTERDAY = """
    SELECT time_bucket('1 hour', timestamp) AS hour,
           AVG(power) AS avg_power
    FROM   energy_readings
    WHERE  timestamp >= DATE_TRUNC('day', NOW()) - INTERVAL '1 day'
      AND  timestamp <  DATE_TRUNC('day', NOW())
    GROUP  BY hour ORDER BY hour;
"""

SQL_WEEKLY = """
    SELECT time_bucket('1 hour', timestamp) AS bucket,
           AVG(power) AS avg_power
    FROM   energy_readings
    WHERE  timestamp >= NOW() - INTERVAL '7 days'
    GROUP  BY bucket ORDER BY bucket;
"""

SQL_MONTHLY_REGION = """
    SELECT SUBSTRING(meter_id, 1, 1)          AS region,
           DATE_TRUNC('day', timestamp)        AS day,
           SUM(energy)                         AS total_energy
    FROM   energy_readings
    WHERE  timestamp >= NOW() - INTERVAL '30 days'
    GROUP  BY region, day
    ORDER  BY day, region;
"""

SQL_RAW_15MIN = """
    SELECT time_bucket('15 minutes', timestamp) AS bucket,
           AVG(power) AS avg_power
    FROM   energy_readings
    WHERE  timestamp >= NOW() - INTERVAL '1 day'
    GROUP  BY bucket ORDER BY bucket;
"""

SQL_CAG_15MIN = """
    SELECT bucket, AVG(avg_power) AS avg_power
    FROM   energy_readings_15min
    WHERE  bucket >= NOW() - INTERVAL '1 day'
    GROUP  BY bucket ORDER BY bucket;
"""

SQL_CHUNK_INFO = """
    SELECT chunk_name,
           pg_size_pretty(chunk_size)  AS chunk_size,
           range_start::text           AS range_start,
           range_end::text             AS range_end
    FROM   chunk_information
    WHERE  hypertable_name = 'energy_readings'
    ORDER  BY range_start DESC
    LIMIT  20;
"""

SQL_COMPRESSION = """
    SELECT hypertable_name,
           pg_size_pretty(hypertable_size(
               format('%I', hypertable_name)::regclass)) AS total_size
    FROM   timescaledb_information.hypertables
    WHERE  hypertable_name IN
           ('energy_readings','energy_readings_3h','energy_readings_week');
"""


# ── App layout ──────────────────────────────────────────────────────────────────

app = dash.Dash(__name__, title="Smart Energy Grid Dashboard")

CARD = {
    "backgroundColor": "#1e1e2e",
    "borderRadius": "10px",
    "padding": "16px",
    "marginBottom": "16px",
    "boxShadow": "0 4px 12px rgba(0,0,0,0.4)",
}

app.layout = html.Div(
    style={"backgroundColor": "#11111b", "minHeight": "100vh",
           "fontFamily": "Inter, sans-serif", "color": "#cdd6f4", "padding": "24px"},
    children=[
        html.H1("⚡ Smart Energy Grid Monitoring",
                style={"textAlign": "center", "color": "#89b4fa",
                       "marginBottom": "8px"}),
        html.P(id="last-update", style={"textAlign": "center", "color": "#6c7086"}),

        dcc.Interval(id="interval", interval=REFRESH_INTERVAL_MS, n_intervals=0),

        # ── Row 1: real-time + today vs yesterday ─────────────────────────────
        html.Div(style={"display": "grid",
                        "gridTemplateColumns": "1fr 1fr", "gap": "16px"}, children=[
            html.Div(style=CARD, children=[
                html.H3("Real-Time Readings (Last Hour)",
                        style={"color": "#a6e3a1"}),
                dcc.Graph(id="realtime-chart", style={"height": "300px"}),
            ]),
            html.Div(style=CARD, children=[
                html.H3("Today vs Yesterday (Hourly Avg)",
                        style={"color": "#fab387"}),
                dcc.Graph(id="today-yesterday-chart", style={"height": "300px"}),
            ]),
        ]),

        # ── Row 2: weekly trend + monthly by region ───────────────────────────
        html.Div(style={"display": "grid",
                        "gridTemplateColumns": "1fr 1fr", "gap": "16px"}, children=[
            html.Div(style=CARD, children=[
                html.H3("Weekly Power Trend", style={"color": "#89dceb"}),
                dcc.Graph(id="weekly-chart", style={"height": "300px"}),
            ]),
            html.Div(style=CARD, children=[
                html.H3("Monthly Energy by Region (kWh/day)",
                        style={"color": "#cba6f7"}),
                dcc.Graph(id="region-chart", style={"height": "300px"}),
            ]),
        ]),

        # ── Row 3: raw vs CAG performance ─────────────────────────────────────
        html.Div(style=CARD, children=[
            html.H3("⚡ Query Performance: Raw Data vs Continuous Aggregates",
                    style={"color": "#f38ba8"}),
            html.Div(style={"display": "grid",
                            "gridTemplateColumns": "1fr 1fr", "gap": "16px"}, children=[
                dcc.Graph(id="perf-chart", style={"height": "300px"}),
                html.Div(id="perf-table"),
            ]),
        ]),

        # ── Row 4: compression + chunk info ───────────────────────────────────
        html.Div(style={"display": "grid",
                        "gridTemplateColumns": "1fr 1fr", "gap": "16px"}, children=[
            html.Div(style=CARD, children=[
                html.H3("Disk Usage by Hypertable Configuration",
                        style={"color": "#f9e2af"}),
                dcc.Graph(id="compression-chart", style={"height": "280px"}),
            ]),
            html.Div(style=CARD, children=[
                html.H3("Recent Chunk Information (1-day hypertable)",
                        style={"color": "#89b4fa"}),
                html.Div(id="chunk-table"),
            ]),
        ]),
    ],
)


# ── Callbacks ───────────────────────────────────────────────────────────────────

@app.callback(
    Output("last-update", "children"),
    Output("realtime-chart", "figure"),
    Output("today-yesterday-chart", "figure"),
    Output("weekly-chart", "figure"),
    Output("region-chart", "figure"),
    Output("perf-chart", "figure"),
    Output("perf-table", "children"),
    Output("compression-chart", "figure"),
    Output("chunk-table", "children"),
    Input("interval", "n_intervals"),
)
def refresh(_n):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    DARK = "#1e1e2e"
    GRID = "#313244"
    TEXT = "#cdd6f4"

    def dark_layout(**kw):
        return go.Layout(
            paper_bgcolor=DARK, plot_bgcolor=DARK,
            font=dict(color=TEXT, size=11),
            xaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
            yaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
            margin=dict(l=50, r=20, t=30, b=40),
            **kw,
        )

    # ── 1. Real-time ──────────────────────────────────────────────────────────
    df_rt = query_df(SQL_REALTIME)
    if df_rt.empty:
        fig_rt = go.Figure(layout=dark_layout(title="No data yet"))
    else:
        fig_rt = go.Figure(layout=dark_layout())
        fig_rt.add_trace(go.Scatter(
            x=df_rt["bucket"], y=df_rt["avg_power"],
            mode="lines", name="Avg Power (W)",
            line=dict(color="#a6e3a1", width=2)))
        fig_rt.add_trace(go.Scatter(
            x=df_rt["bucket"], y=df_rt["max_power"],
            mode="lines", name="Max Power",
            line=dict(color="#f38ba8", width=1, dash="dot")))

    # ── 2. Today vs Yesterday ─────────────────────────────────────────────────
    df_today = query_df(SQL_TODAY)
    df_yest  = query_df(SQL_YESTERDAY)
    fig_ty   = go.Figure(layout=dark_layout())
    if not df_today.empty:
        fig_ty.add_trace(go.Bar(
            x=df_today["hour"].apply(lambda h: h.strftime("%H:00")),
            y=df_today["avg_power"], name="Today",
            marker_color="#fab387"))
    if not df_yest.empty:
        fig_ty.add_trace(go.Bar(
            x=df_yest["hour"].apply(lambda h: h.strftime("%H:00")),
            y=df_yest["avg_power"], name="Yesterday",
            marker_color="#89b4fa", opacity=0.6))
    fig_ty.update_layout(barmode="group")

    # ── 3. Weekly trend ───────────────────────────────────────────────────────
    df_wk = query_df(SQL_WEEKLY)
    if df_wk.empty:
        fig_wk = go.Figure(layout=dark_layout(title="No data"))
    else:
        fig_wk = px.line(df_wk, x="bucket", y="avg_power",
                         color_discrete_sequence=["#89dceb"])
        fig_wk.update_layout(dark_layout())

    # ── 4. Region chart ───────────────────────────────────────────────────────
    df_reg = query_df(SQL_MONTHLY_REGION)
    if df_reg.empty:
        fig_reg = go.Figure(layout=dark_layout(title="No data"))
    else:
        fig_reg = px.line(df_reg, x="day", y="total_energy", color="region",
                          color_discrete_sequence=px.colors.qualitative.Pastel)
        fig_reg.update_layout(dark_layout())

    # ── 5. Performance comparison ─────────────────────────────────────────────
    df_raw, t_raw = timed_query(SQL_RAW_15MIN)
    df_cag, t_cag = timed_query(SQL_CAG_15MIN)

    perf_data = {
        "Query":        ["15-min bucket (raw)", "15-min bucket (CAG)"],
        "Time (ms)":    [round(t_raw, 1), round(t_cag, 1)],
        "Rows returned":[len(df_raw), len(df_cag)],
    }
    fig_perf = go.Figure(
        go.Bar(
            x=perf_data["Query"], y=perf_data["Time (ms)"],
            marker_color=["#f38ba8", "#a6e3a1"],
            text=[f"{t:.1f} ms" for t in perf_data["Time (ms)"]],
            textposition="outside",
        ),
        layout=dark_layout(title="Query Execution Time (ms)"),
    )

    speedup = (t_raw / t_cag) if t_cag > 0 else 0
    perf_table = dash_table.DataTable(
        data=[{"Query": q, "Time (ms)": t, "Rows": r}
              for q, t, r in zip(
                  perf_data["Query"],
                  perf_data["Time (ms)"],
                  perf_data["Rows returned"])],
        columns=[{"name": c, "id": c}
                 for c in ["Query", "Time (ms)", "Rows"]],
        style_table={"overflowX": "auto"},
        style_header={"backgroundColor": "#313244", "color": "#cdd6f4",
                       "fontWeight": "bold"},
        style_cell={"backgroundColor": "#1e1e2e", "color": "#cdd6f4",
                    "border": "1px solid #45475a"},
        style_data_conditional=[
            {"if": {"row_index": 1},
             "color": "#a6e3a1", "fontWeight": "bold"}],
    )

    # Speedup annotation
    perf_table_wrap = html.Div([
        perf_table,
        html.P(f"⚡ CAG is {speedup:.1f}× faster than raw data query",
               style={"color": "#a6e3a1", "marginTop": "12px",
                      "fontWeight": "bold"}),
    ])

    # ── 6. Compression / disk usage ───────────────────────────────────────────
    df_comp = query_df(SQL_COMPRESSION)
    if df_comp.empty:
        fig_comp = go.Figure(layout=dark_layout(title="No compression data"))
    else:
        fig_comp = px.bar(df_comp, x="hypertable_name", y="total_size",
                          color="hypertable_name",
                          color_discrete_sequence=["#cba6f7","#89b4fa","#f9e2af"])
        fig_comp.update_layout(dark_layout(showlegend=False))

    # ── 7. Chunk info table ───────────────────────────────────────────────────
    df_chunk = query_df(SQL_CHUNK_INFO)
    if df_chunk.empty:
        chunk_table = html.P("No chunk data available.",
                             style={"color": "#6c7086"})
    else:
        chunk_table = dash_table.DataTable(
            data=df_chunk.to_dict("records"),
            columns=[{"name": c, "id": c} for c in df_chunk.columns],
            style_table={"overflowX": "auto", "maxHeight": "260px",
                         "overflowY": "auto"},
            style_header={"backgroundColor": "#313244", "color": "#cdd6f4",
                           "fontWeight": "bold"},
            style_cell={"backgroundColor": "#1e1e2e", "color": "#cdd6f4",
                        "border": "1px solid #45475a",
                        "fontSize": "12px", "padding": "6px"},
        )

    return (
        f"Last updated: {now}",
        fig_rt, fig_ty, fig_wk, fig_reg,
        fig_perf, perf_table_wrap,
        fig_comp, chunk_table,
    )


# ── Run ─────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8050)
