---
name: wxcc-migrator
description: Migrates legacy contact center configuration (Cisco UCCE/PCCE, UCCX, Avaya, Genesys, Five9) to Webex Contact Center (WxCC). Use it whenever someone has a CCE ICMDBA configuration export (folder of binary .raw files such as Agent.raw, SkilGrou.raw, PrecQueu.raw, plus a Version file) and wants it readable or converted. Use it when they need WxCC Bulk Operations CSVs (skills, skill profiles, teams, users, queues, entry points, DN mappings, aux codes, global variables, desktop and multimedia profiles), want to map legacy routing objects (call types, precision queues, skill groups, ECC variables, reason codes) to WxCC, or want to provision WxCC idempotently through the Webex CC MCP tools.
---

# WxCC Migrator

This skill takes a legacy contact center configuration and produces Webex Contact Center configuration that can be loaded.

For Cisco CCE it runs a tested three-stage pipeline: **binary export → readable tables → WxCC bulk-upload CSVs**. Every stage leaves an artifact a person can review. For other platforms, apply the same mapping rules to whatever export you have.

## Pipeline at a glance

```
<CCE export>/*.raw ──decode──▶ 1-decoded/*.csv|json  ──transform──▶ 2-wxcc-bulk/NN_*.csv ──validate──▶ validation_report.md
   (bcp native)              (+ _DECODE_SUMMARY.md)               (+ migration_report.md,
                                                                     routing_requirements.json,
                                                                     flow_inventory.csv, crosswalk.csv)
```

The scripts are in `scripts/`. They use only the Python 3 standard library.

| Script | Purpose |
|---|---|
| `run_migration.py <export> <run_dir> [opts]` | Runs all three stages in one go. |
| `cce_decode.py decode <export> <out>` | Turns .raw into CSV/JSON (passwords masked). Unknown tables get a preview file. |
| `cce_decode.py walk/profile <file.raw> "<layout>"` | Works out the layout of a table that is not decoded yet (hybrid step). |
| `cce_decode.py roster <decoded_dir>` | Rebuilds `_agent_roster.csv` (agents with names and teams). |
| `cce_to_wxcc.py <decoded> <out> [opts]` | Produces the WxCC bulk CSVs and the report. |
| `validate_wxcc_csv.py <bulk_dir>` | Checks headers, enums, naming rules, duplicates and cross-file references. |

## Workflow

### 1. Recognise the input

A folder with many short-named `.raw` files and a `Version` file is a **CCE ICMDBA export**. Continue with step 2.

Anything else (UCCX XML, Avaya/Genesys CSV or JSON) has no decoder. Parse it, then follow `references/mapping.md` directly.

Never modify the source export. Write everything into a run folder, for example `demo2-run1/`.

### 2. Decode the binary files into readable tables

```bash
python3 scripts/cce_decode.py decode "<export_dir>" "<run_dir>/1-decoded"
```

Open `_DECODE_SUMMARY.md` and show the user what came out: decoded tables with row counts, empty tables, and tables that still need a layout.

Show one or two readable tables as proof. For agents, use `_agent_roster.csv`: decode writes it automatically by joining Agent, Person and the team tables (agent ID, name, login, teams, supervised teams). Don't write a one-off join. `PrecQueu.csv` is another good example. Show a small sample, not the full PII list.

The format itself (SQL Server bcp native) is explained in `references/cce-raw-format.md`. Read it if you need to explain why the files are not readable, or before extending the decoder.

### 3. Hybrid step: extend the decoder when a needed table is missing

The decoder ships with layouts for 27 tables, which cover everything the core migration needs.

If the migration needs another table and it is listed under *Needs a layout* (for example Business_Hours on another export, or Campaign), work out the layout live:

1. Read `1-decoded/_unknown_preview/<File>.txt`.
2. Run `walk` with a draft layout until `next @N` lands on the start of row 2.
3. Run `profile` until it prints `all bytes consumed` and the values look plausible.
4. Add the layout to `references/cce_schemas.json` and re-run `decode`.

The tells and the type codes are in `references/cce-raw-format.md`.

Only name a column when the data proves what it means. Otherwise keep `c<N>`.

### 4. Gather the tenant-specific values

Ask the user for these, or take the defaults and say so in your summary:

- `--site`: WxCC site name. Default: the CCE agent peripheral name.
- `--timezone`: default `America/New_York`.
- `--dn-prefix`: turns internal CCE dialed numbers into tenant E.164 numbers, for example `+1919555`. Without it the mappings carry the raw digits and get flagged.
- `--email-domain`: used for agents without an e-mail in CCE. Default `example.com`, which is flagged.
- `--agent-user-profile` / `--supervisor-user-profile`: must match the user profile names in the tenant.
- `--existing <tenant export>`: a create-vs-update diff against the current tenant. Use the export file if there is one (for example `wxcc_config_export.txt`). Otherwise build it from the MCP `list` tools.
  - Check that the file exists before you pass it. A wrong path stops the transform.
  - If there is no export, run without `--existing`. Both reports then say the diff was **not performed**. Tell the user plainly that existing objects can't be confirmed, and offer the MCP check.

Any timezone or user profile name the user didn't supply is filled with a default. That default is recorded in `2-wxcc-bulk/_run_context.json` and shown as a warning in both reports. Pass the real values to clear those warnings.
- `--include-empty-queues`, `--chat-capacity`, `--email-capacity`: optional.

### 5. Transform and validate

```bash
python3 scripts/run_migration.py "<export_dir>" "<run_dir>" --existing <tenant_export> [options]
```

The run must end with **0 validation errors**. If it does not, fix the cause in the transform options, or in the code if it is a real bug. Do not hand-edit CSVs without noting it in the report.

Warnings are expected. Most are placeholder e-mails and non-E.164 numbers. Summarise them, do not hide them.

### 6. Present the result

Show the user:

- A table of bulk files in import order, with row counts (from `migration_report.md`).
- The tenant diff, and any name collisions that would update existing objects. If the diff was not performed, say so first, not as a footnote.
- The *Needs a human* list: flows, phone numbers, identities, digital assets, desktop profile review.
- `routing_requirements.json`: the skill requirements per queue, ready for the flow builder (demo 1, prompt-to-flow).

Remind the user that bulk import upserts by Name. Re-running is safe, and there is no bulk delete.

### 7. Optional: provision through MCP instead of CSV

Do this only if the user asks to push configuration through the Webex CC MCP server (`webexccconfig` tools):

- Follow the same import order as the CSVs.
- **Check before you write.** For every object, `list`/`get` by name first, then create only if it is missing, otherwise update.
- **Validate before you send.** Check every payload against the schema expected by the MCP tool.
- Confirm with the user before the first write to a tenant. Report per-object results.
- Keep the source-specific parsing (decoded CSVs) separate from the provisioning calls.

## Mapping essentials

The full rules are in `references/mapping.md`.

| CCE | WxCC |
|---|---|
| Attribute | Skill (Boolean→BOOLEAN, Proficiency→PROFICIENCY 0–10) |
| Agent attribute values | Skill Profile, deduplicated per identical skill set |
| Precision Queue | Queue, SKILLS_BASED; terms → `routing_requirements.json` |
| Skill Group (with members) | Queue + BOOLEAN skill `SG_<name>` |
| Agent Team | Team (AGENT) on the Site |
| Agent + Person | User (needs the Control Hub identity first) |
| Call Type reached by a DN | Entry Point; telephony in 07, digital in 07b |
| Dialed Number (numeric, voice) | Entry Point Mapping |
| Reason Code (non-system) | Aux code, Idle or Wrap-up work type |
| ECC variable (business) | Global Variable |
| Agent Desk Settings | Desktop Profile (name + WxCC defaults) |
| Routing script (Script_Data) | Not converted. Listed in `flow_inventory.csv` for a flow rebuild |

## Guardrails

- Passwords stay masked. Do not copy the PII from decoded tables into chat beyond what the user needs to see.
- Do not invent phone numbers or identities silently. Placeholders are always flagged in both reports.
- Keep decisions traceable. `crosswalk.csv` maps every CCE ID to its WxCC name.
- The Bulk Operations column spellings come from the Webex help article (`references/wxcc-bulk-csv.md`). If a tenant's downloaded template differs, update `scripts/wxcc_bulk_spec.py` and re-run.
