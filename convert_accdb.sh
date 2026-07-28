#!/bin/bash
# ============================================================
# Convert Access Database (.accdb) to SQLite
# Uses mdbtools to export CSV, then Python/sqlite3 to import
# ============================================================
set -e

ACCDB_FILE="${1:-نسخة البحث الدور الأول 2026 - نظام حديث.accdb}"
SQLITE_FILE="${2:-data/students.db}"
TMPDIR_CONV="/tmp/accdb_convert"

echo "=== Access to SQLite Converter ==="
echo "Source: $ACCDB_FILE"
echo "Target: $SQLITE_FILE"

# Check prerequisites
if ! command -v mdb-export &> /dev/null; then
    echo "ERROR: mdbtools is not installed. Install with: apt-get install mdbtools"
    exit 1
fi

# Create temp and output dirs
mkdir -p "$TMPDIR_CONV"
mkdir -p "$(dirname "$SQLITE_FILE")"

# Remove old database if exists
rm -f "$SQLITE_FILE"

echo "Exporting Stage_New_Search to CSV..."
mdb-export "$ACCDB_FILE" Stage_New_Search > "$TMPDIR_CONV/stage_new_search.csv"
echo "  Done: $(wc -l < "$TMPDIR_CONV/stage_new_search.csv") lines"

echo "Exporting Stage_New_Dawly to CSV..."
mdb-export "$ACCDB_FILE" Stage_New_Dawly > "$TMPDIR_CONV/stage_new_dawly.csv"
echo "  Done: $(wc -l < "$TMPDIR_CONV/stage_new_dawly.csv") lines"

echo "Importing into SQLite..."
export CONV_TMPDIR="$TMPDIR_CONV"
export CONV_SQLITE="$SQLITE_FILE"

python3 -c '
import csv, sqlite3, os

tmpdir = os.environ["CONV_TMPDIR"]
sqlite_file = os.environ["CONV_SQLITE"]

conn = sqlite3.connect(sqlite_file)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS students (
    seating_no INTEGER PRIMARY KEY,
    arabic_name TEXT NOT NULL,
    total_degree REAL,
    student_case INTEGER,
    student_case_desc TEXT,
    c_flage REAL
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS student_subjects (
    seating_no INTEGER PRIMARY KEY,
    arabic_name TEXT,
    s1 INTEGER,
    s10 INTEGER,
    s14 INTEGER,
    student_case INTEGER,
    student_case_desc TEXT
)
""")

print("  Importing Stage_New_Search...")
count = 0
with open(os.path.join(tmpdir, "stage_new_search.csv"), "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        try:
            seating_no = int(row["seating_no"])
            arabic_name = row.get("arabic_name", "").strip()
            td = row.get("total_degree", "")
            total_degree = float(td) if td else 0.0
            sc = row.get("student_case", "")
            student_case = int(sc) if sc else 0
            student_case_desc = row.get("student_case_desc", "").strip()
            cf = row.get("c_flage", "")
            c_flage = float(cf) if cf else 0.0
            cur.execute(
                "INSERT OR REPLACE INTO students VALUES (?, ?, ?, ?, ?, ?)",
                (seating_no, arabic_name, total_degree, student_case, student_case_desc, c_flage)
            )
            count += 1
        except Exception:
            pass
print(f"  Imported {count:,} student records")

print("  Importing Stage_New_Dawly...")
count2 = 0
with open(os.path.join(tmpdir, "stage_new_dawly.csv"), "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        try:
            seating_no = int(row["seating_no"])
            arabic_name = row.get("arabic_name", "").strip()
            s1 = int(row.get("s1", 0) or 0)
            s10 = int(row.get("s10", 0) or 0)
            s14 = int(row.get("s14", 0) or 0)
            sc = row.get("student_case", "")
            student_case = int(sc) if sc else 0
            student_case_desc = row.get("student_case_desc", "").strip()
            cur.execute(
                "INSERT OR REPLACE INTO student_subjects VALUES (?, ?, ?, ?, ?, ?, ?)",
                (seating_no, arabic_name, s1, s10, s14, student_case, student_case_desc)
            )
            count2 += 1
        except Exception:
            pass
print(f"  Imported {count2:,} subject records")

print("  Creating indexes...")
cur.execute("CREATE INDEX IF NOT EXISTS idx_students_name ON students(arabic_name)")
cur.execute("CREATE INDEX IF NOT EXISTS idx_subjects_seating ON student_subjects(seating_no)")
conn.commit()

cur.execute("SELECT COUNT(*) FROM students")
total = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM student_subjects")
total2 = cur.fetchone()[0]
print(f"  Verification: {total:,} students, {total2:,} subject records")
conn.close()
print("  SQLite database created successfully!")
'

# Cleanup
rm -rf "$TMPDIR_CONV"

echo ""
echo "=== Conversion complete ==="
echo "SQLite database: $SQLITE_FILE"
echo "Size: $(du -h "$SQLITE_FILE" | cut -f1)"
