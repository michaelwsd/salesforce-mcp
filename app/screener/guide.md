# Investment Screener Guide

How to build a two-page AA screening memo (.docx) in the current house format with the
Armitage Salesforce MCP. The user asks in plain language ("screen Acme", "build a
screener from this IM"); follow this guide end to end without asking them to run
anything. `build_screener` produces a draft for the user to review; only after they
approve it does `approve_screener` attach it to the deal in Salesforce. **Always draft,
then approve: never attach a screener the user has not explicitly approved.**

**Reference standard: `Screener_Project Bundaberg.docx` (Sep-2026).** Screeners older than
about July 2026 predate the current revenue-stream bullets and number conventions; do not
copy them.

## The AA mandate (the test every screener is written against)

Owner-operator seeking **$10-30m** of capital and a partner to jointly develop and execute
a growth plan; business generating **$2-10m of profit**; **Australia / New Zealand** head
office. State fit or misfit plainly. A 100% exit with no owner-operator rolling equity is
a misfit. Say so; do not soften it.

## Workflow

1. Gather everything (in parallel), including finding the deal in Salesforce
2. Score the thesis and Porter's forces before writing
3. Write the screener spec (a JSON object)
4. Call `build_screener`; fix any errors it returns and call it again
5. Quality check
6. Reply with the draft download link and a two-to-three sentence summary, then stop
7. Revise on feedback (new draft each time); on explicit approval, call `approve_screener`

---

## Step 1 - Gather (in parallel)

Run these at the same time, not one after another.

1. **Attached documents** (IM, teaser, CIM, flyer, meeting notes). The primary source of
   truth. Read every page; PDFs often render as images. Extract the business description,
   financials, revenue mix, ownership, transaction details, advisor and process dates.
2. **Salesforce.**
   - `search` for the company (and obvious bolt-ons), e.g.
     `FIND {Acme} IN NAME FIELDS RETURNING Opportunity(Id, Name, StageName), Account(Id, Name)`.
     Note the Opportunity ID: the screener is attached to it.
   - `get_company_overview` on the Opportunity (stage, owner, notes, activities, emails, files)
   - `get_notes` and `get_emails` for prior conversations. A prior approach that was
     killed, and why, is material to the recommendation.
   - `list_files` / `download_file` for IMs, and for any earlier screener on the deal
     (titles start `Screener_`)
   - **Not in Salesforce yet?** Note it, but do not create anything now. If the user
     approves the screener, `create_deal` creates the Account and Opportunity at that
     point (Step 7). Never create a duplicate when `search` finds the company.
4. **Public research.** Company website, LinkedIn, news, ASIC / NZ Companies Office
   filings, market size and growth, named competitors, comparable transactions. Search
   the company name with "Australia", "revenue", "EBITDA", "acquisition", "private equity".

**Synthesise.** Combine sources and be explicit about confirmed versus inferred. Where a
fact is not available, write `[TBC]` (or rate `TBC`). Never guess a number. Where the IM
makes a claim, say it is the IM's claim. Where a number is normalised, say by how much.

## Step 2 - Score before writing

Rate the five thesis criteria (`Y` / `N` / `TBC` / `Y/TBC` / `N/TBC`) and five Porter's
forces (`L` / `M` / `H` / `L/M` / `M/H`) first, with the evidence for each. The ratings
drive the recommendation, so settle them before drafting prose. `TBC` means the
information is not available, not "I would rather not say".

---

## Step 3 - Write the spec

The spec is the `spec` argument to `build_screener`. The complete example at the end of
this guide shows every field; replace every value. All dollar values are A$m numbers; all
percentages are numbers (`47.1`, not `"47%"`).

### Metadata

| Field | Content |
|---|---|
| `project_name` | AA codename, upper case: `"PROJECT BUNDABERG"` |
| `company_name` | Real company name, shown in brackets after the codename |
| `author_initials` | Deal team initials, right-aligned on the title line: `"APC / RMD"` |
| `date` | Month and year: `"October 2026"` |
| `source_note` | Footer attribution: `"Source: X IM (Sep-2026); management accounts; AA analysis"` |
| `fin_note` | One-sentence data-quality note under the financial header: basis, year end, what is forecast |

### Business & industry overview

**`lead_para`** - opening paragraph, no bold prefix. What it sells, to whom, where;
founded year, HQ, FTE and sites; latest revenue and adj. EBITDA with margin.

**`revenue_streams_intro`** - period, total, and the single most important structural
fact about the mix: `"FY26A $9.5m; 90.6% is the one-off sale of the unit."`

**`revenue_streams`** - one sub-bullet per division: `{name, pct, value_m, description}`.

> **House style. This is a named requirement; get it right.**
>
> Renders as: **Division Name (47.1%, $9.9m)** – description
>
> 1. `build_screener` renders the bold name and **(percentage, dollars)**, both to one decimal
>    place. Give `pct` and `value_m` as numbers.
> 2. Lead the description with an **active verb**: "Tests and models", "Calibrates and
>    certifies", "Builds and sells". Not a noun-string of capability names.
> 3. Say **why the customer has no choice**: "required before goods can be legally sold",
>    "so readings hold up in court", "hardware is inert without it". The regulatory or
>    structural driver *is* the business model.
> 4. End with the **charging basis** or the key structural limit: "fee-for-service",
>    "per-test fee", "annual per-unit subscription, c.$270", "VIC only", "its only
>    customer in this division".
> 5. **No staff counts.** "(17 staff)" was once mistranscribed as 17% against an actual
>    24%. FTE goes in `lead_para`. Staff counts here are rejected.
> 6. Percentages must sum to 100.0%; anything else is rejected.
>
> Worked example (the reference standard):
>
> - **Acoustics & Vibration (47.1%, $9.9m)** – Tests and models noise, vibration and wind
>   on buildings, infrastructure and machinery; fee-for-service
> - **Safety & Performance (24.0%, $5.0m)** – NATA-accredited product testing and
>   certification required before goods can be legally sold; per-test fee
> - **Traffic Systems (13.7%, $2.9m)** – Tests and calibrates speed and red-light cameras
>   so readings hold up in court; long-term contract with the Victorian Government, its
>   only customer in this division

**`business_items`** - the remaining labelled bullets, as `{label, text}`, in this order:

- `Revenue model` - charging basis; recurring versus one-off share; gross margin;
  retention or churn, or say plainly that none is disclosed.
- `Go-to-market` - how it wins customers; accreditations or panels that are the licence
  to operate; customer concentration.
- `Demand driver` (optional) - the government program or market tailwind, one sentence.
  Name specific products and OEM/partner brands where they matter to the thesis.

### Financial overview

`build_screener` draws three things side by side: a combo chart, a revenue-mix donut, and the
chart notes.

**`financials`**

| Field | Content |
|---|---|
| `periods` | `["FY23A", "FY24A", "FY25A", "FY26A", "FY27F"]`. Actuals end in `A`, forecasts in `F`. Half-years allowed (`"H1 FY26A"`). |
| `revenue`, `earnings` | A$m, one decimal place, same length as `periods`, no nulls |
| `earnings_metric` | `"EBITDA"`, `"Adj. EBITDA"`, `"EBIT"` or `"Adj. EBIT"`. Use **EBIT for D&A-heavy businesses** (manufacturing, infrastructure, asset-heavy services); EBITDA for most others. |
| `gross_margin_pct` | GP margin % per period, or `null` if not disclosed (the line is omitted) |
| `callout` | Optional `{period, text}` box for a period that needs explaining (one-off contract, demand surge). Keep the text to two short lines with `\n`. |

The chart shows revenue and earnings bars, earnings margin % under each period, the GP
margin line, year-on-year growth arrows and a CAGR arrow. **Growth arrows and CAGR use
full-year actuals only** (`FYxxA`); forecasts and half-years are shown but excluded.
Negative values render below a zero line in brackets. Forecast bars are lighter.

**`revenue_mix`** - donut segments `{label, pct}`, one or two words per label, summing to
100.0%; up to six segments, coloured in AA blues automatically. `revenue_mix_period`
(optional) sets the period shown; default is the latest actual.

**`chart_notes`** - four to six short caveat bullets beside the charts. **This is where the
screener earns its keep.** Cover data quality and period basis; the trend the chart
flatters; normalisations as a share of reported EBITDA; anything outside the transaction
perimeter (related-party property, owner salary not drawn); what the forecast is actually
asking for.

### Transaction dynamics, recommendation & next steps

**`transaction.lead`** - paragraph above the table: ownership (who owns what); what is
being sold and the structure (minority / majority / full exit); whether vendors stay or
roll equity; where adj. EBITDA sits against the $2-10m band; explicit mandate fit or
misfit. **No EV or valuation** unless the IM states one.

**`transaction.source`** - intermediated or direct; advisor firm, city and contact name
(**no email addresses**); IM date and AA recipients; process milestones and dates.

**`transaction.recommendation`** - renders bold dark red in the "Next steps" row:

- `verdict`: `"Pass"`, `"Proceed"` or `"Further diligence"`. Rendered first.
- `rationale`: two or three reasons for and against. If GP margin is low (~10%), flag a
  likely commoditised, price-driven product.
- `gates`: specific, actionable next steps rendered as `(1) ...; (2) ...; (3) ...` - data
  requests, product catalogue review, network discussions, GP margin by segment, contract
  terms to test.

**`transaction.other_niches`** - IM-flagged adjacencies first, then two to four adjacent
niches that would fit the thesis (a niche is the intersection of industry and business
model, e.g. "student wellbeing software", "superannuation fund admin solutions"), and any
AA thematic or portfolio company overlap.

### Investment thesis criteria

The two category headers and five criteria are **fixed**; `build_screener` supplies them
and rejects unknown keys. Provide `{rating, evidence}` for each key:

| Key | Criterion | Evidence guidance |
|---|---|---|
| `growing_high_margin` | Growing, high margin | Revenue CAGR over **actual years only**; GP and EBITDA (or EBIT) margin for the latest actual year |
| `recurring_revenue` | Recurring revenue | One sentence: transactional versus contractually recurring |
| `differentiated` | Differentiated service/product with high barriers to exit | Switching costs, IP, accreditation, relationships; if `TBC`, say what must be validated |
| `large_growing_market` | Large and growing market with barriers to entry | One or two sentences; lead with the strongest stat (TAM, growth rate, government program) |
| `fragmented_end_market` | Fragmented end market | One sentence: customer profile and concentration |

Evidence is two sentences maximum. Lead with the number or verdict, then the counter-fact.
Be critical, especially where data comes from an IM; almost every criterion has a
qualifier, and a screener that finds none has not looked.

Good: `"Revenue CAGR 4.4% FY24A-FY26A, +0.7% in FY26A; adj. EBITDA -17.0% to $2.3m at
10.8%. A 48.0% gross margin does not reach the bottom line."`

Bad: `"The business has demonstrated solid revenue performance over the historical
period, supported by a healthy gross margin profile."`

### Porter's five forces

Keys: `supplier_power`, `buyer_power`, `competitive_rivalry`, `threat_of_substitutes`,
`threat_of_new_entrants`, each `{rating, commentary}`. Rate **industry structure**, not
the company's individual strengths. Two sentences maximum: the structural driver, then the
qualifier or mitigant. Name competitors where known. No claims that cannot be validated
from the IM or public sources.

---

## Number conventions (apply everywhere)

- **Percentages to one decimal place**: 4.4%, 47.1%, 8.3%. Not 4.43%, not 47.10%. Two
  decimals imply precision unaudited management accounts do not support. For an
  approximate claim from an IM, use `~` (`~99% repeat spend`).
- **Values in A$m to one decimal place**: $19.2m, never $19,205k or 19,205.
- **Negatives in brackets** in charts: `(2.7)`, `(17.0%)`.
- Compact forms: `$13.1m`, `~30%`, `FY25A`, `H1 FY26A`, `incl.`, `approx.`, `GP`, `ARR`, `GTM`.

`build_screener` formats every chart label and the revenue-stream brackets itself, rejects
two-decimal percentages and thousands-formatted dollars anywhere in the text, and warns
on whole-number percentages.

## Tone

The reader is a busy Investment Director. Dense with signal, free of noise.

- No marketing language. No adjective that does not carry data: "leading", "robust",
  "innovative" all mean nothing.
- Key number first, then context: `"~85% recurring"`, not `"the business generates
  approximately 85% of its revenue on a recurring basis"`.
- Telegraphic; semicolons pack facts into one line rather than splitting sentences.
- Cut anything that restates the rating (`"Supplier power is low"`), anything the reader
  infers from Y/N/H/M/L, and any sentence opening `"The business..."` or `"It is worth
  noting that..."`.
- `[TBC]` for every gap; never leave a blank and never guess.

---

## Step 4 - Build the draft

Call `build_screener(spec)`.

- **Errors** (sums not 100.0%, wrong ratings, unknown criteria, staff counts, thousands,
  two-decimal percentages) mean nothing was built. Fix every error in the spec and call
  again. Do not ask the user to fix them.
- **Warnings** are returned alongside a successful build. Fix them and rebuild unless
  there is a reason not to (e.g. a whole-number percentage quoted from the IM).
- A successful build returns a `draft_id` and a `download_url` (valid 24 hours). The draft
  is stored privately in Salesforce and is not attached to any deal yet.

## Step 5 - Quality check

- [ ] `build_screener` returned no errors and every warning is resolved or deliberate
- [ ] **Two pages.** If it runs to three, cut content; do not reformat
- [ ] Title reads `SCREENING MEMO – PROJECT X (Company)`, initials right-aligned
- [ ] Revenue-stream bullets follow the house style (active verb, why no choice, charging basis)
- [ ] Chart labels are not clipped or overlapping; the callout (if any) points at the right bar
- [ ] `chart_notes` names at least one thing the chart flatters
- [ ] Mandate fit stated explicitly, not hedged
- [ ] Recommendation opens with the verdict and lists numbered gates
- [ ] Every gap is `[TBC]`; no guessed numbers

## Step 6 - Hand over the draft, then stop

Reply with the `download_url` (the user clicks it to download the .docx and review it in
Word), then a two-to-three sentence summary of the recommendation only. Do not repeat the
memo. Say whether the company is already in Salesforce, and that you will attach the
screener to the deal once they approve. Then **stop and wait**. Do not call
`approve_screener` in the same turn, even if the user asked to "just upload it".

## Step 7 - Revise or approve

- **Changes requested:** update the spec and call `build_screener` again. Each build is a
  new draft with a new link; send the new link and wait again.
- **Approved** ("looks good", "approve", "upload it" after seeing the draft): call
  `approve_screener(draft_id, opportunity_id)` with the `draft_id` of the draft they
  reviewed. If the company is not in Salesforce, first call `create_deal` (company name,
  industry, city, source type) and use the Opportunity ID it returns. Reply with the
  `file_url` and say if you created a new Account/Opportunity.
- **Link expired** (after 24 hours): rebuild from the same spec to get a fresh link.
  Unapproved drafts are deleted after 7 days.

---

## AA format reference (implemented by build_screener; do not change)

| Parameter | Value |
|---|---|
| Page size | A4, 11906 × 16838 twips |
| Margins | Top 567, Bottom 568, Left/Right 1134 twips |
| Content width | 9628 DXA |
| Teal (Accent1) | `#156082`: category headers, section rule, revenue bars |
| Navy (dk2) | `#0E2841`: title, section titles, chart annotations |
| Section header | `#F2F2F2` fill with teal top rule; a one-cell table so it is flush with the tables |
| Recommendation text | `#9C0006` bold |
| Body font | Calibri 9pt; section titles 10pt bold; table cells 9pt; chart notes 7.5pt |
| Thesis col widths | 2830 / 738 / 6060 DXA |
| Porter col widths | 2543 / 603 / 6482 DXA |
| Source table widths | 2819 / 6809 DXA |
| Chart box inner cols | 4900 / 2150 / 2458 DXA |
| Chart image widths | main 3.40in, donut 1.49in |
| Cell margins | 30 DXA top/bottom, 60 DXA left/right |
| Footer | Source attribution left, `Page X of Y` right |

## Troubleshooting

| Problem | Fix |
|---|---|
| "must be numbers, not strings" | Give `pct`, `value_m` and financials as numbers: `47.1`, not `"47.1%"` |
| "sum to 99.9%, must be 100.0%" | Rounding drift; adjust the largest segment so the total is exactly 100.0 |
| No growth arrows or CAGR | Needs at least two full-year actual periods (`FYxxA`) |
| Revenue rejected as thousands | Convert to A$m: 19,205 -> 19.2 |
| Legend text clipped | Shorten `revenue_mix` labels to one or two words |
| Runs to three pages | Cut words: chart notes, thesis evidence and Porter commentary first |
