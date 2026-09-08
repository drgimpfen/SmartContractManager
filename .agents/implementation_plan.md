# 2-Phasen-Plan: Wechselkurs-Modal (UI) & Historische Kalenderjahr-Engine mit Zukunftskurs-Sperre (Backend/DB)

Dieser Plan vereint die Neugestaltung der Wechselkurs-Präsentation im Dashboard zu einem schlanken Modal (Phase 1) mit der finanzmathematisch exakten historischen Stichtagsumrechnung über vollständige Kalenderjahr-Chunks, der Bereinigung bestehender Geister-Zukunftsdaten und einer dauerhaften ORM-Zukunftskurs-Sperre (Phase 2).

---

## 🤖 Modell-Tier-Empfehlung & Komplexitätsbewertung
* **Empfohlenes Modell-Tier**:
  * **Phase 1 (UI-Refactoring)**: `Low` (Fast / Lightweight)
  * **Phase 2 (Backend-Engine & DB-Bereinigung)**: `High` (Flagship / High-Reasoning)
* **Begründung**: Phase 1 umfasst rein isolierte UI- und Bootstrap 5.3 Anpassungen im Dashboard-Template, während Phase 2 mathematisch sensible Finanzkalkulationen, ORM-Validierungen und API-Chunking betrifft.

---

## 🔍 Anti-Redundanz & Deduplizierungs-Audit
* **Bestehende Abstraktionen (DRY / Single Source of Truth):**
  * **Phase 1 (UI):** Verwendet die bestehende Route-Variable `active_exchange_rates` aus `CurrencyService.get_active_rates_for_user` und bindet das Modal über standardisierte Bootstrap 5.3 Attribute ein.
  * **Phase 2 (Backend/DB):** Vergangene Kalenderjahre ($Jahr < Aktuelles Jahr$) werden als vollständiges Kalenderjahr (`YYYY-01-01` bis `YYYY-12-31`) in einem einzigen Request geholt (*Write Once, Read Forever*). Alle Verträge einer Währung teilen sich denselben Cache (100 % Trefferquote).
  * Zukunftsabfragen werden direkt am Eingang von `CurrencyService.get_rate` auf den heutigen Tag geklemmt (`if as_of and as_of > today: as_of = today`), während `ExchangeRateCache` per `@validates('rate_date')` das Persistieren von Zukunftsdaten auf DB-Ebene strikt verbietet.
* **Visuelle Deduplizierung (UI Anti-Redundancy Mandate):**
  * Der 100 % breite Kartenbalken am Seitenende des Dashboards (`#foreignCurrencyRatesCard`) wird ersatzlos entfernt; das Dashboard schließt sauber nach den Diagrammen ab.
  * Der Auslöser für das Modal sitzt exklusiv an einer einzigen Stelle: als dezent-informative Pill-Schaltfläche im Dashboard-Header neben dem Zeitraum-Umschalter.
  * Bei Nutzern ohne Fremdwährungen wird der Button gar nicht gerendert (0 Pixel Platzverschwendung).
* **Disjunkte Phasenabgrenzung:**
  * **Phase 1** ändert ausschließlich das Dashboard-Template (`dashboard.html`), die Lokalisierung (`de.json`, `en.json`) und `tests/test_dashboard.py`.
  * **Phase 2** ändert ausschließlich die Berechnungslogik (`financial_service.py`), den Währungsdienst (`currency_service.py`), das Datenmodell (`models.py`), das Vertragsdetail-Template (`contract_detail.html`) und die Backend-Tests.

---

## ⚠️ User Review Required
> [!IMPORTANT]
> **Phase 1 – UI-Verhalten des Pill-Buttons im Dashboard-Header:**
> * Bei **einer** aktiven Fremdwährung (Standardfall): Zeigt direkt den Kurs: `[ 💱 1 USD = 0.8606 EUR ]` (Information im Augenwinkel ohne Klick).
> * Bei **mehreren** aktiven Fremdwährungen: Zeigt kompakt: `[ 💱 2 Wechselkurse ]`.
> * Klick öffnet das neue `#exchangeRatesModal` mit allen Kursen, EZB-Datum, Quelle und Transparenz-Hinweis.
>
> **Phase 2 – Kalenderjahr-Chunks & Zukunftskurs-Verbot:**
> * Für vergangene Jahre (z. B. 2022 bis 2025) wird immer das **vollständige Kalenderjahr (`01.01. bis 31.12.`)** in einem einzigen API-Call (~0,1 s) geholt und dauerhaft gespeichert (*Write Once, Read Forever*).
> * Für das **laufende Kalenderjahr** (2026) wird strikt nur vom **`01.01. bis heute`** abgerufen.
> * Für Zukunftstermine ($d > \text{heute}$) wird ausnahmslos der heutige Spot-Kurs angewendet; Zukunftsabfragen an die API und Zukunfts-DB-Einträge sind strikt verboten.
> * 12 bestehende Geister-Einträge der Zukunft werden per SQL aus `exchange_rate_cache` gelöscht.

---

## 🛠️ Proposed Changes

### 🎨 Phase 1: Wechselkurs-Modal im Dashboard (Tier: `Low`)

#### [MODIFY] [dashboard.html](file:///home/dev/SmartContractManager/app/templates/dashboard.html)
* **Pill-Auslöser im Header:**
  * Hinzufügen von `#exchangeRatesModalTrigger` links neben dem Zeitraum-Umschalter (`btn-group`).
* **Entfernen der Vollbreiten-Karte:**
  * Löschen des bisherigen `#foreignCurrencyRatesCard` am Ende der Seite.
* **Hinzufügen des Modals `#exchangeRatesModal`:**
  * Zentriertes Bootstrap 5.3 Modal (`modal-dialog-centered`):
    * **Header:** Icon `bi-currency-exchange`, Titel und Schließen-Button.
    * **Body:** Liste aller Fremdwährungen mit Badges, aktuellem EZB-Kurs, Kursdatum, Anzahl betroffener Verträge sowie Infobox zur Indikativität von Referenzkursen.
    * **Footer:** Schließen-Button.

#### [MODIFY] [de.json](file:///home/dev/SmartContractManager/app/locales/de.json) & [en.json](file:///home/dev/SmartContractManager/app/locales/en.json)
* Ergänzung von `dashboard.exchange_rates_modal_hint` für den Transparenzhinweis im Modal.

#### [MODIFY] [test_dashboard.py](file:///home/dev/SmartContractManager/tests/test_dashboard.py)
* Aktualisierung der Dashboard-Tests: Prüfen, dass `#exchangeRatesModalTrigger` und `#exchangeRatesModal` vorhanden sind und `#foreignCurrencyRatesCard` nicht mehr existiert.

---

### ⚙️ Phase 2: Kalenderjahr-Engine, Zukunftskurs-Sperre & DB-Bereinigung (Tier: `High`)

#### [MODIFY] [models.py](file:///home/dev/SmartContractManager/app/models.py)
* **Zukunftskurs-Sperre in `ExchangeRateCache`:**
  * Hinzufügen von `@validates('rate_date')`:
    ```python
    @validates('rate_date')
    def validate_rate_date(self, key, value):
        if value and value > date.today():
            raise ValueError(f"Exchange rate date {value} cannot be in the future.")
        return value
    ```

#### [MODIFY] [currency_service.py](file:///home/dev/SmartContractManager/app/services/currency_service.py)
* **Methode `prefetch_year(base_currency, target_currency, year)`:**
  * Prüft Cache-Vollständigkeit. Wenn unvollständig: Abruf `{year}-01-01` bis `{year}-12-31` (bzw. `today` für das laufende Jahr) und Massen-Persistierung in `ExchangeRateCache`.
* **Methode `prefetch_contract_history(contract, target_currency)`:**
  * Führt `prefetch_year` für alle Kalenderjahre von Vertragsbeginn bis heute aus.
* **Stoppschild in `get_rate(base, target, as_of)`:**
  * `if as_of and as_of > today: as_of = today`.

#### [MODIFY] [financial_service.py](file:///home/dev/SmartContractManager/app/services/financial_service.py)
* **`calculate_contract_cost_summary(contract, as_of=None, target_currency=None)`:**
  * Prefetcht die Vertragshistorie und rechnet vergangene Fälligkeiten (`d <= ref_date`) mit dem taggenauen historischen EZB-Kurs aus dem Cache um. Zukünftige Fälligkeiten nutzen den heutigen Spot-Kurs (`as_of=None`).
* **`calculate_provider_summary(contracts, target_currency, as_of)`:**
  * `total_paid` nutzt die taggenau aggregierten Werte `c_summary["paid_amount_converted"]`.
* **`calculate_cashflow_projection`:**
  * Zukünftige Fälligkeiten nutzen `as_of=None` (keine Zukunftsabfragen).

#### [MODIFY] [contract_detail.html](file:///home/dev/SmartContractManager/app/templates/contract_detail.html)
* Wenn `contract.currency != current_user.currency`, wird unter „Bisher bezahlt“ dezent der historisch exakt umgerechnete Betrag angezeigt (`≈ X.XX EUR`).

#### [MODIFY] [tests/test_currency_service.py](file:///home/dev/SmartContractManager/tests/test_currency_service.py) & [tests/test_financial_service.py](file:///home/dev/SmartContractManager/tests/test_financial_service.py)
* Tests für `@validates('rate_date')` (`ValueError` bei Zukunftsdatum).
* Tests für Kalenderjahr-Prefetching (Cache-Hit bei Zweitaufruf).
* Tests für taggenaue historische Fälligkeitsumrechnung im Fremdwährungsvertrag.

---

## 📋 Verification Plan

### Automatisierte Tests
1. **Verifikation Phase 1 (UI):**
   ```bash
   docker compose exec -T web pytest tests/test_dashboard.py -v
   ```
2. **Verifikation Phase 2 (Backend & DB):**
   ```bash
   docker compose exec -T web pytest tests/test_currency_service.py tests/test_currency_v2.py tests/test_financial_service.py tests/test_provider.py -v
   ```
3. **Gesamte Testsuite:**
   ```bash
   docker compose exec -T web pytest
   ```

### Manuelle UI-Prüfung
1. **Phase 1:** Dashboard aufrufen: Pill-Button im Header prüfen, Modal öffnen und Schließen testen, verifizieren, dass unten kein Balken mehr existiert.
2. **Phase 2:** Prüfen, dass `SELECT COUNT(*) FROM exchange_rate_cache WHERE rate_date > CURRENT_DATE;` exakt `0` liefert. Auf der Detailseite von *Github* prüfen, dass „Bisher bezahlt“ den echten historischen Wechselkursen entspricht.
