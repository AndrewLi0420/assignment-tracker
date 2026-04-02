# TrackerBot

Reads Google Groups / listserv emails from Gmail, extracts assignment events from threaded email conversations, and generates nightly reports.

## What it does

1. Connects to a Gmail inbox via the Gmail API
2. Fetches emails matching a configurable query (e.g. your class listserv address)
3. Strips quoted old thread content so only new text is analyzed
4. Extracts assignment events: new assignments, due dates, extensions, overdue flags
5. Maintains a canonical assignment list with deduplication
6. Generates a nightly report (newly assigned / due soon / overdue)
7. Exposes a REST API for triggering sync and viewing results

---

## Setup

### 1. Python environment

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Gmail API credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or use an existing one)
3. Enable the **Gmail API** under APIs & Services → Library
4. Go to APIs & Services → Credentials → Create Credentials → OAuth client ID
5. Choose **Desktop app** as the application type
6. Download the JSON file and save it as `credentials.json` in the project root
7. On first run, a browser window will open for you to authorize the app
8. After authorization, a `token.json` file is created automatically for future runs

The app only requests `gmail.readonly` scope — it never sends or modifies email.

### 3. Configure `.env`

Copy the example and edit it:

```bash
cp .env.example .env
```

```env
# Gmail search query — match your listserv address
GMAIL_QUERY=to:cs101-staff@lists.school.edu OR from:cs101-staff@lists.school.edu

# Timezone for due date parsing
TIMEZONE=America/Los_Angeles

# Hour (UTC) to run the nightly report
NIGHTLY_REPORT_HOUR=21

# Database file location
DATABASE_URL=sqlite:///./assignments.db

# Gmail OAuth files (defaults to project root)
GMAIL_CREDENTIALS_FILE=credentials.json
GMAIL_TOKEN_FILE=token.json

# Max messages to fetch per sync
MAX_MESSAGES_PER_SYNC=100
```

### 4. Initialize the database

```bash
python scripts/init_db.py
```

---

## Running locally

```bash
uvicorn app.main:app --reload --port 8000
```

The server starts at `http://localhost:8000`.

---

## API endpoints

### `POST /sync`
Fetch new Gmail messages, extract assignments, update canonical state.

```bash
curl -X POST http://localhost:8000/sync
```

Response:
```json
{"new_messages": 12, "new_events": 5, "total_seen": 50}
```

### `GET /assignments`
List all canonical assignments.

```bash
curl http://localhost:8000/assignments
# Filter by status: active, due_soon, overdue, unknown
curl "http://localhost:8000/assignments?status=overdue"
```

### `GET /report/nightly`
Generate and return the current nightly report without waiting for the scheduled run.

```bash
curl http://localhost:8000/report/nightly
```

### `GET /messages`
List recently ingested messages for debugging.

```bash
curl http://localhost:8000/messages
```

### `GET /health`
```bash
curl http://localhost:8000/health
```

---

## Testing the parser

Run the parser smoke test against sample email text (no Gmail connection needed):

```bash
python scripts/test_parser.py
```

---

## How it works

### Quote stripping

Each email body is passed through `clean_new_message_text()` which:
- Removes lines starting with `>`
- Stops at patterns like `On Mon, ... wrote:`, `From:`, `-----Original Message-----`
- Removes signature markers (`--`)

### Extraction

`extract_events()` splits cleaned text into paragraphs and for each one:
- Looks for assignment title patterns (`Homework 7`, `Lab 2`, `Problem Set 4`, etc.)
- Detects event type (`assigned`, `overdue`, `due_date_changed`, etc.) from keywords
- Extracts due dates using `dateparser` with configurable timezone

### Deduplication

Assignments are keyed by `course::normalized_name`. Normalization lowercases, expands `hw → homework`, strips punctuation. Later events override earlier ones for due dates.

### Nightly report

Runs daily at `NIGHTLY_REPORT_HOUR` UTC via APScheduler. Reports are also saved to `reports/` as text files.

---

## Project structure

```
app/
  main.py                 — FastAPI app, lifespan hooks
  config.py               — env-based config
  db.py                   — SQLAlchemy setup
  models.py               — ORM models
  gmail_client.py         — Gmail API auth and message fetching
  parser/
    email_cleaner.py      — quote stripping
    assignment_extractor.py — rule-based event extraction
    normalizer.py         — assignment name normalization
    resolver.py           — merge events into canonical assignments
  services/
    sync_service.py       — orchestrates full sync pipeline
    report_service.py     — generates nightly report text
    scheduler.py          — APScheduler setup
  routes/
    health.py
    sync.py
    assignments.py
    reports.py
  utils/
    dates.py              — dateparser wrapper
    logging.py            — logger factory
scripts/
  init_db.py              — create DB schema
  test_parser.py          — parser smoke test
```
