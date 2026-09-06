# SmartContract Manager

Zentrale, selbstgehostete Webanwendung zur strukturierten Verwaltung privater Verträge, Kündigungsfristen und laufender Fixkosten nach deutschem Recht.

---

## Entwicklungsstatus

> [!NOTE]
> Das Projekt befindet sich aktuell in **aktiver Entwicklung (Pre-Release)**. Eine offizielle Bereitstellung als fertiges Image auf Docker Hub und GitHub Container Registry (GHCR) sowie Installations- und Deployment-Anleitungen folgen mit Erreichen des ersten stabilen Releases.

---

## Kernfunktionen

* 📋 **Vertrags-Cockpit & Fristenüberwachung:**
  * Lückenlose Erfassung von Laufzeiten, Mindestvertragslaufzeiten und Kündigungsfristen.
  * Automatische Abbildung des deutschen Verbraucherrechts (stillschweigende monatliche Verlängerung nach BGB § 309 Nr. 9).
  * Exakte Stichtagsberechnung (Countdown bis zum letztmöglichen Kündigungseingang).
  * Strukturierte Statusübergänge (*Aktiv*, *Kündigung eingereicht*, *Kündigung bestätigt*, *Ruhend*, *Beendet*, *Archiviert*).

* 🏢 **Vertragspartner-Verwaltung:**
  * Zentrale Bündelung aller Kontaktdaten, Kundennummern und Vertragsbeziehungen.
  * Direkte Absprünge in Kundenportale und Kündigungsformulare.
  * Integrierte Notiz-Historie für Gesprächs- und Korrespondenzprotokolle.

* 📊 **Finanz-Dashboard & Cashflow-Vorschau:**
  * Dynamische 12-Monats-Cashflow-Projektion unter Berücksichtigung individueller Abrechnungsanker (`billing_anchor_date`) und Zahlungsrhythmen.
  * Monatsbudget-Analyse (Gegenüberstellung von normalisiertem Monatsmittelwert Ø und tatsächlichen Fälligkeiten).
  * Integrierter Mehrwährungs-Support mit automatischer EZB-Wechselkursumrechnung.

* 🏷️ **Flexibles Tagging & Preishistorie:**
  * Schnelle Kategorisierung über ein dynamisches Tagging-System mit automatischer Farberkennung.
  * Verfolgung von Preisänderungen mit lückenlosem Gültigkeitsverlauf und Unterstützung für geplante künftige Preisstufen (z. B. nach Ablauf von Rabattphasen).

* 🌓 **Moderne Benutzeroberfläche:**
  * Vollständig responsive Gestaltung (optimiert für Smartphones, Tablets und Desktop).
  * Nativer Dark- und Light-Mode auf Basis von Bootstrap 5.3.
  * Mehrsprachig vorbereitet (Deutsch und Englisch).

---

## Roadmap & Meilensteine

Einen vollständigen Überblick über abgeschlossene, aktive und geplante Epics bietet die [ROADMAP.md](ROADMAP.md).

---

## Rechtlicher Hinweis

SmartContract Manager ist ein digitales Organisationswerkzeug zur privaten Vertrags- und Ausgabenverwaltung und erbringt **keine Rechtsberatung** im Sinne des Rechtsdienstleistungsgesetzes (§ 2 Abs. 1 RDG). Sämtliche Frist-, Laufzeit- und Verlängerungsberechnungen erfolgen unverbindlich auf Grundlage der eingegebenen Daten. Der Nachweis des form- und fristgerechten Zugangs von Kündigungen (§ 130 BGB) obliegt stets dem Nutzer.

