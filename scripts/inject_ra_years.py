"""
inject_ra_years.py — preprocess a fresh RA text scrape to add inferred years to bare date lines.

RA's UI drops the year from date lines when the year matches the current display context
(e.g. "Sat, 9 May" instead of "Sat, 9 May 2026"). The `parse_ra.py` date regex requires
4-digit years, so bare dates get skipped silently.

This script walks the file top-to-bottom, tracks the most recent `̸<Month YYYY>` header,
and stamps that year onto each bare date line. Writes the result to
`<input>_normalized.txt` next to the input.

Usage:
    python3 scripts/inject_ra_years.py raw/20260513_basement_text.txt
"""

import re
import sys
from pathlib import Path

MONTH_HDR = re.compile(r"^̸([A-Z][a-z]+)\s+(\d{4})$")
DATE_WITH_YEAR = re.compile(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+\d{1,2}\s+\w+\s+\d{4}\s*$")
DATE_NO_YEAR = re.compile(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+\d{1,2}\s+\w+\s*$")


def main():
    if len(sys.argv) != 2:
        print("usage: inject_ra_years.py <input_text_file>")
        sys.exit(1)

    src_path = Path(sys.argv[1])
    out_path = src_path.with_name(src_path.stem + "_normalized" + src_path.suffix)

    current_year = None
    fixed = 0
    out_lines = []
    for line in src_path.read_text(encoding="utf-8").splitlines():
        m = MONTH_HDR.match(line)
        if m:
            current_year = m.group(2)
        if DATE_NO_YEAR.match(line) and not DATE_WITH_YEAR.match(line):
            if current_year:
                line = line.rstrip() + " " + current_year
                fixed += 1
        out_lines.append(line)

    out_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"Injected year into {fixed} date lines")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
