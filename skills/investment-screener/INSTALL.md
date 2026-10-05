# Installing the Investment Screener skill

Refreshed 6-Oct-2026. Supersedes both the Sep-2026 `investment-screener` skill and the
older `screen` skill; this single skill combines them (see "Where this came from").

## What's in this folder

```
investment-screener/
├── SKILL.md                    <- the instructions Claude reads
├── INSTALL.md                  <- this file
├── scripts/
│   ├── build_screener.py       <- validates a JSON spec and builds the .docx
│   └── fix_xml.py              <- OOXML repair (run automatically by the build)
└── examples/
    └── example_spec.json       <- fictional, complete spec to copy from
```

## Install

1. Copy the whole `investment-screener` folder into your Cowork skills directory:
   - **Windows:** `%APPDATA%\Claude\cowork\skills\`
   - **macOS:** `~/Library/Application Support/Claude/cowork/skills/`

   Keep the folder name `investment-screener`. Remove the old `screen` skill if you have
   it, so the two do not both trigger.
2. Restart Cowork so the skill is picked up.
3. Test: **"Screen [company name]"**, or upload an IM and ask for a screener.

## Dependencies

`python-docx`, `matplotlib` and `numpy`. Claude installs them on first run if missing.
Charts use Calibri; on a Mac with Microsoft Office the script finds Office's bundled
copy automatically.

## Worth knowing

- **Content goes in a JSON spec, not in Python.** Claude no longer edits a template
  script. The build script owns the layout and enforces the house rules: revenue-stream
  and donut percentages sum to 100.0%, one-decimal percentages, values in $m, no staff
  counts in revenue-stream bullets, fixed thesis and Porter rows, valid ratings and
  verdicts. A spec that breaks a rule is rejected with a message saying what to fix.
- **Output path is not hard-coded.** Claude asks where your AA Investment Screener
  folder is. The file is built in a temporary directory and copied in complete, so
  building straight into a OneDrive-synced folder no longer produces a corrupt file.
- **Transaction dynamics is populated**, matching current practice. If the INV team
  wants it blank, delete the section after building.
- **Salesforce:** if the Armitage Salesforce MCP is connected, Claude checks it for prior
  contact, notes and emails on the company before writing the recommendation.

## Where this came from

| Taken from the Sep-2026 `investment-screener` skill | Taken from the older `screen` skill |
|---|---|
| Two-page house format, colours, margins, column widths | Gathering sources in parallel, incl. public research queries |
| Revenue-stream bullet house style and worked example | Score the thesis before writing |
| One-decimal number conventions, values in $m | `[TBC]` for every gap, never guess |
| Revenue-mix donut and chart notes | EBITDA vs EBIT choice for D&A-heavy businesses |
| Mandate test, verdict-first recommendation in dark red | Brackets for negatives; callout box for unusual periods |
| Tone rules, quality checklist | Per-criterion thesis guidance; Porter claims must be verifiable |
| `fix_xml.py` repair step | Flush table alignment; "other niches" definition; no EV unless in the IM |

Where the two disagreed, the newer house format won: two pages rather than one,
one-decimal rather than whole-number percentages, chart notes rather than "no commentary
below the chart", and a lead paragraph rather than four fixed bullets.

## Known gap

The Sep-2026 skill said the thesis table has **three** category headers and **six**
criteria but never listed them. The only screener available when this skill was merged
(Project Dark Horse, Mar-2026) and the older `screen` skill both use **two** headers and
**five** criteria, so that is what the script renders. If `Screener_Project Bundaberg.docx`
has a third header and sixth criterion, add them to `THESIS` at the top of
`scripts/build_screener.py` and to the thesis table in `SKILL.md`.
