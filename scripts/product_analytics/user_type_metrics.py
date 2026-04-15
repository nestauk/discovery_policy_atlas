"""
Query use_case selections from the analysis_projects table
and output a bar chart of counts and percentages.

Usage:
    python scripts/product_analytics/user_type_metrics.py

Requires SUPABASE_URL and SUPABASE_KEY environment variables
(reads from backend/.env automatically).
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client
import matplotlib.pyplot as plt

# Load env from backend/.env
load_dotenv(Path(__file__).resolve().parents[2] / "backend" / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: SUPABASE_URL and SUPABASE_KEY must be set (check backend/.env)")
    sys.exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Only include projects created after use_case was deployed (2026-04-10)
USE_CASE_DEPLOY_DATE = "2026-04-10T00:00:00"

response = (
    supabase.table("analysis_projects")
    .select("search_query, created_at")
    .not_.is_("search_query", "null")
    .gte("created_at", USE_CASE_DEPLOY_DATE)
    .execute()
)

# Extract use_case values
use_cases = []
for row in response.data:
    sq = row.get("search_query") or {}
    uc = sq.get("use_case")
    use_cases.append(uc if uc else "not_set")

# Count occurrences
from collections import Counter

counts = Counter(use_cases)
total = sum(counts.values())

# Print table
print(f"\n{'Use Case':<30} {'Count':>6} {'Percentage':>10}")
print("-" * 48)
for label, count in counts.most_common():
    pct = (count / total) * 100 if total else 0
    print(f"{label:<30} {count:>6} {pct:>9.1f}%")
print("-" * 48)
print(f"{'Total':<30} {total:>6}")

# Bar chart
labels = [k for k, _ in counts.most_common()]
values = [v for _, v in counts.most_common()]
percentages = [(v / total) * 100 for v in values]

fig, ax1 = plt.subplots(figsize=(10, 5))

bars = ax1.bar(labels, values, color="#3B82F6", alpha=0.8)
ax1.set_ylabel("Count")
ax1.set_xlabel("Use Case")
ax1.set_title("Use Case Selections")

# Add percentage labels on bars
for bar, pct in zip(bars, percentages):
    ax1.text(
        bar.get_x() + bar.get_width() / 2,
        bar.get_height() + 0.3,
        f"{pct:.1f}%",
        ha="center",
        va="bottom",
        fontsize=10,
    )

plt.xticks(rotation=30, ha="right")
plt.tight_layout()

output_path = Path(__file__).parent / "use_case_chart.png"
plt.savefig(output_path, dpi=150)
print(f"\nChart saved to {output_path}")
plt.show()
