"""people_export.py — Builds the .xlsx export of the Metadata page's
roster (the page was renamed from "People" to "Metadata" for clarity —
this module's name is unchanged since it's about interviewee-metadata
records, i.e. "people", not the page label).

A small, standalone module (like env_store.py) rather than logic embedded
in pages/6_Metadata.py: it's a pure function with no Streamlit dependency,
so it's directly unit-testable, and keeps that page's file focused on the
page itself.
"""

import io

from openpyxl import Workbook

# Same column set/order as the on-screen table on the Metadata page, so
# the export always matches what's shown there. (field key, column header).
COLUMNS = [
    ("name", "Name"),
    ("role", "Role"),
    ("organization", "Organization"),
    ("rank", "Rank"),
    ("branch_service", "Branch / service"),
    ("seniority_level", "Seniority"),
    ("relationship", "Relationship"),
    ("interview_status", "Interview status"),
    ("interview_date", "Interview date"),
    ("descriptor", "Descriptor"),
]


def build_people_excel(people: list[dict]) -> bytes:
    """Build a one-sheet .xlsx workbook, one row per person (in the order
    given), and return its raw bytes — ready for st.download_button's
    `data`. Built directly with openpyxl rather than round-tripping
    through pandas, since pandas is only an incidental dependency of
    Streamlit today, not one this app otherwise relies on."""
    wb = Workbook()
    ws = wb.active
    ws.title = "People"
    ws.append([header for _, header in COLUMNS])
    for p in people:
        ws.append([p.get(field) or "" for field, _ in COLUMNS])

    # Rough auto-width so columns aren't all default-width in Excel — a
    # nicety, not load-bearing, so it degrades harmlessly if a value is
    # ever an unexpected type.
    for col_cells in ws.columns:
        try:
            longest = max(len(str(c.value)) for c in col_cells if c.value is not None)
        except ValueError:
            longest = 0
        ws.column_dimensions[col_cells[0].column_letter].width = min(max(longest + 2, 10), 50)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
