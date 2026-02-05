# PRÜF – Design Language Concept
Version: v1.0  
Purpose: Internal design reference for UI, web and campaign extensions

---

## 1. Core Idea

The PRÜF design language simulates **German bureaucracy as a cultural ritual**.

Not as satire through chaos or noise,  
but as **order taken seriously enough to become uncanny**.

The interface should feel:
- official
- procedural
- sober
- slightly over-regulated

And only then, in small doses:
- off
- rigid to the point of absurdity
- quietly funny

The humour never shouts.  
It emerges from **excessive correctness**.

It is very important that the page is Mobile First, it will be 99% accessed by mobile users.
We should make this as accessible as possible without overdoing it.

---

## 2. Emotional Target

The design should evoke the feeling of:
- filling out a form at an authority that is calm, slow and absolute
- being processed, not engaged
- receiving a decision, not an opinion

Users should think:
> “This feels like an Amt. Why is this so convincing?”

And only afterwards:
> “Wait. That’s the point.”

---

## 3. Visual Tone

### Keywords
- Amtlich
- Gedämpft
- Papierhaft
- Kontrolliert
- Leicht unheimlich

### What it is NOT
- Not playful
- Not ironic in colour
- Not meme-driven
- Not techy
- Not activist-design-loud

---

## 4. Colour Philosophy

Colours are **functional, not expressive**.

They should feel like:
- office walls
- old folders
- stamped paper
- faded signage

### Principles
- Low saturation
- Earthy, bureaucratic tones
- High contrast only where functionally justified

### Usage
- Backgrounds: muted, heavy, institutional
- Paper surfaces: off-white, beige, grey
- Accents: dark green or black, used sparingly
- Error / “No” states: deep, restrained red (never bright)

Colour should never feel decorative.  
It should feel **administrative**.

---

## 5. Typography System

Typography carries most of the meaning.

### Serif (Primary Voice)
Used for:
- headlines
- decisions
- main text blocks

Reason:
Serifs evoke:
- authority
- tradition
- legal weight
- printed documents

They feel like text that **cannot be argued with**.

### Sans-serif (Secondary Voice)
Used for:
- labels
- UI chrome
- metadata
- helper text

Reason:
Sans-serif is procedural and neutral.  
It reads as “system language”.

### Monospace (Administrative Detail)
Used for:
- reference numbers
- counters
- IDs
- technical or formal identifiers

Reason:
Monospace signals:
- files
- systems
- bureaucracy behind the scenes

---

## 6. Layout & Structure

### Paper Metaphor
Every screen behaves like a **document**:
- contained
- bordered
- slightly elevated
- separate from the background

The UI is not fluid or airy.  
It is **contained and filed**.

### Geometry
- Mostly sharp edges
- Minimal rounding
- Straight lines
- Clear separations

### Alignment
- Structured
- Column-based
- Table-like where possible

Nothing should feel “free”.

---

## 7. Uncanny Elements (Very Important)

Uncanny elements are:
- rare
- subtle
- controlled

Examples:
- harsh, offset shadows
- slightly misaligned stamps
- dotted grids (millimetre paper)
- procedural repetition
- overly formal microcopy

### Rule:
**Only one uncanny gesture per screen.**

If everything is uncanny, nothing is.

The uncanny should feel like:
> “This is correct. Almost too correct.”

---

## 8. Buttons & Interaction

Buttons are **official actions**, not invitations.

They should feel like:
- submitting
- filing
- requesting
- escalating

### Primary CTA
- Visually heavy
- High contrast
- Feels irreversible

Example:
`Antrag faxen`

### Secondary Actions
- Smaller
- Less visual weight
- Almost discouraged

Example:
`Widerspruch einlegen`

Hover and focus states should feel:
- mechanical
- procedural
- deliberate

---

## 9. Copy & Language (UI Tone)

Language is:
- formal
- passive
- administrative
- unemotional

Even jokes are written as:
- notices
- results
- procedural statements

Example:
Not:
> “You increased the counter!”

But:
> “Antrag registriert.”

Humour comes from **framing**, not wording.

---

## 10. Consistency Rule

When extending this design language:

Always ask:
1. Would this exist in a German authority?
2. Would it be useful, boring, or procedural?
3. Is the joke emerging from correctness, not decoration?

If the answer to (1) is no → redesign.

---

## 11. Success Criterion

The design is successful if:
- people trust it for a second
- then notice something is off
- and only then understand the political message

The interface should never explain itself.

It behaves like an authority.


# Sample CSS Code
/* --- PRÜF / Amtlich + Uncanny (refined) --- */
:root {
  --deep-green: #1B4024;
  --dull-beige: #BFBFAA;
  --shadow-green: #737151;
  --paper-white: #D9D9D9;
  --pure-black: #0D0D0D;

  --line: rgba(13, 13, 13, 0.22);
  --muted: rgba(13, 13, 13, 0.62);

  --serif: "Georgia", "Times New Roman", serif;
  --sans: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
  --mono: ui-monospace, "Courier New", Courier, monospace;

  --radius: 0px; /* bureaucratic = sharp */
}

/* Page container */
.demo {
  font-family: var(--serif);
  background-color: var(--deep-green);
  color: var(--pure-black);
  display: flex;
  justify-content: center;
  align-items: flex-start;
  gap: 22px;
  padding: 40px 18px 70px;
  min-height: 100vh;
}

/* Card/screen */
.screen {
  width: min(420px, 92vw);
  background: var(--dull-beige);
  border: 1px solid rgba(27, 64, 36, 0.65);
  box-shadow: 12px 12px 0px var(--pure-black);
  position: relative;
  overflow: hidden;
}

/* Subtle uncanny mm-paper grid */
.screen::before {
  content: "";
  position: absolute;
  inset: 0;
  background-image: radial-gradient(var(--shadow-green) 0.55px, transparent 0.55px);
  background-size: 15px 15px;
  opacity: 0.09;
  pointer-events: none;
}

/* Add a faint "paper texture" so it feels printed, not flat */
.screen::after {
  content: "";
  position: absolute;
  inset: 0;
  background:
    linear-gradient(0deg, rgba(0,0,0,0.025), rgba(0,0,0,0)),
    repeating-linear-gradient(
      90deg,
      rgba(0,0,0,0.012) 0px,
      rgba(0,0,0,0.012) 1px,
      transparent 1px,
      transparent 22px
    );
  opacity: 0.35;
  mix-blend-mode: multiply;
  pointer-events: none;
}

/* Content padding (assumes you have .paper / main wrapper) */
.paper {
  position: relative;
  z-index: 1;
  padding: 16px;
}

/* Topbar: more "header strip" */
.topbar {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(27, 64, 36, 0.55);
  background: rgba(217, 217, 217, 0.18);
}

/* Optional: make brand feel like a stamp label */
.brand .logo {
  font-family: var(--sans);
  font-weight: 900;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.brand .sub {
  font-family: var(--sans);
  font-size: 12px;
  color: rgba(13, 13, 13, 0.70);
}

/* Chip: looks like an office tag */
.chip {
  background: var(--deep-green);
  color: var(--paper-white);
  font-family: var(--mono);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 6px 10px;
  border: 1px solid rgba(13, 13, 13, 0.35);
  box-shadow: 2px 2px 0 rgba(13, 13, 13, 0.55);
}

/* Headings: bureaucratic, not elegant */
h1, h2 {
  margin: 0 0 8px;
  font-size: 1.35rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  border-bottom: 2px solid rgba(27, 64, 36, 0.75);
  display: inline-block;
  padding-bottom: 6px;
}

/* Lede: slightly editorial, but restrained */
.lede {
  margin: 6px 0 14px;
  color: rgba(13, 13, 13, 0.68);
  line-height: 1.35;
}

/* Counter: "off-limits" notice feel */
.counter {
  background: var(--paper-white);
  border: 1px inset var(--shadow-green);
  padding: 14px;
  margin: 18px 0 16px;
  box-shadow: 0 0 0 1px rgba(13,13,13,0.10);
}

.counter .k {
  font-family: var(--sans);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 11px;
  color: var(--muted);
}

.counter .n {
  font-family: var(--mono);
  font-size: 2.4rem;
  color: var(--pure-black);
  margin-top: 6px;
}

.counter .s {
  font-family: var(--sans);
  font-size: 12px;
  color: var(--muted);
  margin-top: 6px;
}

/* Form: make it look like a form table */
.form {
  background: rgba(217, 217, 217, 0.22);
  border: 1px solid rgba(13, 13, 13, 0.20);
}

.row {
  display: grid;
  grid-template-columns: 130px 1fr;
  gap: 10px;
  padding: 10px 12px;
  border-top: 1px solid rgba(13, 13, 13, 0.18);
}

.row:first-child { border-top: 0; }

.row .k {
  font-family: var(--sans);
  text-transform: uppercase;
  letter-spacing: 0.10em;
  font-size: 11px;
  color: var(--muted);
}

.row .v {
  font-family: var(--serif);
  font-size: 14px;
}

/* Actions: keep it stern */
.actions {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-top: 16px;
}

/* Buttons: sharp, official */
.btn {
  font-family: var(--sans);
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  border-radius: var(--radius);
  padding: 12px 14px;
  cursor: pointer;
}

/* Primary CTA: the "Amt" button */
.btn.primary {
  background: var(--deep-green);
  color: var(--paper-white);
  border: 1px solid rgba(13, 13, 13, 0.35);
  box-shadow: 3px 3px 0 rgba(13, 13, 13, 0.55);
  transition: transform 0.12s ease, box-shadow 0.12s ease, background 0.12s ease;
}

.btn.primary:hover {
  background: var(--pure-black);
  transform: translate(-2px, -2px);
  box-shadow: 5px 5px 0 var(--shadow-green);
}

/* Keyboard focus: make it feel like an official highlight */
.btn:focus-visible {
  outline: 3px solid var(--shadow-green);
  outline-offset: 3px;
}

/* Ghost: looks like a link on a form */
.btn.ghost {
  background: transparent;
  border: 1px solid transparent;
  color: var(--deep-green);
  text-decoration: underline;
  font-weight: 700;
  letter-spacing: 0.04em;
}

/* Tiny secondary button (e.g. Widerspruch) */
.btn.tiny {
  background: transparent;
  border: 1px solid rgba(13,13,13,0.25);
  color: rgba(13,13,13,0.80);
  padding: 10px 12px;
  font-size: 12px;
  box-shadow: 2px 2px 0 rgba(13,13,13,0.35);
}

/* Bescheid: make it feel like a cover page */
.bescheid-head .title {
  font-family: var(--sans);
  font-weight: 900;
  letter-spacing: 0.18em;
}

.az, .mono {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--muted);
}

/* Result: less "pretty", more "file note" */
.result {
  background: rgba(27, 64, 36, 0.08);
  border-left: 6px solid var(--deep-green);
  border-top: 1px solid rgba(13,13,13,0.15);
  border-right: 1px solid rgba(13,13,13,0.15);
  border-bottom: 1px solid rgba(13,13,13,0.15);
  padding: 10px 12px;
  font-style: italic;
}

/* Make the "no" line sting without screaming */
.no {
  color: rgba(162, 47, 38, 0.92);
  font-style: normal;
  font-weight: 700;
}

/* Legal footer: present but boring */
.legal {
  margin-top: 16px;
  padding-top: 10px;
  border-top: 1px solid rgba(13,13,13,0.18);
  font-family: var(--sans);
  font-size: 12px;
  display: flex;
  justify-content: center;
  gap: 8px;
  color: rgba(13,13,13,0.70);
}

.legal a {
  color: rgba(13,13,13,0.80);
  text-decoration: none;
  border-bottom: 1px dotted rgba(13,13,13,0.35);
}

.legal a:hover {
  border-bottom-style: solid;
}
