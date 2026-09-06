# Testing Guidelines: SmartContract Manager

## 1. Core Paradigm & Libraries
- **Test-Driven Development (TDD):** Write tests before or alongside implementation.
- **Framework:** Use `pytest` for all testing.
- **Execution Environment (Critical):** All test runs must strictly occur inside the Docker container (`web` service), as dependencies are containerized:
  ```bash
  docker compose exec web pytest
  # or for specific test files:
  docker compose exec web pytest tests/test_auth.py
  ```
  Never execute `pytest` directly on the host machine.
- **Mandatory Libraries:**
  - `pytest-mock`: Strictly required for mocking all external dependencies to ensure tests run isolated without network or file I/O (e.g., mocking the Frankfurter API in Epic 3, or file system interactions during PDF uploads in Epic 4).
  - `factory_boy`: Strictly required for generating test data and fixtures. Due to the highly relational SQLAlchemy data model (`User -> Provider -> Contract -> PriceEntry`), this prevents boilerplate code and ensures consistent model states across tests.
  - `pytest-cov`: Required to measure test coverage.

## 2. Coverage Goals
- **Financial Algorithms:** A strict **100% logic/branch coverage** is mandatory for all financial math algorithms (Cashflow and Budget calculations in Epic 3).
- **Backend Logic:** Maintain a high baseline coverage (e.g., >85%) for the rest of the backend application.

## 3. Directory Structure & Naming
- Tests must reside in the `tests/` directory at the project root.
- Segregate tests logically: `tests/unit/`, `tests/integration/`, `tests/e2e/`.
- Test files must be prefixed with `test_` (e.g., `test_models.py`, `test_dashboard.py`).
- Test function names must be highly descriptive regarding the tested scenario (e.g., `def test_calculate_cashflow_with_leap_year()`).

## 4. Database Setup (`conftest.py`)
- **Strict PostgreSQL Requirement:** An in-memory SQLite database is strictly forbidden for testing. Due to the critical requirement of storing all timestamps in UTC and utilizing datetime functions (like `billing_anchor_date`), SQLite's lack of native datetime types and dialect incompatibilities produce false positives.
- **Implementation:** Use a dedicated PostgreSQL test database (e.g., `smartcontract_test` within the existing `docker-compose.yml` Postgres image) or use Testcontainers.
- **State Management:** The tables must be built before every test run via SQLAlchemy `metadata.create_all()` and either dropped afterwards or rolled back using transaction rollbacks to guarantee a pristine state.

## 5. Specific Epic Testing Requirements
- **Epic 3 (Financial Dashboard & Logic):**
  - Rigorous unit tests covering edge cases like leap years, irregular intervals (e.g., quarterly payments starting mid-year), and currency conversions.
- **Epic 4 (Document Management):**
  - File uploads and OCR processing must be completely mocked out regarding disk I/O.
