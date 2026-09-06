# SmartContract Manager – Roadmap & Epic-Tracking

Dieses Dokument dokumentiert die Projekt-Meilensteine, aktiven Epics und den Entwicklungsfortschritt über den gesamten Lebenszyklus der Anwendung. Es entkoppelt das operative Projektmanagement und Issue-Tracking von den Verhaltensrichtlinien und Architekturregeln in `.agents/AGENTS.md`.

---

## Statusübersicht

| Epic | Bezeichnung | Status | Fortschritt |
| :--- | :--- | :---: | :--- |
| **Epic 1** | Basisinfrastruktur & Authentifizierung | **Abgeschlossen** | 100% (Docker, SQLAlchemy, Session-Auth, Alembic Baseline-Migrationen) |
| **Epic 2** | CRUD-Operationen (Kern) | **Abgeschlossen** | 100% (Verträge, Vertragspartner, Inline-Tag-Picker, Preisüberlappungs-Korrektur, dynamische Fälligkeitsberechnung) |
| **Epic 3** | Finanz-Dashboard & Berechnungs-Engine | **Abgeschlossen** | 100% (CurrencyService mit 24h-DB-Cache, 100% TDD-Abdeckung, Cashflow 12M, Option A Budget-Umschalter, Chart.js Dual-Theme) |
| **Epic 4** | Vertragslebenszyklus & Verlängerungs-Engine | **Abgeschlossen** | 100% (Erweiterte Status, Mindestlaufzeiten, BGB § 309 Nr. 9 rollierende Verlängerung, exakte Fristenberechnung) |
| **Mini-Epic 4.1** | Template-Dekomposition & Modal-Modularisierung | **Abgeschlossen** | 100% (Auslagerung der Modals aus contract_detail in Komponenten, konsolidiertes Vertrags-Modal) |
| **Mini-Epic 4.2** | Vertragspartner-Finanzanalysen & Cashflow | **Geplant (Als Nächstes)** | 0% (Ist-Zahlungen letzte 12M + Prognose nächste 12M im gestapelten Diagramm, KPI-Übersicht) |
| **Epic 5** | Kündigungs-Assistent & Generator | **Geplant** | 0% (E-Mail-Maske mit 1-Klick-Kopieren, strikt KEINE `mailto:`-Links, DIN 5008 PDF-Kündigungsschreiben) |
| **Epic 6** | Backup- & Restore-System | **Geplant** | 0% (Persistenter Docker-Mount `./backup`, AES-256 Archivverschlüsselung, Web-UI Download/Upload, Cron-Picker wie `docker-archiver`) |
| **Epic 7** | OIDC-Integration (OpenID Connect via Authlib) | **Geplant** | 0% (Externe Identity Provider, Single Sign-On, `oidc_sub`-Zuordnung) |
| **Epic 8** | Interaktiver Kalender & Webcal-Synchronisation | **Geplant** | 0% (In-App Monatsgitter- & Agendaliste, Dashboard-Mini-Agenda mit Fristen-Warnhierarchie, dynamischer RFC 5545 Feed, Token-Auth) |
| **Epic 9** | Datenportabilität & Berichte | **Geplant** | 0% (CSV-Massenimport mit Validierung, CSV-Export, formatierte PDF-Finanzberichte) |
| **Epic 10** | Dokumententresor & Speicherverschlüsselung | **Geplant** | 0% (PDF-Anhänge an Verträgen, AES-256 Encryption-at-Rest, geschützte Auslieferung) |
| **Epic 11** | OCR-Pipeline & Volltextsuche | **Optional / Zurückgestellt** | 0% (Asynchroner OCR-Worker mit Tesseract/OCRmyPDF, Volltextsuche in Dokumenten) |

---

## Detaillierte Epics & Meilensteine

### Epic 1: Basisinfrastruktur & Authentifizierung
*Ziel: Etablierung einer sicheren Basisinfrastruktur mit Containerisierung, relationaler Datenbank, versionierten Migrationen und Session-Authentifizierung.*

- [x] Docker-Infrastruktur (`docker-compose.yml`, `Dockerfile`) für PostgreSQL 15 und Flask-Webservice.
- [x] SQLAlchemy-ORM-Einrichtung (`app/models.py`, `app/__init__.py`).
- [x] Klassische Session-Authentifizierung (Registrierung, Login, Logout mit Flask-Login und Passwort-Hashing).
- [x] Alembic-Initialisierung für versionierte Datenbankmigrationen (`alembic.ini`, `migrations/`).
- [x] Initiale Baseline-Migration (`0001_initial_schema.py`) für das Datenbankschema.
- [x] Automatische Ausführung von `alembic upgrade head` beim Start des Docker-Webcontainers.
- [x] Integrationstest-Suite für den Alembic-Migrationszyklus (`tests/test_migrations.py`).

### Epic 2: CRUD-Operationen (Kern)
*Ziel: Vollständige Verwaltung von Vertragspartnern, Verträgen, Tags und Preishistorien.*

- [x] Verwaltung von `Provider`-Entitäten mit Kontaktdaten, Kundennummern, Kundenportalen, Kündigungs-URLs sowie Bearbeiten- und Löschaktionen.
- [x] Dedizierte Vertragspartner-Detailansicht (`/providers/<id>`) mit Bündelung aller Verträge, Stammdaten und Mehrwährungs-Gesamtkostenzusammenfassungen.
- [x] Verwaltung von `Contract`-Entitäten inklusive Zahlungsrhythmen, Kategorien, Kündigungsfristen, Suche, Status- und Tag-Filtern.
- [x] Wiederverwendbare Vertragserstellungs-Komponente (`_contract_modal.html`) mit Vorauswahl des Partners und Weiterleitung (`?next=`).
- [x] Dynamische Berechnung des nächsten Abrechnungsdatums (`contract.next_billing_date`) mit Monatsarithmetik, Enddatums-Logik und Status-Indikatoren (`contracts.due_today`, `contracts.due_in_days`).
- [x] Tagging-System (`Tag`) mit m:n-Vertragsbeziehung (`contract_tags`), deterministischer Farbzuordnung und voll integriertem Inline-Autocomplete-Dropdown (Select2/TomSelect-Stil mit Tastaturnavigation).
- [x] Preishistorie (`PriceEntry`) mit Gültigkeitszeiträumen (`valid_from`, `valid_to`, `is_current`), Kollisionserkennung und intelligenter automatischer Anpassung.
- [x] Geplante & künftige Preisstufen: Dynamischer Status (`future`, `current`, `past`), Ankündigungs-Banner, Fälligkeitsbetrags-Transparenz, sicheres Löschen mit Wiederherstellung der Zeiträume und 12-Monats-Vorschau.
- [x] Interaktiver Preisverlauf (Chart.js Stepped-Line-Chart) in den Vertragsdetails mit KPI-Zusammenfassung, gestrichelten Zukunftslinien und Dark/Light-Mode-Unterstützung.
- [x] UI/UX-Harmonisierung: Ausgewogenes 2-Spalten-Vertragscockpit, responsive Tabellenansicht mit Vertragsnummern, zentrierte Filter-Buttons und kontextbezogene Leerzustände (Empty States).
- [x] Vollständige Testabdeckung mit 72 erfolgreichen Unit- und Integrationstests (`tests/test_contract.py`, `tests/test_provider.py`, `tests/test_contract_future_prices.py`).

### Epic 3: Finanz-Dashboard & Berechnungs-Engine (Testgetrieben via pytest)
*Ziel: Deterministische Cashflow-Projektionen und monatliche Budget-Normalisierung mit automatisierter Währungsumrechnung.*

- [x] **Währungsdienst (`CurrencyService`):** Automatisierter Wechselkursabruf (Frankfurter API) mit 24-stündigem Datenbank-Caching in `ExchangeRateCache` und Ausfallschutz.
- [x] **TDD-Unit-Tests:** Pytest-Suite mit 100% Branch-/Logikabdeckung für Cashflow, Budget-Normalisierung und Randfälle (Schaltjahre, Monatsend-Pinning, Preiswechsel).
- [x] **Cashflow-Modus:** 12-monatige rollierende Vorschau tatsächlicher Zahlungszeitpunkte basierend auf `billing_anchor_date` und Zahlungsintervall (Balkendiagramm via Chart.js mit Theme-Unterstützung).
- [x] **Budget-Modus (Option A):** Interaktiver Umschalter zwischen normalisiertem Monatsmittelwert (Ø), tatsächlichen Ausgaben des aktuellen Monats und Jahresbudget mit Kategorieverteilungs-Diagramm (Doughnut Chart).

### Epic 4: Vertragslebenszyklus & Verlängerungs-Engine
*Ziel: Abbildung realer Vertragslebenszyklen mit Mindestlaufzeiten, gesetzlicher BGB-Verlängerungsmechanik und differenzierten Statusübergängen.*

- [x] Erweiterte `ContractStatus`-Enumeration: `active`, `pending_cancellation` (Kündigung eingereicht), `cancellation_confirmed` (Kündigung bestätigt), `paused` (ruhend), `canceled` (beendet) und `archived`.
- [x] Schema-Erweiterungen an `Contract`: `initial_term_months` (Mindestvertragslaufzeit), `renewal_period_months`, `renewal_type` (`monthly_rolling` nach § 309 Nr. 9 BGB vs. `fixed_period` vs. `none`), `cancellation_sent_date` und `confirmed_end_date`.
- [x] Schema-Erweiterungen an `User`: optionale Felder `full_name` und `address` für automatisierte Absenderangaben in Kündigungsschreiben.
- [x] Verlängerungs- und Kündigungs-Engine:
  - Exakte mathematische Extrapolation von `current_cycle_end_date` und `earliest_cancellation_date`.
  - Nahtlose Einhaltung des deutschen Verbraucherschutzrechts (automatische monatlich rollierende Verlängerung mit max. 1 Monat Frist nach Ablauf der Mindestlaufzeit).
  - Dynamische Fristenindikatoren (`cancellation_deadline`, `days_until_cancellation_deadline`, visuelle Warn-Badges).
- [x] Alembic-Datenbankmigration `0004_contract_lifecycle_rollover.py`.
- [x] Vertrags-UI: Status-Badges in Listen- und Detailansichten, Filter-Tabs für eingereichte/ruhende Verträge und Aktionen für Statusübergänge.
- [x] Entkoppelte Archivierung (`is_archived: bool`) mit Sicherheitsnetz (Archivierung ausschließlich für beendete Verträge mit `status == canceled`). Alembic-Migration `0005_contract_is_archived.py`.
- [x] Vertragstitel (`title`) entkoppelt von der Budgetkategorie (`category`), mit Inline-`<datalist>`-Vervollständigung und Neuanlage für Kategorien und Zahlungsarten.
- [x] Dedizierte Notizen-Historie (`Note`-Modell) mit chronologischem Verlauf, Zeitstempeln und Löschoptionen für Verträge und Vertragspartner.
- [x] Automatische Tag-Bereinigung (`prune_orphaned_tags`), die verwaiste Tags ohne referenzierende Verträge automatisch entfernt.
- [x] Geplante Verträge (`scheduled`-Status) für Vorverträge, saubere Monatsbudget-Isolation und automatische Aktivierung am `start_date`. Alembic-Migration `0006_title_notes_scheduled.py`.
- [x] Terminologie-Harmonisierung: Deutsche Benutzeroberfläche nutzt durchgehend „Vertragspartner“ statt „Provider“.
- [x] Vollständige TDD-Testsuite mit 89 erfolgreichen Unit- und Integrationstests (`tests/test_contract.py`, `tests/test_contract_lifecycle.py`, `tests/test_notes.py`).

### Mini-Epic 4.1: Template-Dekomposition & Modal-Modularisierung
*Ziel: Refactoring monolithischer Templates (insbesondere `contract_detail.html` mit über 1500 Zeilen und dupliziertem Modal-Code in `dashboard.html`) in modulare Jinja2-Komponenten unter `app/templates/components/`.*

- [x] Modularisierung der Modals aus `contract_detail.html` in wiederverwendbare Teil-Templates:
  - `_contract_edit_modal.html`: Auslagerung von `#editContractModal` (3-Sektionen-Aufbau, Abrechnungsanker, Live-Vorschau).
  - `_contract_extend_modal.html`: Auslagerung von `#extendContractModal` (Vertragsverlängerung / VVL-Workflow).
  - `_contract_price_modal.html`: Auslagerung von `#addPriceModal` und Preisanpassungs-Modals.
  - `_contract_status_modals.html`: Auslagerung von `#confirmCancellationModal` und `#deleteContractModal`.
- [x] Konsolidierung der Vertragserstellung: Ersetzung des Inline-Modals in `dashboard.html` durch die geteilte Komponente `_contract_modal.html`.
- [x] 100% Kompatibilität aller Selektoren, IDs und Events für Frontend-Skripte (`contract-term.js`, `combobox.js`, `tag-picker.js`).
- [x] Verifikation der Testsuite und Sicherstellung sauberer Darstellung ohne DOM- oder Layout-Regressionen.

### Mini-Epic 4.2: Vertragspartner-Finanzanalysen & Historischer/Zukünftiger Cashflow
*Ziel: Umfassende Finanzanalysen auf `provider_detail.html` zur visuellen Cashflow-Transparenz (historische Zahlungen + Zukunftsprognose) für Vertragspartner mit einzelnen oder mehreren Verträgen.*

- [ ] **Finanz-Engine (`FinancialService`):**
  - Implementierung von `get_provider_cashflow(user_id, provider_id, past_months=12, future_months=12)` zur Berechnung monatlicher Ist-Zahlungen der letzten 12 Monate und Prognosen der nächsten 12 Monate.
  - Multi-Vertrags-Aufschlüsselung: Stapelung von Ausgaben nach Vertrag bei Partnern mit mehreren Verträgen (z. B. DSL + Mobilfunk bei Vodafone).
- [ ] **Interaktive visuelle Analysen (`provider_detail.html`):**
  - Gestapeltes Balkendiagramm (Chart.js) mit vergangenen Zahlungen und Zukunftsprognosen mit visueller Trennung der Zeitachsen.
  - Vertragspartner-KPI-Karten: Gesamtausgaben über die Vertragslaufzeit, monatlicher Durchschnitt (historisch vs. prognostiziert), Gesamtsumme der festen Bindung der nächsten 12 Monate.
  - Vollständige Bootstrap 5.3 Dark/Light-Theme-Unterstützung abgestimmt auf das Dashboard-Designsystem.
- [ ] **Lokalisierung & TDD-Qualitätsprüfung:**
  - Übersetzungsschlüssel in `app/locales/de.json` und `app/locales/en.json`.
  - Umfassende Unit-Tests in `tests/test_financial_service.py` und Integrationstests in `tests/test_provider.py`.

### Epic 5: Kündigungs-Assistent & Generator
*Ziel: Bereitstellung eines benutzerfreundlichen, rechtssicheren Kündigungsassistenten mit 1-Klick kopierbarer E-Mail-Korrespondenz und herunterladbaren DIN 5008 PDF-Schreiben.*

- [ ] Interaktives Kündigungs-Modal in den Vertragsdetails (`contract_detail.html`):
  - **E-Mail Kündigungsmaske (Strikt KEINE `mailto:`-Links):**
    - Empfängerfeld vorausgefüllt mit `provider.email` + 1-Klick-Button zum Kopieren in die Zwischenablage.
    - Betreffzeile vorausgefüllt mit Vertragsnummer, Kundennummer und Nutzername + 1-Klick-Kopierbutton.
    - Vorformatierter rechtssicherer Kündigungstext (mit Vertragsdaten, Kündigungsdatum, Aufforderung zur schriftlichen Bestätigung innerhalb von 14 Tagen und Widerruf der SEPA-Einzugsermächtigung zum Vertragsende) + 1-Klick-Kopierbutton.
    - Visuelles Feedback nach dem Kopieren (Bootstrap Tooltip / Badge „Kopiert!“).
    - 1-Klick-Aktion zum Setzen des Vertragsstatus auf `pending_cancellation` mit Prüfdatum.
  - **Formeller PDF-Brief (Download):**
    - DIN 5008-konformes formelles Kündigungsschreiben generiert via **ReportLab 5.0.1**.
    - Absenderfenster, Empfängerfenster, Datumszeile, hervorgehobene Betreffzeile, Kündigungstext und Unterschriftsfeld.
    - Geschützter Download-Endpunkt `/contracts/<id>/cancellation/pdf`.
- [ ] Integrationstest-Suite für PDF-Generierung, Sicherheitsprüfungen und Clipboard-Hilfsfunktionen.

### Epic 6: Backup- & Restore-System (mit AES-Verschlüsselung)
*Ziel: Bereitstellung produktionsreifer, verschlüsselter Sicherungs- und Wiederherstellungsfunktionen für Notfallwiederherstellung und unkomplizierten Serverumzug.*

- [ ] Persistenter Host-Volume Bind-Mount `./backup:/app/backup` in `docker-compose.yml`.
- [ ] Dedizierte Backup- & Restore-Verwaltung in den Einstellungen/Admin-Bereich.
- [ ] Konfigurationsoptionen:
  - Automatischer Sicherungszeitplan (`aktiviert` / `deaktiviert`).
  - Aufbewahrungsrichtlinie (automatisches Löschen von Sicherungen älter als die letzten *N* Backups).
  - **Zeitplan-Konfigurator (Cron-Picker im Stil von `docker-archiver`):**
    - Direktes Eingabefeld für Cron-Ausdrücke (`schedule_cron`, z. B. `0 3 * * *`).
    - Schnellwahl-Buttons: `Täglich 03:00 Uhr` (`0 3 * * *`), `Wöchentlich Sonntag` (`0 0 * * 0`), `Monatlich 1.` (`0 0 1 * *`) etc.
    - Live-Countdown bis zur nächsten Ausführung (`data-next-run`).
- [ ] **AES-256 Backup-Verschlüsselung:**
  - Passwort-/Schlüsselbasierte AES-256-Archivverschlüsselung (`.tar.gz.enc`) zum Schutz der Daten auf externen Speichern (NAS, Nextcloud, S3).
  - Passwortabfrage bei Wiederherstellung zur authentifizierten Entschlüsselung.
- [ ] **Web-UI Dateiübertragung & Aktionen:**
  - 1-Klick Web-UI Download bestehender Backup-Archive auf den lokalen Rechner.
  - Web-UI Drag-and-Drop / Datei-Upload von Backup-Archiven auf Neuinstallationen.
  - 1-Klick manuelle Erstellung eines Sofort-Backups.
  - 1-Klick Wiederherstellung mit Sicherheits-Bestätigungsdialog.

### Epic 7: OIDC-Integration (OpenID Connect via Authlib)
*Ziel: Ermöglichung von externem Single Sign-On (SSO) und föderierter Authentifizierung.*

- [ ] Integration des `Authlib` OAuth/OIDC-Clients in die Flask-Anwendung.
- [ ] Erweiterung des `User`-Datenmodells: Attribut `oidc_sub` (String, eindeutig, indexiert) und Unterstützung für optionale Passwörter (`hashed_password` nullable=True).
- [ ] Konfiguration über Standard-Umgebungsvariablen (`OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_DISCOVERY_URL`).
- [ ] Authentifizierungs-Endpunkte für `/auth/oidc/login` und `/auth/oidc/callback`.
- [ ] Automatische Benutzererstellung und Identitätszuordnung anhand von `oidc_sub`.
- [ ] TDD-Integrationstest-Suite für OIDC-Abläufe mit gemockten Authorization-Server-Antworten.

### Epic 8: Interaktiver Kalender & Webcal-Synchronisation (RFC 5545)
*Ziel: Bereitstellung eines interaktiven In-App-Kalenders mit Dual-View-Modus (Monatsgitter & chronologische Agendaliste), eines erweiterten Dashboard-Mini-Agenda-Widgets mit Fristen-Warnhierarchie sowie eines dynamischen, token-geschützten Webcal-Abonnement-Feeds für Google Kalender, Apple Kalender und Outlook.*

- [ ] **Dashboard Mini-Agenda & Fristen-Warnhierarchie:**
  - Ausbau der bisherigen statischen Dashboard-Erinnerungen zu einem dynamischen **Mini-Agenda-Widget** mit den nächsten 3–5 chronologisch anstehenden Terminen (nächste 30–60 Tage).
  - **Strikte Zwei-Zonen-Warnhierarchie:**
    - **Zone A (Alarm & Handlungsbedarf - Rote/Gelbe Badges):**
      - Reguläre **Kündigungsfristen** (`cancellation_deadline = term_end - notice_period`) zur Vermeidung ungewollter automatischer Verlängerungen (z. B. `[ ⚠️ Kündigungsfrist in 5 Tagen ]`).
      - Gesetzliche **Sonderkündigungsrechte** ausgelöst durch einseitige Preiserhöhungen (z. B. § 41 EnWG, § 40 VVG, § 57 TKG), die rasches Handeln vor dem Stichtag erfordern (z. B. `[ ⚠️ Sonderkündigung bis 31.10. ]`).
    - **Zone B (Informative & präventive Stichtage - Cyan/Blau/Orange):**
      - Mindestlaufzeit-Meilensteine, reguläre Vertragsenden und Folge-Rollierungsphasen (z. B. `[ Mindestlaufzeit erfüllt ]`).
      - **Kostenfallen-Frühwarnung:** Vorwarnung 30–60 Tage vor Ablauf vereinbarter Rabattphasen bzw. geplanter Preissprünge (z. B. `[ 🟠 Preissprung auf 44,99 € in 30 T. – Jetzt verhandeln/kündigen ]`).
  - Direkter Footer-Link: `[ 📅 Alle Termine im Kalender anzeigen → ]` mit Absprung in die `/calendar`-Vollansicht.
- [ ] **Interaktive In-App Kalenderansicht (`/calendar`):**
  - Responsiver Umschalter zwischen **Monatsgitter** (klassisches 7-Spalten-Raster) und **Agendaliste** (chronologische Liste mit Datums-Gruppierung, Vertragsdetails und Schnellaktionen) mit `localStorage`-Persistenz.
  - Automatische, mobiloptimierte Agenda-Darstellung auf Smartphones (`d-md-none`).
  - Farbcodierte Event-Kategorisierung: Kündigungsfristen & Sonderkündigung (rotes Alarmsignal mit Warn-Icon), Preissprünge (orange Warnung), Mindestlaufzeit-Enden / Verlängerungen (cyan) und Abrechnungs-Fälligkeiten (grün).
  - Schnellfilter-Leiste: *Alle Termine*, *Kündigungsfristen & Sonderkündigung*, *Laufzeiten & Verlängerungen*, *Zahlungsfälligkeiten*.
  - Direkter Absprung ins Vertragsdetail (`/contracts/<id>`).
- [ ] **Zentrale Kalender-Engine (`CalendarService`):**
  - Einheitliche Terminextrapolations-Pipeline (`get_events_for_range`) für Dashboard-Widget, Web-UI-JSON und `.ics`-Export (Single Source of Truth).
  - Mathematisch saubere Trennung zwischen handlungsrelevanten Kündigungsstichtagen (`term_end - notice_period`), gesetzlichen Sonderkündigungsfenstern und Vertragsbeendigungsdaten (`term_end`).
- [ ] **Konfigurierbarer dynamischer Webcal- / iCalendar-Feed (RFC 5545):**
  - Dynamischer `.ics`-Feed-Endpunkt (`/calendar/feed/<token>.ics`) mit `text/calendar`-MIME-Type und Standard-Headern.
  - Formatierte Terminzusammenfassungen mit klaren Präfixen (z. B. `[Kündigungsfrist]`, `[Sonderkündigung]`, `[Preissprung]`, `[Zahlung]`).
  - Konfigurierbare Feed-Parameter (z. B. `?payments=0` oder `?payments=1` zur optionalen Ein- oder Ausblendung wiederkehrender Zahlungsfälligkeiten).
- [ ] **Kryptografische Feed-Sicherheit & Widerruf:**
  - 256-Bit kryptografisch sichere Feed-Tokens (`secrets.token_urlsafe(32)`).
  - SHA-256 Token-Hashing in der Datenbank (`User.calendar_token_hash`).
  - Constant-Time-Prüfung (`hmac.compare_digest`) und Rate-Limiting gegen Brute-Force- und DoS-Angriffe.
  - 1-Klick Token-Widerruf und Neugenerierung in der UI.
- [ ] **„Kalender abonnieren“-Modal & Plattform-Integration:**
  - 1-Klick kopierbare HTTPS-Feed-URL und nativer `webcal://`-Start-Button für iOS, macOS und Windows.
  - Schritt-für-Schritt Einrichtungsanleitungen für Google Kalender (Web/Android), Apple Kalender (iOS/macOS) und Microsoft Outlook (Web/Desktop).
- [ ] Umfassende TDD-Testsuite für RFC 5545-Konformität, Token-Generierung/Hashing, Bereichsberechnung, Sonderkündigungs-Trigger und Synchronisationsfilter.

### Epic 9: Datenportabilität & Berichte
*Ziel: Unterstützung des tabellarischen Datenaustauschs und formatierter PDF-Finanzberichte.*

- [ ] Meilenstein 1: CSV-Massenimport mit Spalten-Mapping, Zeichencodierungs-Erkennung und zeilenweiser Validierungspipeline.
- [ ] Meilenstein 2: Tabellarischer CSV/Excel-Export von Verträgen und vollständigen Preishistorien.
- [ ] Meilenstein 3: Formatierter PDF-Budgetbericht (Jahres- und Monatsausgaben nach Kategorie).

### Epic 10: Dokumententresor & Speicherverschlüsselung
*Ziel: Schlanke, sichere PDF-Vertragsablage mit AES-256-Verschlüsselung im Ruhezustand (Encryption-at-Rest).*

- [ ] Dokumentenverwaltung direkt verknüpft mit `Contract`-Entitäten (`contract.documents`).
- [ ] **AES-256 Verschlüsselung im Ruhezustand:**
  - Verschlüsselung der PDF-Bytes via `cryptography.fernet` vor dem Schreiben auf das Dateisystem (`stored_filename`).
  - Dateisystem speichert ausschließlich verschlüsselte Chiffretext-Blobs.
  - On-the-fly-Entschlüsselung im RAM bei autorisiertem Download über `/documents/download/<id>`.
- [ ] Strikte serverseitige Sicherheitsrichtlinien (5 MB Upload-Limit, `secure_filename`, MIME-Validierung `application/pdf`).
- [ ] UI im Vertragsdetail: Liste angehängter Dokumente, PDF-Upload, geschützter Download, Dokumentenlöschung.

### Epic 11: OCR-Pipeline & Volltextsuche (Optional / Zurückgestellt)
*Ziel: Asynchrone Textextraktion und Volltextsuche über eingescannte Vertragsdokumente.*

- [ ] Asynchroner OCR-Hintergrund-Worker (`ocrmypdf` / `pytesseract`) zur Textindizierung in `Document.extracted_text`.
- [ ] Erweiterung der globalen Suche zur Recherche innerhalb von Vertragsdokumenten.

---

## Backlog & Zukünftige Ideen
*Funktionen, die für spätere Evaluierung vorgemerkt sind:*

- **Haushalts-Kostenaufteilung (Fair-Share):** Mehrbenutzer-Haushaltsansicht, Aufteilung gemeinsamer Verträge (z. B. 50/50 Miete, Internet) und Verrechnung von Partner-Salden.
- **Abo-Optimierung & Kostenfallen-Erkennung:** Automatische Erkennung bevorstehender Preissprünge, doppelter Dienste (z. B. zwei parallele Musik-Streaming-Abos) und ungenutzter Abonnements.
