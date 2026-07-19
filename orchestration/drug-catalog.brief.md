# Mission brief: drug-catalog

Long name: "a standalone nextjs application with posgres db. we need a browsable catalog of Drugs & Medications (see https://www.drugs.com/drug_information.html), using FHIR coding system. each catalog item should be a one-pager of the molecule (e.g. Semaglutide), categorical data like available routes/forms, patent status; on-label and off-label treatments, side effects, frequently asked questions, related items, and an RSS feed that aggregates news and events around the item. each item should include a molecular diagram true as a 'ProductImage'"

## Goal
Build a standalone Next.js + Postgres web app: a browsable catalog of drugs/medications where
each item is a one-page profile of the molecule (e.g. Semaglutide). Audience is medspas and their
patients, so the seed set leans aesthetic/wellness. Each item is coded against FHIR terminology
and carries structured categorical data plus AI-authored plain-language narrative, a molecular
diagram as its ProductImage, and a per-item news feed. Success = a lead can `docker compose up`,
seed ~20-50 molecules, and browse fully-populated one-pagers locally.

## In scope
- New standalone repo (Next.js App Router + TypeScript, Postgres). Local-only: `docker compose up`
  brings up Postgres; app runs with `pnpm dev`.
- Data model keyed on FHIR. Model each item as a FHIR **MedicationKnowledge**-shaped record
  (it fits a catalog one-pager better than `Medication`): `code.coding` with RxNorm system,
  route/form codings, `drugCharacteristic` (incl. the molecular diagram as ProductImage),
  monograph/indications. RxNorm is the primary coding system; SNOMED/NCI for route/form where available.
- Ingest pipeline (seed-time, run locally) that populates each molecule from open sources:
  - **RxNav / RxNorm API** - RxCUI, ingredient/brand names, FHIR codings.
  - **openFDA** (drug label + NDC) - routes, dosage forms, indications, adverse reactions.
  - **FDA Orange Book** - patent status / exclusivity (best-effort; see risks).
  - **PubChem PUG REST** - 2D molecular structure PNG stored as the item's ProductImage.
- AI-authored narrative fields generated at ingest and stored in Postgres (not at render):
  plain-language summary, on-label vs off-label treatments (off-label clearly labeled),
  side effects summary, FAQ. Each generated fact cites its source.
- RSS: per molecule, aggregate external news/events (Google News RSS query, openFDA
  recall/enforcement, PubMed / clinicaltrials.gov) on a schedule into Postgres, rendered as a
  news panel on the page. **Also emit the app's own outbound feed** per item at
  `/drug/[slug]/feed.xml` (RSS/Atom) so users can subscribe.
- One-pager sections: header (name + ProductImage + FHIR codes), categorical data
  (routes/forms/patent status), on-label & off-label treatments, side effects, FAQ,
  related items, news panel + subscribe link.
- Browse/search: catalog index page with search + filter by class/route/form.
- "Not medical advice" disclaimer sitewide; per-fact source citations; off-label content flagged.

## Non-goals
- No scraping of drugs.com (ToS/legal risk); it is a reference for the target look/fields only.
- No user accounts, auth, favorites, or personalization in v1.
- No cloud deploy, hosted Postgres, or CI/CD in v1 (local-only).
- No e-commerce, pricing, pharmacy, or ordering.
- No broad ingest of the full RxNorm/openFDA corpus - seed set only (~20-50).
- No real-time news; scheduled/cached refresh is fine.
- No clinician decision-support or dosing calculators.

## Constraints
- Stack: Next.js (App Router) + TypeScript; Postgres via `docker compose`; Drizzle ORM
  (lead may substitute Prisma). pnpm. Tailwind for UI. Keep dependencies minimal (ponytail).
- FHIR terminology is mandatory: RxNorm system URI `http://www.nlm.nih.gov/research/umls/rxnorm`
  for `code.coding`; store codings on the record, don't invent ad-hoc codes.
- ProductImage must be a real molecular diagram sourced from PubChem, stored (blob or cached file
  path + URL), not hotlinked at render.
- All external API calls happen at seed/ingest time, not per request; pages read from Postgres.
- Narrative content is LLM-generated but must carry provenance and a disclaimer; off-label labeled.
- Local-only mission: no GitHub push/PR/deploy needed. (If that changes, the orchestrator bridges
  all live GitHub steps - agents prepare artifacts as files/text.)

## Acceptance criteria
- `docker compose up -d && pnpm install && pnpm db:migrate && pnpm seed` populates ~20-50
  medspa-leaning molecules (Semaglutide, Tirzepatide, onabotulinumtoxinA, etc.).
- `pnpm dev` serves a catalog index that browses/searches the seeded items.
- Semaglutide one-pager renders every section fully populated: FHIR RxNorm code visible,
  routes/forms, patent status, on-label + off-label (labeled) treatments, side effects, FAQ,
  related items, PubChem molecular diagram as ProductImage, and a news panel with items.
- `/drug/semaglutide/feed.xml` returns valid RSS/Atom that validates.
- Every narrative fact shows a source; sitewide "not medical advice" disclaimer present.
- A seed self-check asserts each seeded item has: RxNorm code, ProductImage, >=1 route/form,
  and non-empty narrative sections. Ingest is re-runnable (idempotent upsert).

## Affected areas
- New repo at `~/drug-catalog` (nothing in `.botfiles` changes).
- Next.js app: `app/` (catalog index, `drug/[slug]/page.tsx`, `drug/[slug]/feed.xml/route.ts`).
- DB: `docker-compose.yml`, Drizzle schema + migrations, seed script.
- Ingest: `scripts/ingest/` connectors (rxnav, openfda, orangebook, pubchem), narrative generator,
  RSS aggregator + scheduler.

## Risks and unknowns
- **Patent status** is the weakest data point: Orange Book covers small molecules but not biologics
  (Semaglutide/toxins are messy). Treat as best-effort; show "unknown / see source" when absent.
- **openFDA coverage** is uneven for newer/aesthetic drugs; some molecules may lack a label - fall
  back to RxNorm + narrative and flag gaps in the seed self-check.
- **PubChem** returns structures by compound; peptides/biologics (Semaglutide) may render a large
  or awkward diagram - confirm the PNG endpoint works per seed molecule, fallback image if not.
- **RSS aggregation** rate limits / feed shape drift; keep sources swappable and cache aggressively.
- **LLM narrative accuracy** for medical content is a liability - hence mandatory citations,
  off-label labeling, and the sitewide disclaimer. Keep generated claims conservative.
- FHIR MedicationKnowledge vs Medication modeling - lead-data confirms the resource shape early.

## Team plan
- lead-data (claude/opus): Postgres + Drizzle schema (FHIR MedicationKnowledge shape), the seed
  ingest pipeline, and all data sourcing. Owns idempotent seed + self-check.
  - worker-data-ingest (claude/sonnet): connectors - RxNav/RxNorm, openFDA, Orange Book, PubChem
    (ProductImage); LLM narrative generation with provenance.
  - worker-data-feed (claude/sonnet): RSS aggregation (Google News/openFDA/PubMed/clinicaltrials)
    into Postgres + outbound `/drug/[slug]/feed.xml`; scheduled refresh.
- lead-fe (claude/opus): Next.js App Router app - catalog index (browse/search/filter), the
  one-pager layout, ProductImage rendering, disclaimer, Tailwind design. Owns app scaffold + DX
  (compose/migrate/seed scripts wired).
  - worker-fe-onepager (claude/sonnet): the one-pager sections (categorical data, on/off-label
    treatments, side effects, FAQ, related items, news panel + subscribe).
