# Vertragsrecht & Berechnungsregeln: SmartContract Manager

## 1. Zweck & Verbindlichkeit
Dieses Dokument definiert die verbindlichen mathematischen, logischen und juristischen Leitplanken für den Lebenszyklus von Verträgen, Fristenberechnungen und Kündigungsmechanismen im SmartContract Manager.
Alle Entwickler und Agenten müssen diese Regeln bei der Implementierung von Backend-Logik, Validierungen, Berechnungs-Engines und Benutzeroberflächen strikt einhalten.

---

## 2. Mathematische Invarianten & Berechnungsformeln

### 2.1 Fristenberechnung (Cancellation Deadline vs. End Date)
* **Kündigungsstichtag (Cancellation Deadline):**
  $$\text{cancellation\_deadline} = \text{target\_period\_end} - \text{notice\_period}$$
  *Strikte Trennung:* Der Kündigungsstichtag ist der spätestmögliche Tag, an dem die Kündigungserklärung dem Vertragspartner **zugehen** muss. Er ist niemals identisch mit dem Vertragsbeendigungsdatum (`earliest_cancellation_date`).
* **Nächstes Vertragsende (`earliest_cancellation_date`):**
  Liegt der aktuelle Stichtag in der Vergangenheit, rolliert der Vertrag in die nächste Periode (gemäß `renewal_type` und `renewal_period_months`).

### 2.2 Vertragsverlängerung (VVL-Invariante)
* **Laufzeit-Isolation:**
  Wird ein bestehender Vertrag verlängert (z. B. um 12 oder 24 Monate), speichert `contract.initial_term_months` **ausschließlich die neu vereinbarte Verlängerungsdauer (`months_added`)**.
* **Verbot historischer Gesamtlaufzeiten:**
  Es ist strikt untersagt, die Differenz zwischen dem ursprünglichen Vertragsbeginn vor mehreren Jahren und dem neuen Laufzeitende als `initial_term_months` zu speichern (Verhinderung des 95-Monate-Bugs).
* **Mindestbindungs-Kosten (`initial_commitment`):**
  Die garantierte Mindestbindung summiert ausschließlich Zahlungen der aktiven Mindestbindungsperiode (`add_months(initial_end, -term_months)` bis `initial_end`). Alle davor geleisteten Zahlungen gehören ausschließlich in `paid_amount` (Historie).

---

## 3. Gesetzlicher Verbraucherschutz & Laufzeiten (BGB, VVG, EGBGB)

### 3.1 Gesetz für faire Verbraucherverträge (BGB § 309 Nr. 9)
* **BGB § 309 Nr. 9 lit. a (Erstlaufzeit):**
  In vorformulierten Vertragsbedingungen (AGB) darf die anfängliche Vertragslaufzeit für regelmäßige Lieferungen/Dienstleistungen gegenüber Verbrauchern **maximal 24 Monate** betragen. Längere Erstlaufzeiten sind unwirksam.
* **BGB § 309 Nr. 9 lit. b (Automatische Verlängerung seit 01.03.2022):**
  Für alle Verbraucherverträge, die **ab dem 01.03.2022** geschlossen wurden, gilt:
  * Stillschweigende Verlängerungen dürfen ausschließlich auf **unbestimmte Zeit** erfolgen.
  * Der Verbraucher hat das zwingende Recht, den Vertrag jederzeit mit einer Frist von **maximal 1 Monat** zu kündigen (`renewal_type = "monthly_rolling"`, `cancellation_notice_amount <= 1`, `cancellation_notice_unit = "months"`).
  * Klauseln über automatische 12- oder 24-Monats-Verlängerungen sind für Neuverträge seit dem 01.03.2022 gesetzlich unwirksam.
* **Art. 229 § 60 EGBGB (Übergangsrecht für Altverträge):**
  Verträge, die **vor dem 01.03.2022** abgeschlossen wurden, dürfen sich weiterhin stillschweigend um bis zu 12 Monate verlängern (`fixed_period`), sofern dies in den damaligen AGB wirksam vereinbart war.

### 3.2 Gesetzliche Ausnahme für Versicherungen (VVG § 11 Abs. 2)
* Versicherungsverträge (z. B. KFZ-Versicherung, Haftpflicht, Hausrat) unterliegen dem Versicherungsvertragsgesetz (VVG) und sind von der Monats-Regel des § 309 Nr. 9 lit. b BGB ausgenommen.
* **§ 11 Abs. 2 VVG:**
  Versicherungsverträge dürfen sich bei Nichtkündigung weiterhin stillschweigend um jeweils bis zu **1 Jahr (12 Monate)** verlängern (`renewal_type = "fixed_period"`, `renewal_period_months = 12`). Die Kündigungsfrist beträgt hier üblicherweise 1 bis 3 Monate zum Ablauf des Versicherungsjahres.

---

## 4. Gesetzliche Fristenberechnung & Zugang (§§ 187, 188, 193, 130 BGB)

### 4.1 Fristenberechnung nach BGB
* **§ 187 Abs. 1 BGB (Fristbeginn):**
  Ist für den Anfang einer Frist ein Ereignis maßgebend, wird der Tag des Ereignisses nicht mitgerechnet.
* **§ 188 Abs. 2 BGB (Fristende):**
  Eine Frist, die nach Monaten bestimmt ist, endigt mit dem Ablauf desjenigen Tages des letzten Monats, welcher durch seine Zahl dem Tage entspricht, in den das Ereignis fällt.

### 4.2 Wichtiger Fallstrick: Ausschluss von § 193 BGB bei Kündigungsfristen
* **BGH & BAG Grundsatz (Ständige Rechtsprechung):**
  § 193 BGB (Verschiebung des Fristendes auf den nächsten Werktag, wenn der letzte Tag auf einen Samstag, Sonntag oder Feiertag fällt) findet auf **Kündigungsfristen grundsätzlich KEINE Anwendung** zugunsten des Kündigenden!
* **Begründung:**
  Kündigungsfristen sind Mindestfristen zum Schutz des Empfängers. Eine Verschiebung auf den darauffolgenden Montag würde die gesetzliche oder vertragliche Frist des Empfängers unzulässig verkürzen.
* **System-Invariante:**
  Die Fristberechnung darf einen Kündigungsstichtag, der auf ein Wochenende fällt, **keinesfalls auf den folgenden Werktag nach hinten verschieben**. Geht eine Kündigung erst am Montag zu, ist sie verspätet!
* **Puffer-Empfehlung:**
  Erinnerungen und Warnstufen müssen den Nutzer frühzeitig (mindestens 7 bis 14 Tage vor Stichtag) warnen, um Postlaufzeiten und Wochenenden abzufedern.

### 4.3 Zugangsprinzip (§ 130 Abs. 1 BGB)
* Kündigungen sind empfangsbedürftige Willenserklärungen. Sie werden erst wirksam, wenn sie in den **Machtbereich des Empfängers** gelangen (Briefkasten, E-Mail-Postfach) und dieser unter normalen Umständen Kenntnis nehmen kann.
* Der Nachweis des rechtzeitigen Zugangs obliegt stets dem Kündigenden.

---

## 5. Gesetzliche Sonderkündigungsrechte (Außerordentliche Kündigung)

Bei einseitigen Vertragsänderungen greifen branchenspezifische Sonderkündigungsrechte:

### 5.1 Energie / Strom & Gas (§ 41 Abs. 5 EnWG)
* Bei einseitigen Preisanpassungen durch den Energieversorger hat der Kunde das Recht, den Vertrag **ohne Einhaltung einer Kündigungsfrist zum Zeitpunkt des Wirksamwerdens** der Änderung zu kündigen.
* Der Versorger muss die Änderung mindestens 1 Monat (in der Grundversorgung: 6 Wochen) im Voraus ankündigen.

### 5.2 Versicherungen (§ 40 Abs. 1 VVG)
* Erhöht der Versicherer die Prämie ohne Leistungserweiterung, kann der Versicherungsnehmer den Vertrag innerhalb von **einem Monat nach Zugang der Mitteilung** mit sofortiger Wirkung, frühestens jedoch zum Zeitpunkt des Wirksamwerdens der Erhöhung, kündigen.

### 5.3 Telekommunikation (§ 57 Abs. 1 TKG)
* Bei einseitigen Vertrags- oder Tarifänderungen durch den Anbieter kann der Verbraucher den Vertrag **ohne Kosten und ohne Einhaltung einer Frist innerhalb von 3 Monaten** ab Zugang der Unterrichtung kündigen.

### 5.4 Geplante Preisstufen vs. Sonderkündigung
* Regulär vereinbarte Preissprünge (z. B. „ab dem 13. Monat 49,99 € statt 19,99 €“) begründen **kein** Sonderkündigungsrecht, da sie Vertragsbestandteil waren.
* Systemverhalten: Solche Preissprünge erfordern eine rechtzeitige **Kostenfallen-Vorwarnung** (30–60 Tage vorab), damit die ordentliche Kündigungsfrist nicht versäumt wird.

---

## 6. Formvorschriften & Kündigungsstandards

### 6.1 Textform (§ 126b BGB & § 309 Nr. 13 lit. b BGB)
* Für nach dem 30.09.2016 geschlossene Verbraucherverträge ist die **Textform** (§ 126b BGB) ausreichend (E-Mail, Webformular, PDF-Anhang).
* AGB-Klauseln, die eine strengere Form als die Textform vorschreiben (z. B. zwingend Schriftform mit handschriftlicher Unterschrift oder Einschreiben), sind gegenüber Verbrauchern unwirksam.
* **Kündigungsbutton (§ 312k BGB):** Für im elektronischen Geschäftsverkehr geschlossene Verträge muss der Anbieter einen leicht zugänglichen Kündigungsbutton bereitstellen.

### 6.2 Rechtssichere Bausteine für Kündigungsschreiben
Kündigungsschreiben (z. B. nach DIN 5008 generierte PDF-Briefe oder E-Mail-Vorlagen) müssen folgende Schutzbausteine enthalten:
1. **Eindeutige Identifikation:** Name, Anschrift, Kundennummer, Vertragsnummer.
2. **Kündigungserklärung:** Hilfsweise Kündigung zum nächstmöglichen Termin („fristgerecht zum nächstmöglichen Zeitpunkt“).
3. **SEPA-Widerruf:** Ausdrücklicher Widerruf der erteilten Einzugsermächtigung mit Wirkung zum Beendigungszeitpunkt.
4. **Bestätigungsaufforderung:** Aufforderung zur schriftlichen Bestätigung der Kündigung unter verbindlicher Nennung des Beendigungsdatums innerhalb einer Frist von 14 Tagen.
5. **Datenlöschung / Werbewiderspruch:** Widerspruch gegen werbliche Kontaktaufnahme nach Vertragsende (§ 7 UWG).

---

## 7. TDD-Absicherung & Qualitätssicherung
* Jede der vorgenannten Invarianten (insbesondere 24-Monats-Grenze, monatliches Rollieren nach 01.03.2022, VVG-Ausnahme, strikte Stichtagsberechnung ohne § 193 BGB-Verschiebung) muss durch **automatisierte Pytest-Tests** in `tests/test_contract_lifecycle.py` und `tests/test_contract.py` abgesichert sein.
* Regressionen bei Datums- und Fristenberechnungen führen zu sofortigem Testabbruch.
