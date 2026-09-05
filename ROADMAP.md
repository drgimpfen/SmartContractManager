# SmartContract Manager – Roadmap & Epic Tracking

This document tracks project milestones, active epics, and progress across the application life cycle. It decouples operational project management and issue tracking from the behavioral guidelines and architecture rules in `.agents/AGENTS.md`.

---

## Status Overview

| Epic | Name | Status | Progress |
| :--- | :--- | :---: | :--- |
| **Epic 1** | Basic Infrastructure & Core Auth | **Completed** | 100% (Docker, SQLAlchemy, Classic Auth, Alembic Baseline Migrations) |
| **Epic 2** | CRUD Operations (Core) | **Completed** | 100% (Contracts, Providers, Inline Tag Dropdown, Price Overlap Auto-Adjust, Dynamic Next Billing Calculation) |
| **Epic 3** | Financial Dashboard & Calculations | **Planned** | 0% (TDD specifications ready) |
| **Epic 4** | Document Management & OCR | **Planned** | 0% |
| **Epic 5** | Export & Import | **Planned** | 0% |
| **Epic 6** | OIDC Integration (OpenID Connect via Authlib) | **Planned** | 0% (Extracted from Epic 1 into dedicated epic) |

---

## Detailed Epics & Milestones

### Epic 1: Basic Infrastructure & Core Auth
*Objective: Establish secure foundational infrastructure with containerization, relational database layer, version-controlled migrations, and session authentication.*

- [x] Docker infrastructure (`docker-compose.yml`, `Dockerfile`) for PostgreSQL 15 and Flask web service.
- [x] SQLAlchemy ORM setup (`app/models.py`, `app/__init__.py`).
- [x] Classic session authentication (registration, login, logout with Flask-Login and password hashing).
- [x] Alembic initialization for version-controlled migrations (`alembic.ini`, `migrations/`).
- [x] Initial baseline migration (`0001_initial_schema.py`) reflecting the complete database schema.
- [x] Automatic execution of `alembic upgrade head` in the Docker web container on startup.
- [x] Integration test suite for Alembic migration life cycle (`tests/test_migrations.py`).

### Epic 2: CRUD Operations (Core)
*Objective: Full management of providers, contracts, tags, and price histories.*

- [x] Management of `Provider` entities with contact information, customer numbers, customer portals, cancellation URLs, edit, and delete actions.
- [x] Management of `Contract` entities including payment rhythms, categories, notice periods, search, status filtering, and tag filtering.
- [x] Dynamic next billing date calculation (`contract.next_billing_date`) with month arithmetic, end date handling, and smart due date status indicators (`contracts.due_today`, `contracts.due_in_days`).
- [x] Tagging system (`Tag`) with many-to-many contract association (`contract_tags`), deterministic color assignment, and 100% inline autocomplete dropdown tag picker (Select2/TomSelect style with keyboard navigation).
- [x] Price history tracking (`PriceEntry`) maintaining validity ranges (`valid_from`, `valid_to`, `is_current`), overlap collision detection, and smart auto-adjustment.
- [x] UI/UX harmonization: Balanced 2-column contract cockpit, responsive table layout with provider contract numbers, clean typography, centered filter buttons, and context-aware empty states.
- [x] Full test coverage with 28 passing unit and integration tests (`tests/test_contract.py`, `tests/test_provider.py`).

### Epic 3: Financial Dashboard & Calculations (Test-Driven via pytest)
*Objective: Deterministic cash flow projections and monthly budget normalization with automated currency conversion.*

- [ ] **Currency Service (`CurrencyService`):** Automated exchange rate retrieval (e.g. Frankfurter API) with 24-hour database caching in `ExchangeRateCache`.
- [ ] **TDD Unit Tests:** Pytest test suite covering cash flow and budget algorithms prior to UI integration.
- [ ] **Cash Flow Mode:** 12-month forward projection of actual payment dates derived from `billing_anchor_date` and payment frequency (bar chart via Chart.js).
- [ ] **Budget Mode:** Normalized monthly cost distribution grouped by category (pie chart via Chart.js).

### Epic 4: Document Vault & OCR Pipeline
*Objective: Secure PDF contract storage with server-side validation and automated text extraction.*

- [ ] Upload endpoint enforcing strict security policies (5 MB payload cap, `secure_filename`, MIME type verification `application/pdf`).
- [ ] Persistent storage within Docker volumes and association with `Document` records.
- [ ] Authenticated document delivery route (`/documents/download/<id>`) preventing unauthenticated access.
- [ ] Asynchronous/background OCR pipeline (`ocrmypdf`/`pytesseract`) indexing searchable text into `extracted_text`.

### Epic 5: Data Portability
*Objective: Support data migration, bulk onboarding, and formatted exports.*

- [ ] CSV bulk import for contract creation with strict schema validation.
- [ ] Formatted PDF budget report export (rendering HTML templates or ReportLab to PDF).

### Epic 6: OIDC Integration (OpenID Connect via Authlib)
*Objective: Enable external Single Sign-On (SSO) and federated authentication.*

- [ ] Integration of `Authlib` OAuth/OIDC client within the Flask application.
- [ ] Extension of `User` data model: `oidc_sub` attribute (String, unique, indexed) and optional password support (`hashed_password` nullable=True).
- [ ] Configuration via standard environment variables (`OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_DISCOVERY_URL`).
- [ ] Authentication endpoints for `/auth/oidc/login` and `/auth/oidc/callback`.
- [ ] Automatic user provisioning and identity mapping based on `oidc_sub`.
- [ ] TDD integration test suite for OIDC flows with mocked authorization server responses.
