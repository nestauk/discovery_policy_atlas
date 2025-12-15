#!/usr/bin/env python3
"""
Standardize bibliography CSV files for evaluation.

This script reads all CSV files in the bibliographies directory and creates
standardized versions with consistent column names and values.

Standardized format:
- title: The title of the paper
- authors: Author list (if available; otherwise blank)
- title_abstract_screen: 1 for include, 0 for exclude
- full_text_screen: 1 for include, 0 for exclude
"""

import csv
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def normalize_column_name(name: str) -> str:
    """Normalize column name by removing extra spaces and converting to lowercase."""
    return " ".join(name.strip().split()).lower()


def find_title_column(headers: List[str]) -> Optional[str]:
    """Find the title column from headers."""
    normalized = {normalize_column_name(h): h for h in headers}

    # Try exact matches first
    for candidate in ["title"]:
        if candidate in normalized:
            return normalized[candidate]

    return None


def find_author_column(headers: List[str]) -> Optional[str]:
    """Find the author(s) column from headers, if present."""
    normalized = {normalize_column_name(h): h for h in headers}

    for candidate in ["authors", "author", "author(s)", "author list"]:
        candidate_norm = normalize_column_name(candidate)
        if candidate_norm in normalized:
            return normalized[candidate_norm]

    # Fallback: look for any column starting with 'author'
    for norm_name, orig_name in normalized.items():
        if norm_name.startswith("author"):
            return orig_name

    return None


def find_screening_columns(headers: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """Find title/abstract and full text screening columns."""
    normalized = {normalize_column_name(h): h for h in headers}

    title_abstract_col = None
    full_text_col = None

    # Patterns for title/abstract screening
    ta_patterns = [
        r"^title\s*/?\s*abstract",
        r"^title\s+and\s+abstract",
        r"^title\s+screen",
        r"^abstract\s+screen",
    ]

    # Patterns for full text screening
    ft_patterns = [
        r"^full[\s-]*text",
    ]

    # Find title/abstract column via regex patterns
    for norm_name, orig_name in normalized.items():
        for pattern in ta_patterns:
            if re.match(pattern, norm_name):
                title_abstract_col = orig_name
                break
        if title_abstract_col:
            break

    # Fallback: standalone abstract/abstracts columns used as screening indicators
    if not title_abstract_col:
        for norm_name, orig_name in normalized.items():
            if norm_name in ("abstract", "abstracts", "abstract screening"):
                title_abstract_col = orig_name
                break

    # Find full text column
    for norm_name, orig_name in normalized.items():
        for pattern in ft_patterns:
            if re.match(pattern, norm_name):
                full_text_col = orig_name
                break
        if full_text_col:
            break

    return title_abstract_col, full_text_col


def normalize_screening_value(value: Optional[str]) -> int:
    """
    Convert various screening values to standardized 1 (include) or 0 (exclude).

    Args:
        value: The original value from the CSV

    Returns:
        1 for include, 0 for exclude/blank
    """
    if value is None or value == "":
        return 0

    value_clean = str(value).strip().lower()

    # Handle numeric values
    if value_clean in ("1", "1.0"):
        return 1
    if value_clean in ("-1", "-1.0", "0", "0.0"):
        return 0

    # Handle text values
    include_values = ["include", "included", "yes", "y", "true", "t"]
    exclude_values = ["exclude", "excluded", "no", "n", "false", "f"]

    if value_clean in include_values:
        return 1
    if value_clean in exclude_values:
        return 0

    # Default to exclude if unknown
    return 0


def standardize_bibliography(input_path: Path, output_path: Path) -> Dict[str, any]:
    """
    Standardize a bibliography CSV file.

    Args:
        input_path: Path to input CSV file
        output_path: Path to output standardized CSV file

    Returns:
        Dictionary with standardization metadata
    """
    with input_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = list(reader)

    if not headers:
        return {
            "status": "error",
            "message": "No headers found",
            "input_file": str(input_path),
        }

    # Find columns
    title_col = find_title_column(headers)
    author_col = find_author_column(headers)
    ta_col, ft_col = find_screening_columns(headers)

    if not title_col:
        return {
            "status": "error",
            "message": "Title column not found",
            "input_file": str(input_path),
            "headers": headers,
        }

    # Create standardized rows
    standardized_rows = []
    ta_includes = 0
    ft_includes = 0

    for row in rows:
        title = (row.get(title_col) or "").strip()
        if not title:
            continue  # Skip rows without title

        authors = (row.get(author_col) or "").strip() if author_col else ""
        ta_value = normalize_screening_value(row.get(ta_col) if ta_col else None)
        ft_value = normalize_screening_value(row.get(ft_col) if ft_col else None)

        if ta_value == 1:
            ta_includes += 1
        if ft_value == 1:
            ft_includes += 1

        standardized_rows.append(
            {
                "title": title,
                "authors": authors,
                "title_abstract_screen": ta_value,
                "full_text_screen": ft_value,
            }
        )

    # Write standardized CSV
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "title",
                "authors",
                "title_abstract_screen",
                "full_text_screen",
            ],
        )
        writer.writeheader()
        writer.writerows(standardized_rows)

    return {
        "status": "success",
        "input_file": str(input_path),
        "output_file": str(output_path),
        "total_rows": len(rows),
        "standardized_rows": len(standardized_rows),
        "title_column": title_col,
        "author_column": author_col,
        "title_abstract_column": ta_col,
        "full_text_column": ft_col,
        "title_abstract_includes": ta_includes,
        "full_text_includes": ft_includes,
    }


def main():
    """Main function to standardize all bibliography files."""
    evals_dir = Path(__file__).resolve().parent
    biblio_dir = evals_dir / "bibliographies"
    output_dir = evals_dir / "bibliographies_standardized"

    if not biblio_dir.exists():
        print(f"Bibliography directory not found: {biblio_dir}")
        return 1

    # Find all CSV files
    csv_files = sorted(biblio_dir.glob("*.csv"))

    if not csv_files:
        print(f"No CSV files found in {biblio_dir}")
        return 1

    print(f"Found {len(csv_files)} bibliography files to standardize")
    print(f"Output directory: {output_dir}")
    print("-" * 80)

    results = []
    for csv_file in csv_files:
        output_file = output_dir / csv_file.name
        print(f"\nProcessing: {csv_file.name}")

        result = standardize_bibliography(csv_file, output_file)
        results.append(result)

        if result["status"] == "success":
            print("  ✓ Success")
            print(f"    Title column: {result['title_column']}")
            print(f"    Author column: {result['author_column']}")
            print(f"    Title/Abstract column: {result['title_abstract_column']}")
            print(f"    Full Text column: {result['full_text_column']}")
            print(f"    Total rows: {result['total_rows']}")
            print(f"    Standardized rows: {result['standardized_rows']}")
            print(f"    Title/Abstract includes: {result['title_abstract_includes']}")
            print(f"    Full Text includes: {result['full_text_includes']}")
        else:
            print(f"  ✗ Error: {result['message']}")
            if "headers" in result:
                print(f"    Available headers: {', '.join(result['headers'][:10])}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    successful = sum(1 for r in results if r["status"] == "success")
    failed = len(results) - successful

    print(f"Total files: {len(results)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")

    if failed > 0:
        print("\nFailed files:")
        for r in results:
            if r["status"] == "error":
                print(f"  - {Path(r['input_file']).name}: {r['message']}")

    # Write summary report
    summary_file = output_dir / "_standardization_report.txt"
    with summary_file.open("w", encoding="utf-8") as f:
        f.write("Bibliography Standardization Report\n")
        f.write("=" * 80 + "\n\n")

        for result in results:
            f.write(f"File: {Path(result['input_file']).name}\n")
            f.write(f"Status: {result['status']}\n")

            if result["status"] == "success":
                f.write(f"  Title column: {result['title_column']}\n")
                f.write(f"  Author column: {result['author_column']}\n")
                f.write(f"  Title/Abstract column: {result['title_abstract_column']}\n")
                f.write(f"  Full Text column: {result['full_text_column']}\n")
                f.write(f"  Total rows: {result['total_rows']}\n")
                f.write(f"  Standardized rows: {result['standardized_rows']}\n")
                f.write(
                    f"  Title/Abstract includes: {result['title_abstract_includes']}\n"
                )
                f.write(f"  Full Text includes: {result['full_text_includes']}\n")
            else:
                f.write(f"  Error: {result['message']}\n")

            f.write("\n")

        f.write("\nSummary:\n")
        f.write(f"  Total files: {len(results)}\n")
        f.write(f"  Successful: {successful}\n")
        f.write(f"  Failed: {failed}\n")

    print(f"\nDetailed report written to: {summary_file}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
