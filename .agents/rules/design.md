# UI/UX & Design Guidelines: SmartContract Manager

## 1. Core Paradigm & Philosophy
* **Framework:** Bootstrap 5.3 (native Server-Side Rendering with Jinja2).
* **Zero Custom CSS Rule:** Custom CSS rules are strictly forbidden unless Bootstrap provides no utility class or variable for the exact requirement. Use native Bootstrap utility classes (`d-flex`, `gap-3`, `text-muted`, `p-3`, `rounded-3`, `shadow-sm`, etc.).
* **Mobile-First Responsive Layout:** All views must be developed mobile-first using the Bootstrap 12-column grid system (`col-12 col-md-6 col-lg-4`). Tabular data must be wrapped in `.table-responsive` to prevent horizontal clipping on mobile viewports.
* **Independent Row Pattern (Whitespace Hole Prevention):** Never mix dynamic list widgets of variable vertical height (such as deadline reminders, agenda lists, or notification items) with tall fixed-height widgets (such as charts) within the same Bootstrap `.row`. Doing so forces the row to stretch to the tallest widget, creating massive vertical whitespace voids underneath short lists. Instead, isolate them into dedicated full-width rows (`col-12` or `col-md-6 + col-md-6`) that expand or collapse organically with their content, allowing subsequent content rows to follow naturally in the vertical document flow.

## 2. Theming & Color Modes (Dark / Light)
* **Native Switching:** The application relies strictly on Bootstrap 5.3 native color modes using the HTML attribute `data-bs-theme="dark"` or `data-bs-theme="light"` on the root `<html>` element.
* **Theme Persistence:** Theme selection must be stored in `localStorage` and optionally synced to user settings.
* **CSS Custom Properties:** Utilize Bootstrap's semantic variables (`var(--bs-body-bg)`, `var(--bs-body-color)`, `var(--bs-border-color)`, `var(--bs-card-bg)`) rather than hardcoding hex codes.

## 3. UI Components Standards
* **Contracts & Providers Display:**
  * Render primary entities using Bootstrap `.card` components with subtle shadows (`.shadow-sm`) and distinct headers/footers for metadata and quick actions.
* **Status Indicators & Tags:**
  * Use Bootstrap `.badge` elements for status and category tags:
    * Active contract: `bg-success`
    * Canceled contract: `bg-warning text-dark`
    * Archived contract: `bg-secondary`
    * Category tags: Semantic badges with subtle contrast.
* **Financial Highlights & KPI Stat Cards:**
  * Key financial indicators (monthly costs, upcoming payments, total spend) must be presented in KPI stat cards with clear typography (`fs-4`, `fw-bold`, `text-primary` or `text-success`).
  * **Typography & Truncation Rule:** Primary titles and descriptive secondary labels in KPI stat cards must **never** use `.text-truncate`. Compound words and descriptive phrases (especially in German localization) exceed narrow column widths; cutting them off impairs usability. Instead, use `.min-w-0` on the flex container and allow a clean 2-line wrap with `.lh-sm` (or `line-height: 1.25`).
  * **Symmetrical Row Stretching:** All KPI cards within a row must use the `.h-100` utility class within the flex column to ensure identical heights across the row even when one card's label wraps onto multiple lines. Vertical content centering must be preserved with `d-flex align-items-center`.
  * **Control Decoupling Principle:** Segmented button groups, toggles, and timeframe filters (e.g., Monthly Average vs. Current Month vs. Annual Total) must **never** be crammed inside individual KPI stat cards. Place them in the overarching card/section header or a dedicated filter toolbar. Stat tiles remain clean, focused display units.

## 4. Chart.js Visualization Standards (Epic 3)
* **Dual-Theme Legibility:** Charts must be fully legible in both dark and light modes.
* **Colors & Palettes:**
  * Avoid raw primary colors. Use harmonious, balanced color sets:
    * Income / Cash Surplus: `#198754` (success green)
    * Expenses / Outflows: `#dc3545` (danger red)
    * Neutral / Projections: `#0d6efd` (primary blue) / `#6f42c1` (purple)
  * Grid lines and label colors must read dynamically from the active theme (e.g. `rgba(255, 255, 255, 0.15)` in dark mode and `rgba(0, 0, 0, 0.1)` in light mode).
* **Responsiveness & Aspect Ratio Containers:** All Chart.js instances must have `responsive: true` and `maintainAspectRatio: false` within fixed-height aspect ratio containers (`.chart-container`).
* **Chart Pairing Standard:** When placing charts side-by-side in a multi-column row (e.g. 12-month Cashflow projection in `col-8` and Category Cost Doughnut in `col-4`), both charts must reside inside `.chart-container` wrappers with identical fixed heights (e.g. `height: 280px`). This ensures pixel-perfect top and bottom alignment with zero vertical voids.

## 5. Forms & Validation UX
* **Structure:** Forms must use clear semantic markup with `<label class="form-label">` or Bootstrap Floating Labels (`.form-floating`).
* **CSRF Protection:** Every POST form must include `{{ form.hidden_tag() }}`.
* **Server-Side Validation Feedback:**
  * When a form field fails validation, apply the `.is-invalid` class to the input element and render the error message immediately below using `.invalid-feedback`.
  * Flash messages and general error notifications must use dismissible Bootstrap alerts (`.alert.alert-<category>.alert-dismissible.fade.show`).

## 6. Iconography
* **Standard:** Standardize exclusively on **Bootstrap Icons** (`bi bi-<name>`).
* **Consistency:**
  * Dashboard: `bi-speedometer2`
  * Contracts: `bi-file-earmark-text`
  * Providers: `bi-building`
  * Settings: `bi-gear`
  * Actions: `bi-pencil` (edit), `bi-trash` (delete), `bi-plus-lg` (add/create), `bi-download` (export/download).
