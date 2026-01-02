"""
Project: Unified Daily Scanner HTML Report
Filename: core/report_html.py
Version: 1.0.0
Author: Copilot, Gemini (Assistant) & [Your Name]
Date: 2025-12-16

Purpose:
    Generate a static HTML report from unified_report.csv
    for quick, zero-dependency visual inspection.
"""

import os
import pandas as pd
import config

UNIFIED_CSV = os.path.join(config.DATA_DIR, "unified_report.csv")
OUT_HTML    = os.path.join(config.DATA_DIR, "unified_report.html")


def generate_html_report():
    if not os.path.exists(UNIFIED_CSV):
        print(f"[ERROR] Missing unified report: {UNIFIED_CSV}")
        return

    df = pd.read_csv(UNIFIED_CSV)

    if df.empty:
        print("[WARN] unified_report.csv is empty. No HTML generated.")
        return

    # Limit columns to something readable; reorder for UX
    preferred_cols = [
        "Symbol",
        "Scanner",
        "StratScore",
        "StratConviction",
        "CatalystScore",
        "CatalystStrength",
        "Reason",
        "Move%",
        "Gap%",
        "RS_Score",
        "Vol_M",
        "Float_M",
        "Depth%",
        "Sector",
        "Industry",
        "CreatedAt",
    ]
    cols = [c for c in preferred_cols if c in df.columns]
    df = df[cols]

    # Basic HTML-escaped table content
    table_html = df.to_html(
        index=False,
        classes="data-table",
        border=0,
        escape=True
    )

    # Full HTML document
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>Unified Daily Report</title>
<style>
    body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        margin: 20px;
        background-color: #111;
        color: #eee;
    }}
    h1 {{
        margin-bottom: 4px;
    }}
    .meta {{
        font-size: 0.9rem;
        color: #aaa;
        margin-bottom: 16px;
    }}
    .filters {{
        margin-bottom: 16px;
    }}
    .filters button {{
        margin-right: 8px;
        padding: 4px 10px;
        border-radius: 4px;
        border: 1px solid #444;
        background-color: #222;
        color: #eee;
        cursor: pointer;
        font-size: 0.85rem;
    }}
    .filters button.active {{
        background-color: #3b82f6;
        border-color: #60a5fa;
    }}
    table.data-table {{
        border-collapse: collapse;
        width: 100%;
        font-size: 0.85rem;
    }}
    table.data-table th, table.data-table td {{
        border-bottom: 1px solid #333;
        padding: 4px 8px;
        text-align: left;
        white-space: nowrap;
    }}
    table.data-table th {{
        cursor: pointer;
        background-color: #181818;
        position: sticky;
        top: 0;
        z-index: 1;
    }}
    table.data-table tr:nth-child(even) {{
        background-color: #181818;
    }}
    table.data-table tr:nth-child(odd) {{
        background-color: #151515;
    }}
    table.data-table tr:hover {{
        background-color: #272727;
    }}
    .conv-A {{
        background-color: #064e3b !important;
    }}
    .conv-B {{
        background-color: #4b4730 !important;
    }}
    .conv-C {{
        background-color: #1f2933 !important;
    }}
</style>
</head>
<body>
<h1>Unified Daily Scanner Report</h1>
<div class="meta">
    Source: unified_report.csv | Rows: {len(df)} |
    Generated from Strategy Engine v2 outputs
</div>

<div class="filters">
    <strong>Scanner:</strong>
    <button data-scanner="ALL" class="active">All</button>
    <button data-scanner="EP">EP</button>
    <button data-scanner="TREND">TREND</button>
    <button data-scanner="HTF">HTF</button>
</div>

{table_html}

<script>
// Scanner filter
const buttons = document.querySelectorAll('.filters button');
const table = document.querySelector('table.data-table');
const rows = Array.from(table.querySelectorAll('tbody tr'));

buttons.forEach(btn => {{
    btn.addEventListener('click', () => {{
        buttons.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        const target = btn.getAttribute('data-scanner');
        const scannerIdx = Array.from(table.querySelectorAll('th'))
            .findIndex(th => th.textContent.trim() === 'Scanner');

        rows.forEach(row => {{
            if (target === 'ALL') {{
                row.style.display = '';
            }} else {{
                const cell = row.children[scannerIdx];
                if (!cell) return;
                const val = cell.textContent.trim();
                row.style.display = (val === target) ? '' : 'none';
            }}
        }});
    }});
}});

// Conviction highlighting
(function applyConvictionClasses() {{
    const headers = Array.from(table.querySelectorAll('th'));
    const convIdx = headers.findIndex(th => th.textContent.trim() === 'StratConviction');
    if (convIdx === -1) return;

    rows.forEach(row => {{
        const cell = row.children[convIdx];
        if (!cell) return;
        const val = cell.textContent.trim().toUpperCase();
        if (val === 'A') row.classList.add('conv-A');
        else if (val === 'B') row.classList.add('conv-B');
        else if (val === 'C') row.classList.add('conv-C');
    }});
}})();

// Simple column sort
(function enableSorting() {{
    const headers = Array.from(table.querySelectorAll('th'));
    headers.forEach((th, idx) => {{
        let asc = false;
        th.addEventListener('click', () => {{
            const tbody = table.querySelector('tbody');
            const sorted = Array.from(tbody.querySelectorAll('tr'))
                .sort((a, b) => {{
                    const ta = a.children[idx].textContent.trim();
                    const tb = b.children[idx].textContent.trim();

                    const na = parseFloat(ta.replace(/[^0-9.-]/g, ''));
                    const nb = parseFloat(tb.replace(/[^0-9.-]/g, ''));

                    if (!isNaN(na) && !isNaN(nb)) {{
                        return asc ? na - nb : nb - na;
                    }} else {{
                        return asc
                            ? ta.localeCompare(tb)
                            : tb.localeCompare(ta);
                    }}
                }});
            asc = !asc;
            sorted.forEach(row => tbody.appendChild(row));
        }});
    }});
}})();
</script>
</body>
</html>
"""

    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[SUCCESS] Wrote HTML report to {OUT_HTML}")


if __name__ == "__main__":
    print("\n=== Unified Daily HTML Report Builder ===")
    generate_html_report()