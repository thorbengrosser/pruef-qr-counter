# PRÜF QR Mini-App — Screen Definitions (UI Only)
Scope: Screens only.  
Language: Instructions in English, UI copy in German.  
Platform: Mobile-first web app.

---

## Screen 0 — Landing (Optional Entry Screen)

**Purpose (instructional):**
- Short intro screen for users arriving via social links.
- Can be skipped when entering via QR scan.

**UI Elements:**
- Headline (large)
- Short explanatory text
- Primary CTA button
- Persistent footer with legal links

**UI Copy (DE):**
- Headline: `Willkommen in der QR-Code-Prüfstelle`
- Text: `Dauert nur wenige Sekunden. Keine App. Kein Login.`
- Primary CTA: `Direkt Antrag faxen`

**Footer (always visible):**
- `Impressum`
- `Datenschutz`

---

## Screen 1 — Antrag auf QR-Code-Prüfung (Form Screen)

**Purpose (instructional):**
- Present the core interaction as a bureaucratic form parody.
- One primary action only.

**UI Elements:**
- Title
- Helper text
- Large counter display
- Fake form (non-interactive, visual only)
- Primary CTA button
- Persistent footer with legal links

**UI Copy (DE):**
- Title: `Antrag auf QR-Code-Prüfung`
- Helper text: `Bitte vollständig ausfüllen (haben wir bereits für Sie erledigt).`

**Counter Section:**
- Label: `Eingegangene Anträge:`
- Value: `{{ZAHL}}`
- Subtext: `(Zählung seit Start der Aktion)`

**Fake Form Fields (static text):**
- `Antragsteller*in: Bürger*in (m/w/d), Ordnungsliebe`
- `Anliegen: Prüfung eines QR-Codes`
- `Begründung: Weil alles Ordnung haben muss`

**Primary CTA:**
- Button label: `Antrag faxen`

**Footer (always visible):**
- `Impressum`
- `Datenschutz`

---

## Screen 2 — Bearbeitung läuft (Processing Screen)

**Purpose (instructional):**
- Communicate that the request is being processed.
- Deliver humour via rotating bureaucratic status messages.

**UI Elements:**
- Waiting number / ticket display
- Main processing message
- Rotating status messages
- Persistent footer with legal links

**UI Copy (DE):**
- Waiting number: `Ihre Wartenummer: A-38`
- Subline: `Bitte bleiben Sie in der Leitung. Sie sind bereits verbunden.`
- Main status: `Fax wird übertragen…`

**Rotating Status Messages (examples, one at a time):**
- `Eingangsstempel wird poliert…`
- `Zuständigkeit wird geprüft (zuständig).`
- `Formular wird auf Formularhaftigkeit geprüft (formularkonform).`
- `Aktenordner wird dramatisch geöffnet…`
- `Bitte nicht drängeln. Drängeln wird geprüft.`
- `Fax ist das Internet der Behörden.`
- `Datenschutz wird respektvoll angesehen.`
- `Protokoll wird nach Protokoll protokolliert…`

**Footer (always visible):**
- `Impressum`
- `Datenschutz`

---

## Screen 3 — Bescheid (Decision Screen)

**Purpose (instructional):**
- Deliver the result and the central political message.
- Offer two next actions with different visual priority.

**UI Elements:**
- Title (“Bescheid”)
- Reference number
- Result block
- Central message
- Two CTAs (unequal visual weight)
- Persistent footer with legal links

**UI Copy (DE):**
- Title: `BESCHEID`
- Reference line (small): `Az.: PRÜF-QR-2026-XXXX`

**Result Block:**
- `✅ QR-Code wurde geprüft.`
- `✅ Ergebnis: verfassungskonform.`

**Central Message:**
- `Nur: Das Bundesverfassungsgericht prüft Parteien nicht automatisch.`
- *(optional small line)* `Und genau das soll sich ändern.`

**CTAs:**
- Primary (visually dominant): `Was nun?`
- Secondary (smaller, joke): `Widerspruch einlegen`

**Footer (always visible):**
- `Impressum`
- `Datenschutz`

---

## Screen 3b — Widerspruch (Optional Joke Screen)

**Purpose (instructional):**
- Provide a humorous second check.
- Allow sharing.
- Lead users onward to the info screen.

**UI Elements:**
- Title
- Short explanatory line
- Result block
- Two CTAs
- Persistent footer with legal links

**UI Copy (DE):**
- Title: `Widerspruch eingegangen.`
- Subline: `Wir prüfen erneut. Gründlicher. Wirklich.`

**Result Block:**
- `✅ QR-Code erneut geprüft.`
- `✅ Immer noch verfassungskonform.`
- `❌ Gesichert rechtsextreme Parteien: immer noch nicht automatisch geprüft.`

**CTAs:**
- Primary: `Was nun?`
- Secondary: `Teilen`

**Footer (always visible):**
- `Impressum`
- `Datenschutz`

---

## Screen 4 — Was nun? (Info Screen)

**Purpose (instructional):**
- Provide exactly three clear next steps.
- No additional explanations.

**UI Elements:**
- Title
- Three large link buttons
- Persistent footer with legal links

**UI Copy (DE):**
- Title: `Was nun?`
- Button 1: `Zu PRÜF`
- Button 2: `Spenden`
- Button 3: `PRÜF-Stand`

**Footer (always visible):**
- `Impressum`
- `Datenschutz`

---
