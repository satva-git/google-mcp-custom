import pytest
from unittest.mock import patch, MagicMock, Mock
from fastmcp import Client
from fastmcp.exceptions import ToolError
from googleapiclient.errors import HttpError

from app.server import mcp


# Fixtures
@pytest.fixture
def mock_service():
    """Create a mock Google Docs service"""
    service = MagicMock()
    return service


@pytest.fixture
def mock_document_data():
    """Sample document data for testing"""
    return {
        "document_id": "test_doc_id_1",
        "title": "Test Document",
        "markdown_content": "# Hello World\n\nThis is a test document.",
        "revision_id": "rev_123",
    }


@pytest.fixture
def mock_create_data():
    """Sample create document response"""
    return {
        "document_id": "new_doc_id",
        "title": "New Document",
        "document_link": "https://docs.google.com/document/d/new_doc_id/edit",
    }


@pytest.fixture
def mock_list_data():
    """Sample list documents response"""
    return {
        "files": [
            {
                "id": "doc_1",
                "name": "Document 1",
                "modifiedTime": "2024-01-01T10:00:00.000Z",
                "createdTime": "2024-01-01T09:00:00.000Z",
            },
            {
                "id": "doc_2",
                "name": "Document 2",
                "modifiedTime": "2024-01-02T10:00:00.000Z",
                "createdTime": "2024-01-02T09:00:00.000Z",
            },
        ],
        "nextPageToken": None,
    }


@pytest.fixture
def mock_batch_update_response():
    """Sample batch update response"""
    return {
        "documentId": "test_doc_id_1",
        "replies": [{}],
    }


# Integration Tests - Testing the MCP Server
class TestMCPServer:
    """Test the FastMCP server integration"""

    async def test_list_tools(self):
        """Test that all tools are properly registered"""
        async with Client(mcp) as client:
            tools = await client.list_tools()

            tool_names = {tool.name for tool in tools}
            expected_tools = {
                "list_documents",
                "get_document",
                "create_document",
                "insert_text",
                "append_text",
                "replace_text",
                "delete_content",
                "format_text",
                "set_paragraph_style",
                "insert_table",
                "batch_update_document",
                "export_document",
            }
            assert expected_tools <= tool_names


# Unit Tests - Testing Individual Functions
class TestDocumentFunctions:
    """Test individual document-related functions"""

    @patch("app.server._get_access_token")
    @patch("app.server.get_client")
    @patch("app.server.list_documents")
    async def test_list_documents_success(
        self,
        mock_list_documents,
        mock_get_client,
        mock_get_access_token,
        mock_service,
        mock_list_data,
    ):
        mock_get_access_token.return_value = "fake_token"
        mock_get_client.return_value = mock_service
        mock_list_documents.return_value = mock_list_data

        async with Client(mcp) as client:
            result = await client.call_tool(
                name="list_documents", arguments={"max_results": 20}
            )
            assert result.structured_content == mock_list_data

        mock_list_documents.assert_called_once_with(
            mock_service,
            max_results=20,
            page_token=None,
            file_name_contains=None,
        )

    @patch("app.server._get_access_token")
    @patch("app.server.get_client")
    @patch("app.server.list_documents")
    async def test_list_documents_with_filters(
        self,
        mock_list_documents,
        mock_get_client,
        mock_get_access_token,
        mock_service,
        mock_list_data,
    ):
        mock_get_access_token.return_value = "fake_token"
        mock_get_client.return_value = mock_service
        mock_list_documents.return_value = mock_list_data

        async with Client(mcp) as client:
            result = await client.call_tool(
                name="list_documents",
                arguments={
                    "max_results": 10,
                    "file_name_contains": "test",
                },
            )
            assert result.structured_content == mock_list_data

        mock_list_documents.assert_called_once_with(
            mock_service,
            max_results=10,
            page_token=None,
            file_name_contains="test",
        )

    @patch("app.server._get_access_token")
    @patch("app.server.get_client")
    @patch("app.server.get_document_as_markdown")
    async def test_get_document_success(
        self,
        mock_get_doc,
        mock_get_client,
        mock_get_access_token,
        mock_service,
        mock_document_data,
    ):
        mock_get_access_token.return_value = "fake_token"
        mock_get_client.return_value = mock_service
        mock_get_doc.return_value = mock_document_data

        async with Client(mcp) as client:
            result = await client.call_tool(
                name="get_document", arguments={"document_id": "test_doc_id_1"}
            )
            assert result.structured_content == mock_document_data

        mock_get_doc.assert_called_once_with(mock_service, "test_doc_id_1")

    @patch("app.server._get_access_token")
    @patch("app.server.get_client")
    @patch("app.server.create_document")
    async def test_create_document_success(
        self,
        mock_create_doc,
        mock_get_client,
        mock_get_access_token,
        mock_service,
        mock_create_data,
    ):
        mock_get_access_token.return_value = "fake_token"
        mock_get_client.return_value = mock_service
        mock_create_doc.return_value = mock_create_data

        async with Client(mcp) as client:
            result = await client.call_tool(
                name="create_document", arguments={"title": "New Document"}
            )
            assert result.structured_content == mock_create_data

        mock_create_doc.assert_called_once_with(mock_service, "New Document")

    @patch("app.server._get_access_token")
    @patch("app.server.get_client")
    @patch("app.server.create_document")
    @patch("app.server.insert_text")
    async def test_create_document_with_content(
        self,
        mock_insert,
        mock_create_doc,
        mock_get_client,
        mock_get_access_token,
        mock_service,
        mock_create_data,
    ):
        mock_get_access_token.return_value = "fake_token"
        mock_get_client.return_value = mock_service
        mock_create_doc.return_value = mock_create_data
        mock_insert.return_value = {"replies": [{}]}

        async with Client(mcp) as client:
            result = await client.call_tool(
                name="create_document",
                arguments={"title": "New Document", "initial_content": "Hello World"},
            )
            assert result.structured_content == mock_create_data

        mock_create_doc.assert_called_once_with(mock_service, "New Document")
        mock_insert.assert_called_once_with(mock_service, "new_doc_id", "Hello World", 1)

    @patch("app.server._get_access_token")
    @patch("app.server.get_client")
    @patch("app.server.insert_text")
    async def test_insert_text_success(
        self,
        mock_insert,
        mock_get_client,
        mock_get_access_token,
        mock_service,
        mock_batch_update_response,
    ):
        mock_get_access_token.return_value = "fake_token"
        mock_get_client.return_value = mock_service
        mock_insert.return_value = mock_batch_update_response

        async with Client(mcp) as client:
            result = await client.call_tool(
                name="insert_text",
                arguments={
                    "document_id": "test_doc_id_1",
                    "text": "Hello",
                    "index": 1,
                },
            )
            assert result.structured_content == mock_batch_update_response

        mock_insert.assert_called_once_with(mock_service, "test_doc_id_1", "Hello", 1)

    @patch("app.server._get_access_token")
    @patch("app.server.get_client")
    @patch("app.server.append_text")
    async def test_append_text_success(
        self,
        mock_append,
        mock_get_client,
        mock_get_access_token,
        mock_service,
        mock_batch_update_response,
    ):
        mock_get_access_token.return_value = "fake_token"
        mock_get_client.return_value = mock_service
        mock_append.return_value = mock_batch_update_response

        async with Client(mcp) as client:
            result = await client.call_tool(
                name="append_text",
                arguments={
                    "document_id": "test_doc_id_1",
                    "text": "Appended text",
                },
            )
            assert result.structured_content == mock_batch_update_response

        mock_append.assert_called_once_with(
            mock_service, "test_doc_id_1", "Appended text"
        )

    @patch("app.server._get_access_token")
    @patch("app.server.get_client")
    @patch("app.server.replace_all_text")
    async def test_replace_text_success(
        self,
        mock_replace,
        mock_get_client,
        mock_get_access_token,
        mock_service,
    ):
        mock_get_access_token.return_value = "fake_token"
        mock_get_client.return_value = mock_service
        mock_replace.return_value = {"occurrences_changed": 3}

        async with Client(mcp) as client:
            result = await client.call_tool(
                name="replace_text",
                arguments={
                    "document_id": "test_doc_id_1",
                    "find_text": "old",
                    "replace_text": "new",
                    "match_case": True,
                },
            )
            assert result.structured_content == {"occurrences_changed": 3}

        mock_replace.assert_called_once_with(
            mock_service, "test_doc_id_1", "old", "new", True
        )

    @patch("app.server._get_access_token")
    @patch("app.server.get_client")
    @patch("app.server.delete_content_range")
    async def test_delete_content_success(
        self,
        mock_delete,
        mock_get_client,
        mock_get_access_token,
        mock_service,
        mock_batch_update_response,
    ):
        mock_get_access_token.return_value = "fake_token"
        mock_get_client.return_value = mock_service
        mock_delete.return_value = mock_batch_update_response

        async with Client(mcp) as client:
            result = await client.call_tool(
                name="delete_content",
                arguments={
                    "document_id": "test_doc_id_1",
                    "start_index": 1,
                    "end_index": 10,
                },
            )
            assert result.structured_content == mock_batch_update_response

        mock_delete.assert_called_once_with(mock_service, "test_doc_id_1", 1, 10)

    @patch("app.server._get_access_token")
    @patch("app.server.get_client")
    @patch("app.server.update_text_style")
    async def test_format_text_success(
        self,
        mock_style,
        mock_get_client,
        mock_get_access_token,
        mock_service,
        mock_batch_update_response,
    ):
        mock_get_access_token.return_value = "fake_token"
        mock_get_client.return_value = mock_service
        mock_style.return_value = mock_batch_update_response

        async with Client(mcp) as client:
            result = await client.call_tool(
                name="format_text",
                arguments={
                    "document_id": "test_doc_id_1",
                    "start_index": 1,
                    "end_index": 10,
                    "bold": True,
                    "italic": True,
                },
            )
            assert result.structured_content == mock_batch_update_response

        mock_style.assert_called_once_with(
            mock_service,
            "test_doc_id_1",
            1,
            10,
            bold=True,
            italic=True,
            underline=None,
            strikethrough=None,
            font_size=None,
            font_family=None,
        )

    @patch("app.server._get_access_token")
    @patch("app.server.get_client")
    @patch("app.server.update_paragraph_style")
    async def test_set_paragraph_style_success(
        self,
        mock_para_style,
        mock_get_client,
        mock_get_access_token,
        mock_service,
        mock_batch_update_response,
    ):
        mock_get_access_token.return_value = "fake_token"
        mock_get_client.return_value = mock_service
        mock_para_style.return_value = mock_batch_update_response

        async with Client(mcp) as client:
            result = await client.call_tool(
                name="set_paragraph_style",
                arguments={
                    "document_id": "test_doc_id_1",
                    "start_index": 1,
                    "end_index": 10,
                    "named_style_type": "HEADING_1",
                    "alignment": "CENTER",
                },
            )
            assert result.structured_content == mock_batch_update_response

        mock_para_style.assert_called_once_with(
            mock_service,
            "test_doc_id_1",
            1,
            10,
            named_style_type="HEADING_1",
            alignment="CENTER",
        )

    @patch("app.server._get_access_token")
    @patch("app.server.get_client")
    @patch("app.server.insert_table")
    async def test_insert_table_success(
        self,
        mock_table,
        mock_get_client,
        mock_get_access_token,
        mock_service,
        mock_batch_update_response,
    ):
        mock_get_access_token.return_value = "fake_token"
        mock_get_client.return_value = mock_service
        mock_table.return_value = mock_batch_update_response

        async with Client(mcp) as client:
            result = await client.call_tool(
                name="insert_table",
                arguments={
                    "document_id": "test_doc_id_1",
                    "rows": 3,
                    "columns": 4,
                    "index": 1,
                },
            )
            assert result.structured_content == mock_batch_update_response

        mock_table.assert_called_once_with(mock_service, "test_doc_id_1", 3, 4, 1)

    @patch("app.server._get_access_token")
    @patch("app.server.get_client")
    @patch("app.server.batch_update")
    async def test_batch_update_document_success(
        self,
        mock_batch,
        mock_get_client,
        mock_get_access_token,
        mock_service,
        mock_batch_update_response,
    ):
        mock_get_access_token.return_value = "fake_token"
        mock_get_client.return_value = mock_service
        mock_batch.return_value = mock_batch_update_response

        requests = [{"insertText": {"location": {"index": 1}, "text": "Hello"}}]

        async with Client(mcp) as client:
            result = await client.call_tool(
                name="batch_update_document",
                arguments={
                    "document_id": "test_doc_id_1",
                    "requests": requests,
                },
            )
            assert result.structured_content == mock_batch_update_response

        mock_batch.assert_called_once_with(mock_service, "test_doc_id_1", requests)

    @patch("app.server._get_access_token")
    @patch("app.server.get_client")
    @patch("app.server.export_document")
    async def test_export_document_as_html(
        self,
        mock_export,
        mock_get_client,
        mock_get_access_token,
        mock_service,
    ):
        mock_get_access_token.return_value = "fake_token"
        mock_get_client.return_value = mock_service
        expected = {
            "document_id": "test_doc_id_1",
            "file_name": "Test Document.html",
            "mime_type": "text/html",
            "export_format": "html",
            "content": "<html><body><p>Hello</p></body></html>",
            "size_bytes": 38,
        }
        mock_export.return_value = expected

        async with Client(mcp) as client:
            result = await client.call_tool(
                name="export_document",
                arguments={
                    "document_id": "test_doc_id_1",
                    "export_format": "html",
                },
            )
            assert result.structured_content == expected

        mock_export.assert_called_once_with(mock_service, "test_doc_id_1", "html")

    @patch("app.server._get_access_token")
    @patch("app.server.get_client")
    @patch("app.server.export_document")
    async def test_export_document_as_pdf(
        self,
        mock_export,
        mock_get_client,
        mock_get_access_token,
        mock_service,
    ):
        mock_get_access_token.return_value = "fake_token"
        mock_get_client.return_value = mock_service
        expected = {
            "document_id": "test_doc_id_1",
            "file_name": "Test Document.pdf",
            "mime_type": "application/pdf",
            "export_format": "pdf",
            "content": "base64encodedcontent",
            "size_bytes": 1024,
        }
        mock_export.return_value = expected

        async with Client(mcp) as client:
            result = await client.call_tool(
                name="export_document",
                arguments={
                    "document_id": "test_doc_id_1",
                    "export_format": "pdf",
                },
            )
            assert result.structured_content == expected

    @patch("app.server._get_access_token")
    @patch("app.server.get_client")
    @patch("app.server.export_document")
    async def test_export_document_default_format(
        self,
        mock_export,
        mock_get_client,
        mock_get_access_token,
        mock_service,
    ):
        mock_get_access_token.return_value = "fake_token"
        mock_get_client.return_value = mock_service
        mock_export.return_value = {"document_id": "test_doc_id_1"}

        async with Client(mcp) as client:
            await client.call_tool(
                name="export_document",
                arguments={"document_id": "test_doc_id_1"},
            )

        mock_export.assert_called_once_with(mock_service, "test_doc_id_1", "html")

    @patch("app.server._get_access_token")
    @patch("app.server.get_client")
    @patch("app.server.export_document")
    async def test_export_document_invalid_format(
        self,
        mock_export,
        mock_get_client,
        mock_get_access_token,
        mock_service,
    ):
        mock_get_access_token.return_value = "fake_token"
        mock_get_client.return_value = mock_service
        mock_export.side_effect = ValueError("Unsupported export format 'bmp'. Supported: html, pdf, docx, txt, rtf, epub")

        async with Client(mcp) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool(
                    name="export_document",
                    arguments={
                        "document_id": "test_doc_id_1",
                        "export_format": "bmp",
                    },
                )
            assert "Unsupported export format" in str(exc_info.value)


class TestContentConversion:
    """Test the markdown conversion functions"""

    def test_convert_heading(self):
        from app.apis.documents import _convert_paragraph

        paragraph = {
            "paragraphStyle": {"namedStyleType": "HEADING_1"},
            "elements": [
                {"textRun": {"content": "Hello World\n", "textStyle": {}}}
            ],
        }
        result = _convert_paragraph(paragraph, {})
        assert result == "# Hello World\n"

    def test_convert_heading_2(self):
        from app.apis.documents import _convert_paragraph

        paragraph = {
            "paragraphStyle": {"namedStyleType": "HEADING_2"},
            "elements": [
                {"textRun": {"content": "Subtitle\n", "textStyle": {}}}
            ],
        }
        result = _convert_paragraph(paragraph, {})
        assert result == "## Subtitle\n"

    def test_convert_bold_text(self):
        from app.apis.documents import _convert_text_run

        text_run = {"content": "bold text", "textStyle": {"bold": True}}
        result = _convert_text_run(text_run)
        assert result == "**bold text**"

    def test_convert_italic_text(self):
        from app.apis.documents import _convert_text_run

        text_run = {"content": "italic text", "textStyle": {"italic": True}}
        result = _convert_text_run(text_run)
        assert result == "*italic text*"

    def test_convert_strikethrough_text(self):
        from app.apis.documents import _convert_text_run

        text_run = {"content": "deleted", "textStyle": {"strikethrough": True}}
        result = _convert_text_run(text_run)
        assert result == "~~deleted~~"

    def test_convert_link(self):
        from app.apis.documents import _convert_text_run

        text_run = {
            "content": "click here",
            "textStyle": {"link": {"url": "https://example.com"}},
        }
        result = _convert_text_run(text_run)
        assert result == "[click here](https://example.com)"

    def test_convert_bold_italic(self):
        from app.apis.documents import _convert_text_run

        text_run = {
            "content": "bold italic",
            "textStyle": {"bold": True, "italic": True},
        }
        result = _convert_text_run(text_run)
        assert result == "***bold italic***"

    def test_convert_table(self):
        from app.apis.documents import _convert_table

        table = {
            "tableRows": [
                {
                    "tableCells": [
                        {
                            "content": [
                                {
                                    "paragraph": {
                                        "elements": [
                                            {
                                                "textRun": {
                                                    "content": "Header 1",
                                                    "textStyle": {},
                                                }
                                            }
                                        ]
                                    }
                                }
                            ]
                        },
                        {
                            "content": [
                                {
                                    "paragraph": {
                                        "elements": [
                                            {
                                                "textRun": {
                                                    "content": "Header 2",
                                                    "textStyle": {},
                                                }
                                            }
                                        ]
                                    }
                                }
                            ]
                        },
                    ]
                },
                {
                    "tableCells": [
                        {
                            "content": [
                                {
                                    "paragraph": {
                                        "elements": [
                                            {
                                                "textRun": {
                                                    "content": "Cell 1",
                                                    "textStyle": {},
                                                }
                                            }
                                        ]
                                    }
                                }
                            ]
                        },
                        {
                            "content": [
                                {
                                    "paragraph": {
                                        "elements": [
                                            {
                                                "textRun": {
                                                    "content": "Cell 2",
                                                    "textStyle": {},
                                                }
                                            }
                                        ]
                                    }
                                }
                            ]
                        },
                    ]
                },
            ]
        }
        result = _convert_table(table)
        assert "| Header 1 | Header 2 |" in result
        assert "| --- | --- |" in result
        assert "| Cell 1 | Cell 2 |" in result

    def test_convert_unordered_list(self):
        from app.apis.documents import _convert_paragraph

        lists_dict = {
            "list_1": {
                "listProperties": {
                    "nestingLevels": [{"glyphType": "GLYPH_TYPE_UNSPECIFIED"}]
                }
            }
        }
        paragraph = {
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
            "bullet": {"listId": "list_1", "nestingLevel": 0},
            "elements": [
                {"textRun": {"content": "Item 1\n", "textStyle": {}}}
            ],
        }
        result = _convert_paragraph(paragraph, lists_dict)
        assert result == "- Item 1\n"

    def test_convert_ordered_list(self):
        from app.apis.documents import _convert_paragraph

        lists_dict = {
            "list_1": {
                "listProperties": {
                    "nestingLevels": [{"glyphType": "DECIMAL"}]
                }
            }
        }
        paragraph = {
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
            "bullet": {"listId": "list_1", "nestingLevel": 0},
            "elements": [
                {"textRun": {"content": "Step 1\n", "textStyle": {}}}
            ],
        }
        result = _convert_paragraph(paragraph, lists_dict)
        assert result == "1. Step 1\n"

    def test_convert_empty_paragraph(self):
        from app.apis.documents import _convert_paragraph

        paragraph = {
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
            "elements": [{"textRun": {"content": "\n", "textStyle": {}}}],
        }
        result = _convert_paragraph(paragraph, {})
        assert result == "\n"

    def test_convert_body_to_markdown(self):
        from app.apis.documents import _convert_body_to_markdown

        body = {
            "content": [
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "HEADING_1"},
                        "elements": [
                            {"textRun": {"content": "Title\n", "textStyle": {}}}
                        ],
                    }
                },
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        "elements": [
                            {"textRun": {"content": "Some text\n", "textStyle": {}}}
                        ],
                    }
                },
            ]
        }
        result = _convert_body_to_markdown(body, {})
        assert "# Title" in result
        assert "Some text" in result


class TestErrorHandling:
    """Test error handling scenarios"""

    @patch("app.server._get_access_token")
    @patch("app.server.get_client")
    @patch("app.server.get_document_as_markdown")
    async def test_http_error_handling(
        self, mock_get_doc, mock_get_client, mock_get_access_token, mock_service
    ):
        mock_get_access_token.return_value = "fake_token"
        mock_get_client.return_value = mock_service
        mock_resp = Mock()
        mock_resp.status = 403
        mock_get_doc.side_effect = HttpError(
            resp=mock_resp, content=b'{"error": {"message": "Forbidden"}}'
        )

        async with Client(mcp) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool(
                    name="get_document",
                    arguments={"document_id": "test_doc_id"},
                )
            assert "HttpError" in str(exc_info.value)

    @patch("app.server._get_access_token")
    @patch("app.server.get_client")
    @patch("app.server.get_document_as_markdown")
    async def test_generic_error_handling(
        self, mock_get_doc, mock_get_client, mock_get_access_token, mock_service
    ):
        mock_get_access_token.return_value = "fake_token"
        mock_get_client.return_value = mock_service
        mock_get_doc.side_effect = Exception("Generic error")

        async with Client(mcp) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool(
                    name="get_document",
                    arguments={"document_id": "test_doc_id"},
                )
            assert "Unexpected ToolError" in str(exc_info.value)

    @patch("app.server._get_access_token")
    @patch("app.server.get_client")
    @patch("app.server.list_documents")
    async def test_list_documents_http_error(
        self, mock_list, mock_get_client, mock_get_access_token, mock_service
    ):
        mock_get_access_token.return_value = "fake_token"
        mock_get_client.return_value = mock_service
        mock_resp = Mock()
        mock_resp.status = 500
        mock_list.side_effect = HttpError(
            resp=mock_resp, content=b'{"error": {"message": "Server Error"}}'
        )

        async with Client(mcp) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool(
                    name="list_documents", arguments={}
                )
            assert "HttpError" in str(exc_info.value)
