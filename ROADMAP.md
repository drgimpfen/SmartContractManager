# SmartContract Manager – Roadmap & Epic Tracking

This document tracks project milestones, active epics, and progress across the application life cycle. It decouples operational project management and issue tracking from the behavioral guidelines and architecture rules in `.agents/AGENTS.md`.

---

## Status Overview

| Epic | Name | Status | Progress |
| :--- | :--- | :---: | :--- |
| **Epic 1** | Basic Infrastructure & Core Auth | **Completed** | 100% (Docker, SQLAlchemy, Classic Auth, Alembic Baseline Migrations) |
| **Epic 2** | CRUD Operations (Core) | **Completed** | 100% (Contracts, Providers, Inline Tag Dropdown, Price Overlap Auto-Adjust, Dynamic Next Billing Calculation) |
| **Epic 3** | Financial Dashboard & Calculations | **Completed** | 100% (CurrencyService with 24h DB cache, TDD 100% coverage, Cashflow 12M, Option A Budget Toggles, Chart.js dual-theme) |
| **Epic 4** | Contract Lifecycle & Rollover Engine | **Completed** | 100% (Extended statuses, minimum contract terms, BGB § 309 Nr. 9 rolling renewals, exact deadline math) |
| **Mini-Epic 4.1** | Template Decomposition & Modal Modularization | **Planned (Next)** | 0% (Extract 1500+ LOC modals from contract_detail into components, eliminate duplicates) |
| **Mini-Epic 4.2** | Provider Multi-Contract Analytics & Cashflow | **Planned** | 0% (Past 12M actuals + Next 12M forecast stacked chart, KPI summary for providers) |
| **Epic 5** | Cancellation Assistant & Generator | **Planned** | 0% (E-Mail mask with 1-click copy, strictly NO `mailto:`, DIN 5008 formal PDF letter download) |
| **Epic 6** | Backup & Restore System | **Planned** | 0% (Persistent Docker `./backup` mount, AES-256 backup encryption, Web UI Download/Upload, On-Demand & Cron Picker like `docker-archiver`) |
| **Epic 7** | Data Portability & Reporting | **Planned** | 0% (CSV contract bulk import with validation, CSV data export, formatted PDF financial reports) |
| **Epic 8** | OIDC Integration (OpenID Connect via Authlib) | **Planned** | 0% (External SSO identity providers, `oidc_sub` mapping) |
| **Epic 9** | Document Vault & Storage Encryption | **Planned** | 0% (Lightweight PDF attachments linked to contracts, AES-256 Encryption-at-Rest, authenticated delivery) |
| **Epic 10** | OCR Pipeline & Full-Text Search | **Optional / Postponed** | 0% (Background OCR text extraction via Tesseract/OCRmyPDF, full-text contract search) |

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
- [x] Dedicated Provider Details view (`/providers/<id>`) aggregating all associated contracts, master contact data, and multi-currency lifetime/remaining cost summaries.
- [x] Management of `Contract` entities including payment rhythms, categories, notice periods, search, status filtering, and tag filtering.
- [x] Reusable contract creation modal component (`_contract_modal.html`) supporting direct opening with preselected provider and seamless redirects (`?next=`).
- [x] Dynamic next billing date calculation (`contract.next_billing_date`) with month arithmetic, end date handling, and smart due date status indicators (`contracts.due_today`, `contracts.due_in_days`).
- [x] Tagging system (`Tag`) with many-to-many contract association (`contract_tags`), deterministic color assignment, and 100% inline autocomplete dropdown tag picker (Select2/TomSelect style with keyboard navigation).
- [x] Price history tracking (`PriceEntry`) maintaining validity ranges (`valid_from`, `valid_to`, `is_current`), overlap collision detection, and smart auto-adjustment.
- [x] Scheduled & future price management: Dynamic status (`future`, `current`, `past`), scheduled announcement banners, next billing due amount clarity, safe deletion with range restoration, and 12-month forward annual projection.
- [x] Interactive price timeline chart (Chart.js stepped line chart) in contract details with KPI summary strip, dashed future segments, and dark/light mode responsiveness.
- [x] UI/UX harmonization: Balanced 2-column contract cockpit, responsive table layout with provider contract numbers, clean typography, centered filter buttons, and context-aware empty states.
- [x] Full test coverage with 72 passing unit and integration tests (`tests/test_contract.py`, `tests/test_provider.py`, `tests/test_contract_future_prices.py`).

### Epic 3: Financial Dashboard & Calculations (Test-Driven via pytest)
*Objective: Deterministic cash flow projections and monthly budget normalization with automated currency conversion.*

- [x] **Currency Service (`CurrencyService`):** Automated exchange rate retrieval (Frankfurter API) with 24-hour database caching in `ExchangeRateCache` and resilient fallback.
- [x] **TDD Unit Tests:** Pytest test suite with 100% branch/logic coverage covering cash flow, budget normalization, edge cases (leap years, month-end pinning, price changes).
- [x] **Cash Flow Mode:** 12-month forward projection of actual payment dates derived from `billing_anchor_date` and payment frequency (bar chart via Chart.js with theme awareness).
- [x] **Budget Mode (Option A):** Interactive client-side switcher between normalized monthly average (Ø), actual current month expenses, and annual total budget with category distribution doughnut chart.

### Epic 4: Contract Lifecycle & Rollover Engine
*Objective: Model real-world contract lifecycles with minimum commitment periods, statutory German BGB rollover mechanics, and fine-grained status transitions.*

- [x] Extended `ContractStatus` enumeration supporting `active`, `pending_cancellation` (Kündigung eingereicht), `cancellation_confirmed` (Kündigung bestätigt), `paused` (ruhend), `canceled` (beendet), and `archived`.
- [x] Schema enhancements on `Contract`: `initial_term_months` (Mindestvertragslaufzeit), `renewal_period_months`, `renewal_type` (`monthly_rolling` per § 309 Nr. 9 BGB vs. `fixed_period` vs. `none`), `cancellation_sent_date`, and `confirmed_end_date`.
- [x] Schema enhancements on `User`: optional `full_name` and `address` fields for automatic sender population in cancellation correspondence.
- [x] Rollover & termination engine:
  - Exact mathematical extrapolation of `current_cycle_end_date` and `earliest_cancellation_date`.
  - Seamless handling of German consumer protection law (automatic monthly rolling extensions with max 1-month notice after initial minimum term).
  - Dynamic cancellation deadline indicators (`cancellation_deadline`, `days_until_cancellation_deadline`, warning badges).
- [x] Alembic database migration `0004_contract_lifecycle_rollover.py`.
- [x] Contract UI updates: Status badges in list and detail views, filter tabs for pending/paused contracts, and lifecycle status transition controls.
- [x] Decoupled archiving action (`is_archived: bool`) with failsafe (archive allowed strictly only for terminated contracts `status == canceled`). Alembic migration `0005_contract_is_archived.py`.
- [x] Contract Title (`title`) decoupled from budget category (`category`), with inline `<datalist>` autocomplete and creation for categories and payment methods.
- [x] Dedicated Notes Timeline (`Note` model) with chronological history, timestamping, and deletion controls for both Contracts and Providers.
- [x] Automatic Tag Garbage Collection (`prune_orphaned_tags`) automatically removing tags with zero referencing contracts.
- [x] Scheduled contracts (`scheduled` status) for future contracts, clean current month budget isolation, and automated activation on `start_date`. Alembic migration `0006_title_notes_scheduled.py`.
- [x] UI terminology harmonized: German UI uses "Vertragspartner" instead of "Provider".
- [x] Full TDD test suite with 89 passing unit and integration tests across contracts, lifecycle, financial projections, and notes (`tests/test_contract.py`, `tests/test_contract_lifecycle.py`, `tests/test_notes.py`).

### Mini-Epic 4.1: Template Decomposition & Modal Component Modularization
*Objective: Refactor monolithic templates (specifically `contract_detail.html` with 1500+ lines and duplicate modal code in `dashboard.html`) into modular, encapsulated Jinja2 component templates in `app/templates/components/`.*

- [ ] Modularize `contract_detail.html` modals into reusable partials:
  - `_contract_edit_modal.html`: Extract `#editContractModal` (3-section structure, billing anchor, live-calculation preview).
  - `_contract_extend_modal.html`: Extract `#extendContractModal` (contract extension / VVL workflow).
  - `_contract_price_modal.html`: Extract `#addPriceModal` and price change modals.
  - `_contract_status_modals.html`: Extract `#confirmCancellationModal` and `#deleteContractModal`.
- [ ] Consolidate contract creation modals: Replace inline modal in `dashboard.html` with the shared component `_contract_modal.html`.
- [ ] Maintain 100% selector, ID, and event compatibility for frontend scripts (`contract-term.js`, `combobox.js`, `tag-picker.js`).
- [ ] Verify test suite and ensure clean template rendering without DOM or layout regressions.

### Mini-Epic 4.2: Provider Financial Analytics & Historical/Future Cashflow
*Objective: Introduce comprehensive financial analytics on `provider_detail.html`, providing visual cashflow transparency (historical payments + forward projection) for providers with single or multiple contracts.*

- [ ] **Financial Engine (`FinancialService`):**
  - Implement `get_provider_cashflow(user_id, provider_id, past_months=12, future_months=12)` calculating monthly actuals over the past 12 months and projections over the next 12 months.
  - Multi-contract breakdown: Stack expenses per contract for multi-contract providers (e.g. DSL + Mobile under Vodafone).
- [ ] **Interactive Visual Analytics (`provider_detail.html`):**
  - Stacked bar chart (Chart.js) showing past actual payments vs. future projections with clear timeline separation.
  - Provider KPI cards: Total lifetime spend, monthly average (historical vs. projected), total next 12-month commitment.
  - Full Bootstrap 5.3 dark/light theme awareness matching the dashboard cashflow design system.
- [ ] **Localization & TDD Quality Gate:**
  - Translation keys in `app/locales/de.json` and `app/locales/en.json`.
  - Comprehensive unit tests in `tests/test_financial_service.py` and integration tests in `tests/test_provider.py`.

### Epic 5: Cancellation Assistant & Generator
*Objective: Provide a user-friendly, legally compliant cancellation assistant with one-click copyable email correspondence and downloadable formal DIN 5008 PDF letters.*

- [ ] Interactive Cancellation Assistant modal in contract details (`contract_detail.html`):
  - **E-Mail Kündigungsmaske (Strictly NO `mailto:` links):**
    - Recipient field prefilled with `provider.email` + 1-click copy to clipboard button.
    - Subject line prefilled with contract number, customer number, and user name + 1-click copy button.
    - Preformatted legal body text (with contract number, customer number, earliest termination date, request for written confirmation within 14 days, and SEPA direct debit revocation upon contract end) + 1-click copy button.
    - Visual copy confirmation feedback (Bootstrap tooltip / badge "Kopiert!").
    - 1-Click action button to mark contract as `pending_cancellation` with audit date.
  - **Formeller PDF-Brief (Download):**
    - Clean DIN 5008-compliant formal cancellation letter generated using **ReportLab 5.0.1**.
    - Sender address window, recipient window, date line, bold subject line, legal cancellation body text, and physical signature space.
    - Authenticated download endpoint `/contracts/<id>/cancellation/pdf`.
- [ ] Integration test suite for PDF generation, security checks, and clipboard UI helper functions.

### Epic 6: Backup & Restore System (mit AES-Verschlüsselung)
*Objective: Provide production-grade, encrypted backup and restore capabilities for disaster recovery and effortless instance relocation.*

- [ ] Persistent host volume bind mount `./backup:/app/backup` in `docker-compose.yml`.
- [ ] Dedicated Backup & Restore management view in settings/admin section.
- [ ] Configuration options:
  - Automated backup schedule toggle (`enabled` / `disabled`).
  - Retention count policy (automatically prune snapshots older than the last *N* backups).
  - **Schedule Configurator (Cron Picker im Stil von `docker-archiver`):**
    - Direct cron expression input field (`schedule_cron`, e.g. `0 3 * * *`).
    - Quick-preset button group: `Täglich 03:00 Uhr` (`0 3 * * *`), `Wöchentlich Sonntag` (`0 0 * * 0`), `Monatlich 1.` (`0 0 1 * *`), etc.
    - Next execution countdown display (`data-next-run` with live relative timer).
- [ ] **AES-256 Backup Encryption:**
  - Password-/Key-based AES-256 archive encryption (`.tar.gz.enc`) protecting data on external clouds (NAS, Nextcloud, S3).
  - Password prompt upon restoration for authenticated decryption.
- [ ] **Web UI File Transfer & Operations:**
  - One-click Web UI download of existing backup archives to client computer.
  - Web UI drag-and-drop / file upload of backup archives onto new/fresh instances.
  - One-click on-demand manual backup creation.
  - One-click restore execution with safety confirmation prompt.

### Epic 7: Data Portability & Reporting
*Objective: Support tabular data exchange and formatted financial PDF reports.*

- [ ] Milestone 1: CSV bulk onboarding import with column mapping, encoding detection, and row-by-row validation pipeline.
- [ ] Milestone 2: Tabular CSV/Excel export of contracts and full price histories.
- [ ] Milestone 3: Formatted PDF budget report (annual and monthly expenditure summaries by category).

### Epic 8: OIDC Integration (OpenID Connect via Authlib)
*Objective: Enable external Single Sign-On (SSO) and federated authentication.*

- [ ] Integration of `Authlib` OAuth/OIDC client within the Flask application.
- [ ] Extension of `User` data model: `oidc_sub` attribute (String, unique, indexed) and optional password support (`hashed_password` nullable=True).
- [ ] Configuration via standard environment variables (`OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_DISCOVERY_URL`).
- [ ] Authentication endpoints for `/auth/oidc/login` and `/auth/oidc/callback`.
- [ ] Automatic user provisioning and identity mapping based on `oidc_sub`.
- [ ] TDD integration test suite for OIDC flows with mocked authorization server responses.

### Epic 9: Document Vault & Storage Encryption
*Objective: Lightweight, secure PDF contract storage with AES-256 encryption-at-rest.*

- [ ] Document management directly linked to `Contract` entities (`contract.documents`).
- [ ] **AES-256 Encryption-at-Rest:**
  - Encryption of raw PDF bytes via `cryptography.fernet` before writing to storage volume (`stored_filename`).
  - Storage on disk consists strictly of encrypted ciphertext blobs.
  - On-the-fly decryption in RAM upon authenticated request via `/documents/download/<id>`.
- [ ] Strict server-side security policies (5 MB upload limit, `secure_filename`, MIME verification `application/pdf`).
- [ ] Contract detail UI section: List attached documents, upload new PDF, secure download, delete attachment.

### Epic 10: OCR Pipeline & Full-Text Search (Optional / Postponed)
*Objective: Background text extraction and full-text search indexing across scanned contract documents.*

- [ ] Background OCR worker pipeline (`ocrmypdf` / `pytesseract`) indexing text into `Document.extracted_text`.
- [ ] Global search extension for searching within contract document contents.

---

## Backlog & Future Exploration
*Features deferred for future consideration:*

- **Household Cost Splitting (Fair-Share):** Multi-user household views, splitting shared contracts (e.g. 50/50 rent, internet) and calculating partner balances.
- **Subscription Insights & Trap Warnings:** Automatic detection of impending price jumps, duplicate services (e.g. two music streaming plans), and unused subscriptions.
