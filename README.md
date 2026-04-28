# Funnel Analysis: Edge Cases & Real-World Intricacies

> "A naive funnel lies. A robust funnel tells the truth.
>  A good analyst documents that truth so the business can act on it."

## What This Project Is

Most funnel analysis tutorials show you clean data and simple conversion rates.
This project simulates what funnel analysis actually looks like at a real
tech company — messy, fragmented, and full of traps that mislead
decision-makers when left unaddressed.

This is not an academic exercise. Every edge case modelled here has a
direct equivalent in production data at companies like Airbnb, Spotify,
and any mid-to-large e-commerce platform.

---

## The Dataset

A simulated e-commerce event log of **1,711 raw events** across **468 users**
with four real-world intricacies intentionally injected:

| Intricacy | Description | Business Impact |
|---|---|---|
| **Loopbacks** | Users cycling cart → home → cart | Inflates step counts |
| **Duplicate Events** | SDK fires checkout_click 3× in 2 seconds | Overcounts conversion volume |
| **Cross-Device Fragmentation** | Mobile session → Web purchase | Misattributes conversion credit |
| **Orphaned Purchases** | Purchase fires with no prior cart event | Inflates checkout conversion rate |

**Funnel Steps:** `home → product_view → add_to_cart → checkout_click → purchase`

---

## The Four Findings

### Finding 1 — Naive Funnel Inflates Checkout Conversion by 7.1 Points

Orphaned purchase events — purchases with no prior checkout path —
caused the naive funnel to report an **83.7% checkout-to-purchase rate.**

Strict sequence analysis, enforcing chronological order at every step,
revealed the true rate was **76.6%** — a 7.1 percentage point inflation.

**13 users (8.4% of purchases)** had purchase events with no verifiable
checkout path. These were flagged for data engineering audit.

| Model | Checkout → Purchase Rate |
|---|---|
| Naive funnel | 83.7% |
| Strict sequence funnel | 76.6% |
| **Inflation** | **7.1 percentage points** |

---

### Finding 2 — Checkout Volume Overcounted by 49%

Rapid-fire duplicate `checkout_click` events — consistent with SDK retry
behavior or button debounce failure — inflated raw checkout event volume
from **184 true user-level events to 274 raw events.**

A 5-second deduplication window removed all **90 duplicate events.**
Every removed event was a `checkout_click` — zero false positives
on any other event type.

If a team is measuring "checkout attempts" from raw event counts,
they are working with numbers that are **49% higher than reality.**

---

### Finding 3 — 34 User Journeys Were Being Misread as Drop-offs

Cross-device users who switched devices mid-funnel had gaps of
**up to 724 minutes** between events on different devices.

A 30-minute sessionization timeout correctly identified **34 session
boundaries** caused entirely by device switching — not genuine abandonment.

Without sessionization these users appeared as:
- One incomplete mobile session (looks like drop-off)
- One incomplete web session (looks like a new user drop-off)

With sessionization their true journey became visible as a single
cross-device path, correctly attributed to one user.

---

### Finding 4 — Standard Attribution Models Miss 22 Mobile-Influenced Conversions

**The core insight:** Cross-device users in this dataset switch to a secondary
device for a single mid-funnel step — typically at `add_to_cart` or
`checkout_click` — then return to their primary device to complete the purchase.

This pattern makes their `first_device` and `last_device` identical,
causing First-Touch and Last-Touch attribution to produce mathematically
identical results. Both models assign **zero credit** to the mid-funnel device.

**Mobile_App appeared as a mid-funnel influence in 22 converted journeys**
— representing **14.3% of all conversions** — receiving zero attribution
credit under standard models.

A Position-Based model was implemented assigning:
- 80% credit to the primary device (first and last touch)
- 20% credit to the mid-funnel influence device

This revealed Mobile's true conversion influence:

| Attribution Model | Mobile Credit | Mobile Conv Rate |
|---|---|---|
| Last Touch | 59.0 | 33.1% |
| Position-Based | 59.8 | 33.6% |
| True influence (direct + assisted) | 81 conversions | 52.6% touched |

---

## Key Technical Concepts Demonstrated

- **Strict Sequence Funnels** using timestamp-enforced chronological ordering
- **Window Function Logic** via Pandas `shift()` for deduplication
- **Sessionization** with configurable inactivity timeout
- **Position-Based Attribution** for mid-funnel device influence
- **Identity Resolution** assumptions and their real-world failure modes
- **Data Pipeline Lineage** — raw → deduplicated → sessionized layers preserved

---

## Project Structure
