"""
Performance Benchmarking Script
Runs all 4 baseline queries on each hypertable configuration and prints
a formatted comparison table for inclusion in the technical report.

Usage:
    python benchmark.py
"""

import time
import psycopg2
import psycopg2.extras

DB_CONFIG = dict(
    host="localhost", port=5432,
    dbname="energy_db", user="postgres", password="postgres"
)

HYPERTABLES = ["energy_readings_3h", "energy_readings", "energy_readings_week"]
LABELS      = ["3-hour chunks", "1-day chunks", "1-week chunks"]

QUERIES = {
    "Q1: Hourly avg today": """
        SELECT time_bucket('1 hour', timestamp) AS hour, AVG(power)
        FROM   {table}
        WHERE  timestamp >= DATE_TRUNC('day', NOW())
        GROUP  BY hour ORDER BY hour;
    """,
    "Q2: Peak 15-min (7d)": """
        SELECT time_bucket('15 minutes', timestamp) AS period, AVG(power)
        FROM   {table}
        WHERE  timestamp >= NOW() - INTERVAL '7 days'
        GROUP  BY period ORDER BY 2 DESC LIMIT 10;
    """,
    "Q3: Monthly per meter": """
        SELECT meter_id, DATE_TRUNC('month', timestamp) AS month, SUM(energy)
        FROM   {table}
        GROUP  BY meter_id, month ORDER BY month, 3 DESC;
    """,
    "Q4: Full scan": """
        SELECT COUNT(*), AVG(power), MAX(power), MIN(power)
        FROM   {table};
    """,
}

COMPRESSION_QUERIES = {
    "Q2 (post-compress)": """
        SELECT time_bucket('15 minutes', timestamp) AS period, AVG(power)
        FROM   {table}
        WHERE  timestamp >= NOW() - INTERVAL '7 days'
        GROUP  BY period ORDER BY 2 DESC LIMIT 10;
    """,
    "Q3 (post-compress)": """
        SELECT meter_id, DATE_TRUNC('month', timestamp) AS month, SUM(energy)
        FROM   {table}
        GROUP  BY meter_id, month ORDER BY month, 3 DESC;
    """,
}

CAG_QUERIES = {
    "Raw 15-min (1d window)": """
        SELECT time_bucket('15 minutes', timestamp) AS bucket, AVG(power)
        FROM   energy_readings
        WHERE  timestamp >= NOW() - INTERVAL '1 day'
        GROUP  BY bucket ORDER BY bucket;
    """,
    "CAG 15-min (1d window)": """
        SELECT bucket, AVG(avg_power)
        FROM   energy_readings_15min
        WHERE  bucket >= NOW() - INTERVAL '1 day'
        GROUP  BY bucket ORDER BY bucket;
    """,
    "Raw hourly (7d window)": """
        SELECT time_bucket('1 hour', timestamp) AS bucket, AVG(power)
        FROM   energy_readings
        WHERE  timestamp >= NOW() - INTERVAL '7 days'
        GROUP  BY bucket ORDER BY bucket;
    """,
    "CAG hourly (7d window)": """
        SELECT bucket, AVG(avg_power)
        FROM   energy_readings_1h
        WHERE  bucket >= NOW() - INTERVAL '7 days'
        GROUP  BY bucket ORDER BY bucket;
    """,
}


def run_query(cur, sql: str, repeats: int = 3) -> float:
    """Return median execution time in milliseconds over `repeats` runs."""
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        cur.execute(sql)
        cur.fetchall()
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    return times[len(times) // 2]   # median


def col_width(rows, header):
    return max(len(header), max((len(str(r)) for r in rows), default=0)) + 2


def print_table(title: str, headers: list, rows: list):
    widths = [col_width([r[i] for r in rows], h) for i, h in enumerate(headers)]
    sep  = "+" + "+".join("-" * w for w in widths) + "+"
    fmt  = "|" + "|".join(f" {{:<{w-1}}}" for w in widths) + "|"
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    print(sep)
    print(fmt.format(*headers))
    print(sep)
    for row in rows:
        print(fmt.format(*row))
    print(sep)


def get_disk_sizes(cur):
    cur.execute("""
        SELECT hypertable_name,
               pg_size_pretty(hypertable_size(
                   format('%I', hypertable_name)::regclass)) AS size
        FROM   timescaledb_information.hypertables
        WHERE  hypertable_name IN
               ('energy_readings','energy_readings_3h','energy_readings_week');
    """)
    return {row[0]: row[1] for row in cur.fetchall()}


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    cur  = conn.cursor()

    print("\n" + "="*60)
    print("  SMART ENERGY GRID – PERFORMANCE BENCHMARK REPORT")
    print("="*60)

    # ── Section 1: Chunk interval comparison ──────────────────────────────────
    results = {}   # results[query_name][table_label] = ms
    for qname, qtpl in QUERIES.items():
        results[qname] = {}
        for table, label in zip(HYPERTABLES, LABELS):
            sql = qtpl.format(table=table)
            try:
                ms = run_query(cur, sql)
                results[qname][label] = f"{ms:.1f} ms"
            except Exception as exc:
                results[qname][label] = f"ERR: {exc}"

    headers = ["Query"] + LABELS
    rows    = [[qname] + [results[qname].get(lbl, "—") for lbl in LABELS]
               for qname in QUERIES]
    print_table("STEP 4: Chunk Interval Comparison (median of 3 runs)", headers, rows)

    # ── Section 2: Disk usage / compression ───────────────────────────────────
    try:
        sizes = get_disk_sizes(cur)
        size_rows = [(t, sizes.get(t, "—")) for t in
                     ["energy_readings_3h", "energy_readings", "energy_readings_week"]]
        print_table("STEP 5: Disk Usage by Configuration",
                    ["Hypertable", "Total Size"], size_rows)
    except Exception as exc:
        print(f"\n[SKIP] Disk usage query failed: {exc}")

    # ── Section 3: Compression query performance ──────────────────────────────
    comp_rows = []
    for qname, qtpl in COMPRESSION_QUERIES.items():
        row = [qname]
        for table, label in zip(HYPERTABLES, LABELS):
            sql = qtpl.format(table=table)
            try:
                ms = run_query(cur, sql)
                row.append(f"{ms:.1f} ms")
            except Exception as exc:
                row.append(f"ERR")
        comp_rows.append(row)
    print_table("STEP 5: Post-Compression Query Times",
                ["Query"] + LABELS, comp_rows)

    # ── Section 4: Continuous aggregate speedup ───────────────────────────────
    cag_rows = []
    for qname, sql in CAG_QUERIES.items():
        try:
            ms = run_query(cur, sql)
            cag_rows.append([qname, f"{ms:.1f} ms"])
        except Exception as exc:
            cag_rows.append([qname, f"ERR: {exc}"])

    print_table("STEP 6: Continuous Aggregate Performance",
                ["Query", "Execution Time (median)"], cag_rows)

    # ── Speedup summary ───────────────────────────────────────────────────────
    if len(cag_rows) >= 2:
        try:
            raw_ms = float(cag_rows[0][1].replace(" ms",""))
            cag_ms = float(cag_rows[1][1].replace(" ms",""))
            speedup = raw_ms / cag_ms if cag_ms > 0 else 0
            print(f"\n  >> 15-min CAG is {speedup:.1f}× faster than raw query")
        except Exception:
            pass

    cur.close()
    conn.close()
    print("\nBenchmark complete.\n")


if __name__ == "__main__":
    main()
