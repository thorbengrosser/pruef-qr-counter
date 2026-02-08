# PRÜF QR Counter

This project is a networked protest object: a physical sign with a small electronic display that shows a live counter, combined with a web page that allows anyone to increase that number. Each interaction updates the display in real time. What looks like a simple technical counter is used as a public, procedural gesture — a visible record of repeated “checks” that mirrors the logic of the PRÜF protests in Germany. The hardware, software, and web components together form a minimal system designed to be deployed in public space, understood at a glance, and experienced through use rather than explanation.

## Concept & Motivation

This project is inspired by the **PRÜF protests in Germany** (“Prüfung rettet übrigens Freiheit”), a protest movement that focuses on a procedural demand rather than a slogan:
that right-wing extremist parties should be **formally reviewed** using the mechanisms already provided by Germany’s constitutional system.

A central element of PRÜF is the observation that *checking* is deeply embedded in German political and cultural practice. Technical devices, institutions, infrastructure, and everyday processes are routinely inspected, certified, audited, and reviewed. Against this background, the refusal or delay to initiate formal constitutional reviews appears less like a legal necessity and more like a political choice.

PRÜF uses this contrast deliberately. Instead of arguing *against* something, the protests insist on a procedure that already exists and frame it as an act of civic order rather than resistance.

This repository implements a **digital, interactive protest object** that translates this logic into a physical and technical form.

By repeatedly “checking” a QR code — and making the number of checks visible on a physical display mounted on a protest sign — the project mirrors the core PRÜF idea:
procedures are followed, again and again, even when they lead nowhere. The repetition itself becomes the statement.

The design language, interaction model, and pacing are intentionally bureaucratic. The system is not optimized for speed, convenience, or delight. Redundancy is allowed. Repetition is encouraged. The device does exactly what it is instructed to do, without questioning whether the act has political consequences.

In a protest context, this creates a quiet but persistent form of commentary:
if trivial objects can be checked endlessly, then refusing to initiate formal constitutional reviews is not a matter of feasibility, but of will.

---

## Technical Overview (Dry)

This repository contains the code for a small distributed system used in a protest installation context.

It consists of:

- a **web application** that allows users to trigger a simple action (incrementing a counter)
- a **backend service** that records these events and exposes a minimal JSON API
- **firmware for ESP32 microcontrollers** and **embedded Linux devices** (e.g. Raspberry Pi–class systems) that periodically poll the API and render the current counter value on a low-power display

The backend maintains a monotonically increasing counter and minimal metadata required for rate limiting and basic statistics. The API is designed to be small, predictable, and suitable for frequent polling by constrained devices.

Embedded clients fetch the counter value at regular intervals and update a locally attached display. The system is tolerant of intermittent connectivity and does not rely on persistent sessions.

The web application does not use cookies or user accounts. Where identifiers are required for operational purposes, they are derived in a one-way manner and are not intended for user tracking beyond short-term constraints.

The overall design prioritizes:

- low operational complexity
- minimal infrastructure requirements
- portability across hosting environments
- robustness in public, real-world deployments

While the system was built specifically for use in PRÜF-related protest settings, the technical components are generic and can be reused for other installations involving public counters, networked displays, or simple interactive artifacts.

## Repository Structure

| Directory        | Description |
|------------------|-------------|
| **web-app/**     | Flask web application and JSON API. Users scan the QR code, increment the counter, and see the current value. Includes Docker setup and deployment docs. See `web-app/README.md`. |
| **esp32/**       | ESP32 prototype / reference firmware (C++/PlatformIO). Polls `GET /api/count` and drives an iPixel-style display. Useful as a minimal microcontroller client. See `esp32/README.md`. |
| **rpi/**         | Raspberry Pi Zero 2 W client. Python daemon (`display_app.py`) + Flask config UI + NetworkManager scripts + install script. Provides the “set-and-forget” protest sign: captive portal, WiFi failover, BLE display control. See `rpi/README.md`. |


## Tech Stack (Very Short)

- **web-app:** Flask, SQLite, Docker; mobile-first UI in a sober institutional style.
- **clients:** ESP32 (C++) and Raspberry Pi Zero 2 W (Python 3.10+, BLE via `pypixelcolor`/`bleak`).

See each subdirectory’s `README.md` for details.

## Acknowledgements

This project would not exist in its current form without:

- **pypixelcolor** — the BLE / iPixel library that makes talking to the displays from Python feasible on small hardware.
- The authors and maintainers of **bleak**, **Pillow**, **Flask**, **NetworkManager**, and the wider Raspberry Pi ecosystem.
- Espressif and everyone who is involved in the ESP32 ecosystem. Your devices literally power everything.

Any mistakes or regressions are of course mine, not theirs.

## License

This project is licensed under the terms in **[LICENSE](LICENSE)**. In short:

- You may **use, copy, modify, and redistribute** it, including for commercial use.
- **No law-enforcement or military use** — see the LICENSE file for the exact restriction.
- **No warranty** — provided “as is”.

If these terms are incompatible with your context, you are free to use the ideas and implement your own.