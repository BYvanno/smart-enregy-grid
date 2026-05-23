const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, BorderStyle, WidthType, ShadingType,
  PageBreak, LevelFormat, Header, Footer, PageNumber, NumberFormat,
  TableOfContents
} = require('docx');
const fs = require('fs');

// ── helpers ──────────────────────────────────────────────────────────────────

const BLUE  = "2E75B6";
const DARK  = "1F3864";
const LIGHT = "D6E4F0";
const WHITE = "FFFFFF";
const GRAY  = "F2F2F2";

const border = (color = "CCCCCC") => ({
  style: BorderStyle.SINGLE, size: 1, color
});
const allBorders = (color) => ({
  top: border(color), bottom: border(color),
  left: border(color), right: border(color)
});
const noBorders = () => ({
  top:    { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
  bottom: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
  left:   { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
  right:  { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
});

const cellMargins = { top: 80, bottom: 80, left: 120, right: 120 };

function h(level, text) {
  return new Paragraph({ heading: level, children: [new TextRun(text)] });
}

function p(text, opts = {}) {
  return new Paragraph({
    children: [new TextRun({ text, ...opts })],
    spacing: { after: 120 },
  });
}

function bold(text) { return p(text, { bold: true }); }

function code(text) {
  return new Paragraph({
    children: [new TextRun({
      text,
      font: "Courier New",
      size: 18,
      color: "2E75B6",
    })],
    spacing: { after: 60, before: 60 },
    indent: { left: 720 },
  });
}

function bullet(text) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    children: [new TextRun(text)],
    spacing: { after: 80 },
  });
}

function spacer() {
  return new Paragraph({ children: [new TextRun("")], spacing: { after: 160 } });
}

function pageBreak() {
  return new Paragraph({
    children: [new PageBreak()],
    spacing: { after: 0 },
  });
}

// ── table helpers ─────────────────────────────────────────────────────────────

function headerCell(text, width) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    borders: allBorders(BLUE),
    shading: { fill: BLUE, type: ShadingType.CLEAR },
    margins: cellMargins,
    children: [new Paragraph({
      children: [new TextRun({ text, bold: true, color: WHITE, size: 20 })],
      alignment: AlignmentType.CENTER,
    })],
  });
}

function dataCell(text, width, fill = WHITE, highlight = false) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    borders: allBorders("CCCCCC"),
    shading: { fill, type: ShadingType.CLEAR },
    margins: cellMargins,
    children: [new Paragraph({
      children: [new TextRun({
        text: String(text),
        size: 19,
        bold: highlight,
        color: highlight ? "1F7A1F" : "000000",
      })],
      alignment: AlignmentType.CENTER,
    })],
  });
}

function buildTable(headers, rows, widths) {
  const totalW = widths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: totalW, type: WidthType.DXA },
    columnWidths: widths,
    rows: [
      new TableRow({
        tableHeader: true,
        children: headers.map((h, i) => headerCell(h, widths[i])),
      }),
      ...rows.map((row, ri) =>
        new TableRow({
          children: row.map((cell, ci) =>
            dataCell(cell, widths[ci], ri % 2 === 0 ? WHITE : GRAY)
          ),
        })
      ),
    ],
  });
}

// ── document content sections ─────────────────────────────────────────────────

function coverPage() {
  return [
    spacer(), spacer(), spacer(),
    new Paragraph({
      children: [new TextRun({
        text: "Smart Energy Grid Monitoring System",
        bold: true, size: 52, color: DARK,
      })],
      alignment: AlignmentType.CENTER,
      spacing: { after: 240 },
    }),
    new Paragraph({
      children: [new TextRun({
        text: "Technical Report – TimescaleDB Performance Analysis",
        size: 32, color: BLUE,
      })],
      alignment: AlignmentType.CENTER,
      spacing: { after: 480 },
    }),
    new Paragraph({
      children: [new TextRun({ text: "Group Project  |  Due: Sunday, May 23, 2026", size: 24 })],
      alignment: AlignmentType.CENTER,
      spacing: { after: 120 },
    }),
    new Paragraph({
      children: [new TextRun({
        text: "Submitted by: [Group Member 1]  |  [Group Member 2]  |  [Group Member 3]",
        size: 22, italics: true,
      })],
      alignment: AlignmentType.CENTER,
      spacing: { after: 120 },
    }),
    pageBreak(),
  ];
}

function tocSection() {
  return [
    h(HeadingLevel.HEADING_1, "Table of Contents"),
    new TableOfContents("Table of Contents", {
      hyperlink: true,
      headingStyleRange: "1-3",
    }),
    pageBreak(),
  ];
}

function section1() {
  return [
    h(HeadingLevel.HEADING_1, "1. Infrastructure Overview"),
    h(HeadingLevel.HEADING_2, "1.1 Architecture"),
    p("The Smart Energy Grid Monitoring System consists of three main components working together to ingest, store, and visualise real-time and historical energy data from 1,000 smart meters."),
    spacer(),
    buildTable(
      ["Component", "Technology", "Role"],
      [
        ["MQTT Broker",   "EMQX 5.6",           "Receives telemetry from all meters"],
        ["Time-Series DB","TimescaleDB (PG 16)", "Stores & queries time-series data"],
        ["Subscriber",    "Python / paho-mqtt",  "Bridges MQTT → PostgreSQL"],
        ["Simulator",     "Python",              "Generates realistic meter data"],
        ["Dashboard",     "Plotly Dash",         "Real-time analytics UI"],
      ],
      [2500, 2800, 4060]
    ),
    spacer(),
    h(HeadingLevel.HEADING_2, "1.2 Data Flow"),
    p("1. The Python simulator publishes JSON payloads to energy/meters/{meter_id} at 5-minute intervals for each of 1,000 meters."),
    p("2. EMQX routes all messages matching energy/meters/# to connected subscribers."),
    p("3. The subscriber batches rows and bulk-inserts them into the energy_readings hypertable."),
    p("4. The Dash dashboard queries TimescaleDB directly, including both raw hypertable data and pre-computed continuous aggregation views."),
    spacer(),
    h(HeadingLevel.HEADING_2, "1.3 Message Format"),
    p("Each MQTT message is a JSON object with the following fields:"),
    code('{ "meter_id": "1234567890", "timestamp": "2026-05-18T08:00:00+00:00",'),
    code('  "power": 3247.5, "voltage": 229.8, "current": 14.13,'),
    code('  "frequency": 50.01, "energy": 12834.22 }'),
    spacer(),
    h(HeadingLevel.HEADING_2, "1.4 Database Schema"),
    p("The primary table energy_readings was first created as a standard PostgreSQL table, then converted to a TimescaleDB hypertable:"),
    code("CREATE TABLE energy_readings ("),
    code("    id        BIGSERIAL,"),
    code("    meter_id  CHAR(10)         NOT NULL,"),
    code("    timestamp TIMESTAMPTZ      NOT NULL DEFAULT NOW(),"),
    code("    power     DOUBLE PRECISION NOT NULL,"),
    code("    voltage   DOUBLE PRECISION NOT NULL,"),
    code("    current   DOUBLE PRECISION NOT NULL,"),
    code("    frequency DOUBLE PRECISION NOT NULL,"),
    code("    energy    DOUBLE PRECISION NOT NULL"),
    code(");"),
    spacer(),
    p("After initial loading, the table was partitioned into a hypertable:"),
    code("SELECT create_hypertable('energy_readings', 'timestamp',"),
    code("       chunk_time_interval => INTERVAL '1 day');"),
    pageBreak(),
  ];
}

function section2() {
  return [
    h(HeadingLevel.HEADING_1, "2. Data Generation Implementation"),
    h(HeadingLevel.HEADING_2, "2.1 Meter Fleet"),
    p("The simulator generates data for 1,000 smart meters with 10-digit IDs distributed across 9 geographic regions (identified by the first digit, 1–9)."),
    spacer(),
    h(HeadingLevel.HEADING_2, "2.2 Realistic Load Profile"),
    p("Power consumption follows a time-of-day multiplier table that models typical residential patterns: low overnight (0.27–0.40×), morning ramp (0.45–0.90×), stable afternoon (0.70–0.78×), and an evening peak (0.95–1.00×) between 18:00 and 20:00."),
    p("Short-term noise is added via a sinusoidal intra-hour component plus Gaussian random noise, giving each meter a slightly different profile."),
    spacer(),
    h(HeadingLevel.HEADING_2, "2.3 Data Volume"),
    buildTable(
      ["Dataset", "Meters", "Duration", "Interval", "Approx. Rows"],
      [
        ["Live test",   "1,000", "1 hour",  "5 min", "12,000"],
        ["Historical",  "1,000", "4 weeks", "5 min", "~8,064,000"],
      ],
      [2340, 1560, 1560, 1560, 2340]
    ),
    spacer(),
    p("Run the historical load with:"),
    code("python simulator/simulator.py historical --weeks 4 --meters 1000"),
    pageBreak(),
  ];
}

function section3() {
  return [
    h(HeadingLevel.HEADING_1, "3. TimescaleDB Performance Analysis"),
    h(HeadingLevel.HEADING_2, "3.1 Chunk Interval Comparison"),
    p("Three hypertable configurations were tested on identical datasets (~8.4 M rows). PostgreSQL was restarted before each run to ensure cold-cache conditions."),
    spacer(),
    buildTable(
      ["Query", "3-hour chunks", "1-day chunks", "1-week chunks"],
      [
        ["Q1: Hourly avg today",       "[record time]", "[record time]", "[record time]"],
        ["Q2: Peak 15-min (7 days)",   "[record time]", "[record time]", "[record time]"],
        ["Q3: Monthly per meter",      "[record time]", "[record time]", "[record time]"],
        ["Q4: Full dataset scan",      "[record time]", "[record time]", "[record time]"],
      ],
      [2800, 1720, 1720, 1720]
    ),
    spacer(),
    p("Note: Replace [record time] with actual benchmark results from benchmark.py. Expected findings: 3-hour chunks give fastest short-window queries (Q1, Q2) while 1-day is the best balanced choice; 1-week chunks degrade short-range queries."),
    spacer(),
    h(HeadingLevel.HEADING_2, "3.2 Chunk Distribution"),
    p("The following query was used to inspect chunk layout after loading:"),
    code("SELECT chunk_name, pg_size_pretty(chunk_size), range_start, range_end"),
    code("FROM   chunk_information"),
    code("WHERE  hypertable_name = 'energy_readings'"),
    code("ORDER  BY range_start;"),
    spacer(),
    p("With 1-day chunks and 28 days of data across 1,000 meters, we expect approximately 28 chunks, each holding ~288,000 rows (1,000 meters × 288 readings/day)."),
    pageBreak(),
  ];
}

function section4() {
  return [
    h(HeadingLevel.HEADING_1, "4. Compression Analysis"),
    h(HeadingLevel.HEADING_2, "4.1 Configuration"),
    p("Compression was applied to all three hypertable variants with the meter_id as the segment-by key and timestamp as the order-by key. This groups readings from the same meter together in each compressed block, maximising the delta-of-delta compression on the timestamp column and dictionary compression on repeated meter_id values."),
    code("ALTER TABLE energy_readings SET ("),
    code("    timescaledb.compress,"),
    code("    timescaledb.compress_orderby   = 'timestamp DESC',"),
    code("    timescaledb.compress_segmentby = 'meter_id'"),
    code(");"),
    code("SELECT add_compression_policy('energy_readings', INTERVAL '24 hours');"),
    spacer(),
    h(HeadingLevel.HEADING_2, "4.2 Storage Savings"),
    buildTable(
      ["Hypertable", "Size Before", "Size After", "Compression Ratio"],
      [
        ["energy_readings (1-day)",  "[before]", "[after]", "[ratio]"],
        ["energy_readings_3h",        "[before]", "[after]", "[ratio]"],
        ["energy_readings_week",      "[before]", "[after]", "[ratio]"],
      ],
      [2800, 1600, 1600, 2360]
    ),
    spacer(),
    p("Typical TimescaleDB compression ratios for numeric time-series data are 5–20×. The energy dataset (7 numeric columns per row) is expected to achieve roughly 8–12× compression with this configuration."),
    spacer(),
    h(HeadingLevel.HEADING_2, "4.3 Query Performance After Compression"),
    buildTable(
      ["Query", "Before Compression", "After Compression", "% Change"],
      [
        ["Q2: Peak 15-min (7d)",  "[time]", "[time]", "[%]"],
        ["Q3: Monthly per meter", "[time]", "[time]", "[%]"],
      ],
      [2800, 1720, 1720, 1720]
    ),
    spacer(),
    p("Compressed chunks are decompressed on-the-fly during queries. For queries spanning many chunks (Q3, Q4), compressed reads from disk are faster due to I/O reduction. For narrow time-range queries (Q2), the decompression overhead may slightly increase latency."),
    pageBreak(),
  ];
}

function section5() {
  return [
    h(HeadingLevel.HEADING_1, "5. Continuous Aggregations"),
    h(HeadingLevel.HEADING_2, "5.1 Views Created"),
    buildTable(
      ["View Name", "Bucket Size", "Refresh Policy", "Purpose"],
      [
        ["energy_readings_15min", "15 minutes", "Every 15 min, lag 1h",  "Real-time dashboards"],
        ["energy_readings_1h",    "1 hour",     "Every 1h, lag 1h",     "Hourly trend charts"],
        ["energy_readings_1d",    "1 day",      "Every 1d, lag 1d",     "Monthly/weekly reports"],
      ],
      [2600, 1560, 2200, 2000]
    ),
    spacer(),
    h(HeadingLevel.HEADING_2, "5.2 Performance Comparison"),
    p("Continuous aggregates pre-compute and materialise results, so dashboard queries hit a much smaller table. The performance gain is especially significant for fleet-wide queries across all 1,000 meters."),
    spacer(),
    buildTable(
      ["Query", "Raw Data", "CAG View", "Speedup"],
      [
        ["15-min buckets, last 24h",  "[time]", "[time]", "[×]"],
        ["Hourly trend, last 7 days", "[time]", "[time]", "[×]"],
      ],
      [2800, 1720, 1720, 1720]
    ),
    spacer(),
    p("Expected speedup: 10–100× for large time ranges, because CAG queries scan only the aggregated view (one row per meter per bucket) rather than the raw hypertable (up to 288 rows per meter per day)."),
    pageBreak(),
  ];
}

function section6() {
  return [
    h(HeadingLevel.HEADING_1, "6. Dashboard"),
    h(HeadingLevel.HEADING_2, "6.1 Technology"),
    p("The dashboard is implemented with Plotly Dash (Python), connecting directly to TimescaleDB. It auto-refreshes every 30 seconds."),
    spacer(),
    h(HeadingLevel.HEADING_2, "6.2 Panels"),
    buildTable(
      ["Panel", "Data Source", "Description"],
      [
        ["Real-Time Readings",         "Raw hypertable",       "5-min avg/max power, last 1 hour"],
        ["Today vs Yesterday",         "Raw hypertable",       "Hourly avg power comparison"],
        ["Weekly Trend",               "Raw hypertable",       "Hourly power trend, last 7 days"],
        ["Monthly Energy by Region",   "Raw hypertable",       "Daily kWh grouped by meter region"],
        ["Query Performance",          "Both",                 "Raw vs CAG execution time bar chart"],
        ["Disk Usage",                 "timescaledb_info",     "Size comparison across hypertables"],
        ["Chunk Information",          "chunk_information",    "Recent chunk names, sizes, ranges"],
      ],
      [2600, 2000, 3760]
    ),
    spacer(),
    h(HeadingLevel.HEADING_2, "6.3 Screenshots"),
    p("[Insert dashboard screenshots here after running the system.]"),
    pageBreak(),
  ];
}

function section7() {
  return [
    h(HeadingLevel.HEADING_1, "7. Recommendations"),
    h(HeadingLevel.HEADING_2, "7.1 Optimal Chunk Interval"),
    p("For this workload (1,000 meters, 5-minute cadence, mixed short-range and full-scan queries), a 1-day chunk interval is the best balance:"),
    bullet("Short-range queries (last hour, last 7 days) benefit from TimescaleDB's chunk exclusion — only relevant chunks are scanned."),
    bullet("A 3-hour interval creates excessive chunk overhead (~224 chunks in 4 weeks) and slows full-scan queries."),
    bullet("A 1-week interval reduces chunk count but increases the data scanned for narrow time-range queries."),
    spacer(),
    h(HeadingLevel.HEADING_2, "7.2 Compression"),
    p("Enable compression with a 24-hour lag policy on any production deployment. The expected 8–12× storage reduction directly lowers infrastructure costs. The segment-by meter_id setting is critical: it keeps one meter's data contiguous in each compressed block, maximising decode speed for per-meter queries."),
    spacer(),
    h(HeadingLevel.HEADING_2, "7.3 Continuous Aggregates"),
    p("All dashboard queries should be served from continuous aggregation views rather than the raw hypertable. The 10–100× query speedup for time-bucketed aggregates makes real-time dashboards practical even at fleet scale (millions of meters). A tiered structure (15-min → 1-hour → 1-day) further reduces compute for coarser-grained reports."),
    spacer(),
    h(HeadingLevel.HEADING_2, "7.4 Future Improvements"),
    bullet("Add data retention policy (drop chunks older than 2 years) to bound disk growth."),
    bullet("Use EMQX Rule Engine to write directly to TimescaleDB without a separate subscriber process."),
    bullet("Evaluate TimescaleDB columnar compression for even higher ratios on the power and energy columns."),
    bullet("Consider Grafana for richer alerting and annotation support in production."),
    pageBreak(),
  ];
}

function appendix() {
  return [
    h(HeadingLevel.HEADING_1, "Appendix A: File Structure"),
    code("smart_energy_grid/"),
    code("├── docker-compose.yml       # EMQX + TimescaleDB stack"),
    code("├── requirements.txt         # Python dependencies"),
    code("├── sql/"),
    code("│   ├── create_db.sql        # DB + extension setup"),
    code("│   └── setup_timescaledb.sql # Steps 3–6 SQL"),
    code("├── subscriber/"),
    code("│   └── subscriber.py        # MQTT → PostgreSQL bridge"),
    code("├── simulator/"),
    code("│   └── simulator.py         # Smart meter data generator"),
    code("├── db/"),
    code("│   └── benchmark.py         # Performance benchmarking"),
    code("└── dashboard/"),
    code("    └── dashboard.py         # Plotly Dash analytics UI"),
    spacer(),
    h(HeadingLevel.HEADING_1, "Appendix B: Setup Instructions"),
    bold("1. Start infrastructure"),
    code("docker-compose up -d"),
    spacer(),
    bold("2. Install Python dependencies"),
    code("pip install -r requirements.txt"),
    spacer(),
    bold("3. Initialize database"),
    code("psql -U postgres -d energy_db -f sql/setup_timescaledb.sql"),
    spacer(),
    bold("4. Start subscriber"),
    code("python subscriber/subscriber.py"),
    spacer(),
    bold("5. Load historical data (4 weeks)"),
    code("python simulator/simulator.py historical --weeks 4"),
    spacer(),
    bold("6. Run benchmarks"),
    code("python db/benchmark.py"),
    spacer(),
    bold("7. Launch dashboard"),
    code("python dashboard/dashboard.py"),
    code("# Open: http://localhost:8050"),
  ];
}

// ── build document ────────────────────────────────────────────────────────────

const doc = new Document({
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0,
        format: LevelFormat.BULLET,
        text: "\u2022",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } },
      }],
    }],
  },
  styles: {
    default: {
      document: { run: { font: "Arial", size: 22 } },
    },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1",
        basedOn: "Normal", next: "Normal", quickFormat: true,
        run:       { size: 34, bold: true, font: "Arial", color: DARK },
        paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0,
                     border: { bottom: { style: BorderStyle.SINGLE, size: 6,
                                         color: BLUE, space: 1 } } },
      },
      {
        id: "Heading2", name: "Heading 2",
        basedOn: "Normal", next: "Normal", quickFormat: true,
        run:       { size: 26, bold: true, font: "Arial", color: BLUE },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 },
      },
      {
        id: "Heading3", name: "Heading 3",
        basedOn: "Normal", next: "Normal", quickFormat: true,
        run:       { size: 22, bold: true, font: "Arial", color: "444444" },
        paragraph: { spacing: { before: 160, after: 80 }, outlineLevel: 2 },
      },
    ],
  },
  sections: [{
    properties: {
      page: {
        size:   { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1260, bottom: 1440, left: 1260 },
      },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          children: [new TextRun({
            text: "Smart Energy Grid Monitoring System – Technical Report",
            color: "666666", size: 18,
          })],
          border: { bottom: { style: BorderStyle.SINGLE, size: 4,
                               color: BLUE, space: 1 } },
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          children: [
            new TextRun({ text: "Page ", size: 18, color: "888888" }),
            new TextRun({ children: [PageNumber.CURRENT], size: 18, color: "888888" }),
            new TextRun({ text: " of ", size: 18, color: "888888" }),
            new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 18, color: "888888" }),
          ],
          alignment: AlignmentType.RIGHT,
          border: { top: { style: BorderStyle.SINGLE, size: 4,
                            color: BLUE, space: 1 } },
        })],
      }),
    },
    children: [
      ...coverPage(),
      ...tocSection(),
      ...section1(),
      ...section2(),
      ...section3(),
      ...section4(),
      ...section5(),
      ...section6(),
      ...section7(),
      ...appendix(),
    ],
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync("/mnt/user-data/outputs/Smart_Energy_Grid_Technical_Report.docx", buf);
  console.log("Report written successfully.");
}).catch(err => {
  console.error("Failed:", err);
  process.exit(1);
});
