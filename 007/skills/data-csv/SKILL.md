---
name: data-csv
description: Parse, query, and transform CSV files. Use when asked to read, filter, sort, or convert CSV data.
license: Apache-2.0
metadata:
  author: ooe
  version: "1.0"
---

# data-csv

CSV parsing and transformation utilities.

## Usage

```bash
# Show CSV info (columns, row count)
python scripts/csv_tool.py info data.csv

# Print first N rows
python scripts/csv_tool.py head data.csv --rows 5

# Filter rows by column value
python scripts/csv_tool.py filter data.csv --column age --gt 30

# Select specific columns
python scripts/csv_tool.py select data.csv --columns name,age

# Sort by column
python scripts/csv_tool.py sort data.csv --by age --desc

# Convert to JSON
python scripts/csv_tool.py json data.csv
```

## Dependencies

Python 3.6+ (standard library only)
