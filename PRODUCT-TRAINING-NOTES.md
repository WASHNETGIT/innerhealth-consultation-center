# Agent training on products — what was done and what is verified

Date: 2026-11-19 · Catalog: `static/products/catalog.json`

## What the agent had before
- It was told only a **count**: "we stock the Green World range: 78 products across 6 categories".
- It had no names, sizes, prices or benefits in its brief, so any product answer was a guess.
- A product search function existed but **a product code was never recognised** ("how much is W01" returned nothing).

## What is in place now
1. **Exact catalog facts in the agent's brief** — every product's code, name, size and price, straight
   from the catalog file, with a rule: never invent a benefit, price, dosage or cure.
2. **Exact code lookup** — a code like W01 or W73 returns that one product, never a fuzzy guess.
3. **Catalog corrected** (backup kept beside the file):
   - `W72` was used by two different products. The Tourmaline Thermal Waist Protector is now **W73**.
   - Two rows for *Green World Herbal Toothpaste* — the stale `W54_OLD` row was removed.
   - Result: **78 products, 0 duplicate codes, 0 duplicate names, 0 missing prices.**

## Verified against the catalog
| Question | Agent answered | Catalog says | Match |
|---|---|---|---|
| How much is W01? | Cordyceps Plus Capsule (500mg × 60 capsules) R390 | R390 | yes |
| Blood sugar products | W49 Glucoblock R351, W14 Balsam Pear Tea R254, W67 Balsam Pear Tablet R429 | same | yes |

## Known gap still open
Asking the **admin** endpoint a product question returns clinic statistics first
("Patients: 0. Bookings: 0 …") and the product matches second. The product list is
correct, but the opening line answers the wrong question. This is the admin-answer
routing, not the catalog. Fix: route a product question to the product answer only.
