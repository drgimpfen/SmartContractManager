# SmartContract Manager

A web application for centralized management of personal contracts, cancellation deadlines, and fixed expenses.

## Features

- User management with classic login
- Contract management with category, status, duration, payment, and tags
- Provider management with contact and link data
- Dashboard with cashflow and budget overview
- PDF upload for contract documents and OCR-based text extraction
- Dark/Light mode and responsive Bootstrap UI
- PostgreSQL database in Docker

## Getting Started

1. Optionally copy `.env.example` to `.env` and adjust settings.
2. Start the application with Docker Compose:

```bash
docker compose up --build
```

3. Open `http://localhost:8000` in the browser.

## Local development

1. Create a Python virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the server:

```bash
uvicorn app.main:app --reload
```

## Structure

- `app/main.py` – FastAPI application and routing
- `app/db.py` – SQLAlchemy configuration
- `app/models.py` – data model
- `app/routes/` – application routes
- `app/templates/` – Jinja2 templates
- `app/static/` – CSS/JS and upload directory
