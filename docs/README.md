# Google Docs MCP Server

An MCP (Model Context Protocol) server for interacting with Google Docs. Provides tools for creating, reading, and editing Google Docs documents.

## Features

- **List Documents** — List Google Docs in the user's Drive with filtering and pagination
- **Get Document** — Retrieve document content as markdown for easy LLM consumption
- **Create Document** — Create new documents with optional initial content
- **Insert / Append Text** — Add text at a specific position or at the end
- **Replace Text** — Find and replace text across the entire document
- **Delete Content** — Remove content in a specified range
- **Format Text** — Apply bold, italic, underline, strikethrough, font size, and font family
- **Set Paragraph Style** — Apply heading styles and alignment
- **Insert Table** — Add tables at a specific position
- **Batch Update** — Execute raw Google Docs API batch update requests

## Setup

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- Google Cloud project with Docs API and Drive API enabled
- OAuth 2.0 credentials

### Install Dependencies

```bash
uv sync
```

### Run the Server

```bash
uv run python -m app.server
```

The server starts on port 9000 by default. Configure with the `PORT` environment variable.

### Run with Docker

```bash
docker compose up --build
```

## API Scopes Required

- `https://www.googleapis.com/auth/documents` — Full access to Google Docs
- `https://www.googleapis.com/auth/drive.readonly` — Read-only access to Drive (for listing documents)

## Running Tests

```bash
uv run pytest
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PORT` | `9000` | Server port |
| `MCP_PATH` | `/mcp/google-docs` | MCP endpoint path |
