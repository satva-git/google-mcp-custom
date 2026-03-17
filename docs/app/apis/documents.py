from .helper import setup_logger

logger = setup_logger(__name__)


def _convert_text_run(text_run):
    """Convert a TextRun element to markdown."""
    text = text_run.get("content", "")
    if not text or text == "\n":
        return text

    style = text_run.get("textStyle", {})
    link = style.get("link", {})

    # Strip trailing newline for formatting, re-add after
    trailing_newline = text.endswith("\n")
    if trailing_newline:
        text = text[:-1]

    if not text:
        return "\n" if trailing_newline else ""

    # Apply formatting
    if style.get("strikethrough"):
        text = f"~~{text}~~"
    if style.get("bold"):
        text = f"**{text}**"
    if style.get("italic"):
        text = f"*{text}*"

    # Apply link
    url = link.get("url")
    if url:
        text = f"[{text}]({url})"

    if trailing_newline:
        text += "\n"

    return text


def _convert_paragraph(paragraph, lists_dict):
    """Convert a Paragraph element to markdown."""
    style = paragraph.get("paragraphStyle", {})
    named_style = style.get("namedStyleType", "NORMAL_TEXT")
    bullet = paragraph.get("bullet", None)

    # Build text content from elements
    text_parts = []
    for element in paragraph.get("elements", []):
        text_run = element.get("textRun")
        if text_run:
            text_parts.append(_convert_text_run(text_run))

    text = "".join(text_parts).rstrip("\n")

    if not text.strip():
        return "\n"

    # Headings
    heading_map = {
        "HEADING_1": "# ",
        "HEADING_2": "## ",
        "HEADING_3": "### ",
        "HEADING_4": "#### ",
        "HEADING_5": "##### ",
        "HEADING_6": "###### ",
    }

    if named_style in heading_map:
        return f"{heading_map[named_style]}{text}\n"

    # Bullet / numbered lists
    if bullet:
        list_id = bullet.get("listId", "")
        nesting_level = bullet.get("nestingLevel", 0)
        indent = "  " * nesting_level

        # Determine if ordered or unordered from lists dict
        list_props = lists_dict.get(list_id, {}).get("listProperties", {})
        nesting_levels = list_props.get("nestingLevels", [])

        is_ordered = False
        if nesting_levels and len(nesting_levels) > nesting_level:
            glyph_type = nesting_levels[nesting_level].get("glyphType", "")
            if glyph_type in (
                "DECIMAL",
                "ALPHA",
                "UPPER_ALPHA",
                "ROMAN",
                "UPPER_ROMAN",
            ):
                is_ordered = True

        if is_ordered:
            return f"{indent}1. {text}\n"
        else:
            return f"{indent}- {text}\n"

    return f"{text}\n"


def _convert_table(table):
    """Convert a Table element to markdown."""
    rows = table.get("tableRows", [])
    if not rows:
        return ""

    md_rows = []
    for row in rows:
        cells = row.get("tableCells", [])
        cell_texts = []
        for cell in cells:
            # Extract text from cell content
            parts = []
            for content in cell.get("content", []):
                para = content.get("paragraph")
                if para:
                    for element in para.get("elements", []):
                        text_run = element.get("textRun")
                        if text_run:
                            parts.append(text_run.get("content", "").strip().replace("|", "\\|"))
            cell_texts.append(" ".join(parts))
        md_rows.append(cell_texts)

    if not md_rows:
        return ""

    lines = []
    # Header row
    lines.append("| " + " | ".join(md_rows[0]) + " |")
    lines.append("| " + " | ".join("---" for _ in md_rows[0]) + " |")
    # Data rows
    for row in md_rows[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines) + "\n"


def _convert_body_to_markdown(body, lists_dict):
    """Convert a Google Docs body to markdown."""
    parts = []
    for element in body.get("content", []):
        if "paragraph" in element:
            parts.append(_convert_paragraph(element["paragraph"], lists_dict))
        elif "table" in element:
            parts.append(_convert_table(element["table"]))
        elif "sectionBreak" in element:
            parts.append("\n---\n")

    return "".join(parts).rstrip()


def get_document(service, doc_id):
    """Get a document's raw API response."""
    return service.documents().get(documentId=doc_id).execute()


def get_document_as_markdown(service, doc_id):
    """Get a document and convert its content to markdown."""
    doc = get_document(service, doc_id)
    body = doc.get("body", {})
    lists_dict = doc.get("lists", {})
    markdown_content = _convert_body_to_markdown(body, lists_dict)

    return {
        "document_id": doc.get("documentId"),
        "title": doc.get("title"),
        "markdown_content": markdown_content,
        "revision_id": doc.get("revisionId"),
    }


def create_document(service, title):
    """Create a new Google Docs document."""
    doc = service.documents().create(body={"title": title}).execute()
    doc_id = doc.get("documentId")
    return {
        "document_id": doc_id,
        "title": doc.get("title"),
        "document_link": f"https://docs.google.com/document/d/{doc_id}/edit",
    }


def batch_update(service, doc_id, requests):
    """Execute a batch update on a document."""
    return (
        service.documents()
        .batchUpdate(documentId=doc_id, body={"requests": requests})
        .execute()
    )


def insert_text(service, doc_id, text, index):
    """Insert text at a specific index in the document."""
    requests = [{"insertText": {"location": {"index": index}, "text": text}}]
    return batch_update(service, doc_id, requests)


def append_text(service, doc_id, text):
    """Append text to the end of the document."""
    doc = get_document(service, doc_id)
    body = doc.get("body", {})
    content = body.get("content", [])
    end_index = max(content[-1].get("endIndex", 1) - 1, 1) if content else 1
    return insert_text(service, doc_id, text, end_index)


def replace_all_text(service, doc_id, find, replace, match_case=True):
    """Replace all occurrences of text in the document."""
    requests = [
        {
            "replaceAllText": {
                "containsText": {"text": find, "matchCase": match_case},
                "replaceText": replace,
            }
        }
    ]
    result = batch_update(service, doc_id, requests)
    replies = result.get("replies", [{}])
    occurrences = replies[0].get("replaceAllText", {}).get("occurrencesChanged", 0)
    return {"occurrences_changed": occurrences}


def delete_content_range(service, doc_id, start, end):
    """Delete content in a range."""
    requests = [
        {
            "deleteContentRange": {
                "range": {
                    "startIndex": start,
                    "endIndex": end,
                }
            }
        }
    ]
    return batch_update(service, doc_id, requests)


def update_text_style(
    service,
    doc_id,
    start,
    end,
    bold=None,
    italic=None,
    underline=None,
    strikethrough=None,
    font_size=None,
    font_family=None,
):
    """Update text style for a range."""
    text_style = {}
    fields = []

    if bold is not None:
        text_style["bold"] = bold
        fields.append("bold")
    if italic is not None:
        text_style["italic"] = italic
        fields.append("italic")
    if underline is not None:
        text_style["underline"] = underline
        fields.append("underline")
    if strikethrough is not None:
        text_style["strikethrough"] = strikethrough
        fields.append("strikethrough")
    if font_size is not None:
        text_style["fontSize"] = {"magnitude": font_size, "unit": "PT"}
        fields.append("fontSize")
    if font_family is not None:
        text_style["weightedFontFamily"] = {"fontFamily": font_family}
        fields.append("weightedFontFamily")

    if not fields:
        return {"message": "No style changes specified"}

    requests = [
        {
            "updateTextStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "textStyle": text_style,
                "fields": ",".join(fields),
            }
        }
    ]
    return batch_update(service, doc_id, requests)


def update_paragraph_style(
    service, doc_id, start, end, named_style_type=None, alignment=None
):
    """Update paragraph style for a range."""
    paragraph_style = {}
    fields = []

    if named_style_type is not None:
        paragraph_style["namedStyleType"] = named_style_type
        fields.append("namedStyleType")
    if alignment is not None:
        paragraph_style["alignment"] = alignment
        fields.append("alignment")

    if not fields:
        return {"message": "No style changes specified"}

    requests = [
        {
            "updateParagraphStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "paragraphStyle": paragraph_style,
                "fields": ",".join(fields),
            }
        }
    ]
    return batch_update(service, doc_id, requests)


def insert_table(service, doc_id, rows, columns, index):
    """Insert a table at a specific index."""
    requests = [
        {
            "insertTable": {
                "rows": rows,
                "columns": columns,
                "location": {"index": index},
            }
        }
    ]
    return batch_update(service, doc_id, requests)


def list_documents(
    drive_service, max_results=20, page_token=None, file_name_contains=None
):
    """List Google Docs documents using the Drive API."""
    params = {
        "q": "mimeType='application/vnd.google-apps.document'",
        "pageSize": max_results,
        "fields": "nextPageToken, files(id, name, modifiedTime, createdTime)",
        "supportsAllDrives": True,
        "includeItemsFromAllDrives": True,
    }

    if file_name_contains:
        escaped = file_name_contains.replace("'", "\\'")
        params["q"] += f" and name contains '{escaped}'"

    if page_token:
        params["pageToken"] = page_token

    response = drive_service.files().list(**params).execute()

    return {
        "files": response.get("files", []),
        "nextPageToken": response.get("nextPageToken"),
    }
