"""
report_import.py — Turn an uploaded, already-processed interview file
(.docx / .pdf / .md / .txt) into plain text, for Process Interview's
"already-processed result" path. Pure file parsing, like docx_export.py
in reverse: no Streamlit, no database, no API — so it's directly
testable, and ai.parse_processed_result only ever sees plain text.

The extracted text is what gets saved as that interview's raw_text, so
it's also what Corpus Chat reads and what every digest quote is verified
against — extraction must keep the document's real words, in reading
order, including everything inside tables (this app's own Word export is
almost entirely tables).
"""

import io
import re

SUPPORTED_EXTENSIONS = ["docx", "pdf", "md", "markdown", "txt"]


class ReportImportError(Exception):
    """Raised when an uploaded file can't be read as text. Pages should
    catch this and show st.error(str(e))."""


def _docx_text(data: bytes) -> str:
    """Walk the document body in order — paragraphs AND tables, the way
    it reads on the page. python-docx's doc.paragraphs alone skips every
    table, which would lose nearly all of this app's own report export.
    A merged cell shows up once per column it spans, so repeated cells
    in a row are collapsed; table rows become " | "-joined lines."""
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        doc = Document(io.BytesIO(data))
    except Exception as e:
        raise ReportImportError(f"Couldn't open that Word file ({e}).")

    lines: list[str] = []

    def walk(parent, element):
        for child in element.iterchildren():
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "p":
                text = Paragraph(child, parent).text.strip()
                if text:
                    lines.append(text)
            elif tag == "tbl":
                table = Table(child, parent)
                for row in table.rows:
                    seen, cells = set(), []
                    for cell in row.cells:
                        if id(cell._tc) in seen:
                            continue
                        seen.add(id(cell._tc))
                        text = "\n".join(
                            p.text.strip() for p in cell.paragraphs if p.text.strip()
                        )
                        # Nested tables inside a cell are rare but real.
                        for nested in cell.tables:
                            for nrow in nested.rows:
                                text += "\n" + " | ".join(c.text.strip() for c in nrow.cells)
                        if text.strip():
                            cells.append(text.strip())
                    if cells:
                        lines.append(" | ".join(cells))
                lines.append("")
            elif tag == "sdt":  # content controls wrap ordinary paragraphs
                content = child.find(child.tag.replace("sdt", "sdtContent"))
                if content is not None:
                    walk(parent, content)

    walk(doc, doc.element.body)
    return "\n".join(lines)


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except Exception as e:
        raise ReportImportError(f"Couldn't read that PDF ({e}).")
    text = "\n\n".join(p for p in pages if p)
    if not text.strip():
        raise ReportImportError(
            "That PDF has no selectable text (it's probably a scan or an "
            "image). Export it as Word or text instead, or paste the "
            "content in below."
        )
    return text


def _plain_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def extract_text(filename: str, data: bytes) -> str:
    """Plain text of one uploaded file, chosen by its extension. Raises
    ReportImportError for an unsupported type, an unreadable file, or a
    file with no text in it."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "docx":
        text = _docx_text(data)
    elif ext == "pdf":
        text = _pdf_text(data)
    elif ext in ("md", "markdown", "txt"):
        text = _plain_text(data)
    else:
        raise ReportImportError(
            f"“{filename}” isn't a supported file type — use "
            ".docx, .pdf, .md, or .txt."
        )
    # Tidy whitespace without touching words: normalize line endings,
    # strip trailing spaces, and collapse runs of 3+ blank lines.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise ReportImportError(f"“{filename}” doesn't contain any text.")
    return text
