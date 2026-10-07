# Webex Contact Center Bulk Operations – CSV reference

Bulk Operations is in Control Hub: **Services › Contact Center › Tenant Settings › Bulk Operations › Create Bulk Operation**. Pick the object type, then **Import**. The same page has *Download a sample template* and *Export*.

Sources:
- help.webex.com article **imku7e**, "CSV definition for bulk operations in Webex Contact Center"
- help.webex.com article **31e39g**, "Bulk Operations in Webex Contact Center"

The headers in `scripts/wxcc_bulk_spec.py` follow the column order in article imku7e. If the downloaded template differs, the template's spelling and order win. Update `wxcc_bulk_spec.py` to match and re-run.

## Rules that matter for migration

- **There is no Action column. Import is an upsert keyed on `Name`** (on `Email` for Users). An existing name is updated; a new name is created. Re-running the same file is therefore idempotent. A name collision with an object the tenant already has means you overwrite that object, so check the tenant diff in `migration_report.md` (run with `--existing`).
- **Size limits:** 5000 rows per file. Plan for 5 MB per file; one article says 10 MB, the other 5 MB. Only one bulk job runs at a time.
- **Multi-value cells** are separated by `|`, for example `Team1|Team2`.
- **Parent/child rows:** Skill Profiles and Queues use them.
  - The parent row holds the object.
  - Each child row repeats `Name` and fills only the child columns: one skill per row, or one distribution group per row.
  - A queue import overwrites every distribution group, so always send the full set.
- **Errors:** if a job ends with errors, use *Export errors to CSV*. It adds an `Error Message` column. Fix those rows and re-import only them.
- **Deletes:** bulk import cannot delete objects. The only exception is the `Delete=Yes` column on a skill profile row, which removes that one skill from the profile.
- **Users:** the CSV only sets Contact Center attributes. The person must already exist in Control Hub with a Contact Center licence (use `controlhub_users_to_create.csv`).

## Import order (= file prefix)

| # | File | Depends on |
|---|---|---|
| 01 | auxiliary_codes | The work types "Default Idle Work Type" and "Default Wrapup Work Type", which exist in every tenant |
| 02 | skill_definitions | – |
| 03 | skill_profiles | 02 |
| 04 | multimedia_profiles | – |
| 05 | sites | 04 |
| 06 | teams | 05, optionally 03 and 04 |
| 07 | entry_points (07b digital: after Webex Connect assets) | – |
| 08 | entry_point_mappings | 07, and the PSTN numbers in the tenant |
| 09 | queues | 06, plus the audio file in Default Music in Queue |
| 10 | global_variables | – |
| 11 | desktop_profiles | 01, 06, 07, 09 |
| 12 | users | Control Hub users and user profiles, plus 03, 04, 05, 06, 11 |

Flows are not bulk-loadable. Assign each entry point's flow afterwards, in Flow Designer or through the MCP server.

## Header rows

```
Skill Definition:   Name,Description,Service Level Threshold,Type,List Values For Enum
Skill Profile:      Name,Description,Skill Name,Skill Values,Delete
Multimedia Profile: Name,Description,Type,Voice,Chat,Email,Social
Site:               Name,Multimedia Profile
Team:               Name,Site,Type,Multimedia Profile,Skill Profile,DN,Capacity,Desktop Layout
Auxiliary Code:     Name,Description,Default,Work Type
Entry Point:        Name,Description,Service Level Threshold,Timezone,Channel Type,Social Channel Type,Asset Name
EP Mapping:         Dialed Number,Entry Point,Region
Queue:              Name,Description,Channel Type,Max Time In Queue,Service Level Threshold,Timezone,Permit Monitoring,Permit Recording,Record All Calls,Pause or Resume Enabled,Recording Pause Duration,Default Music in Queue,Routing Type,Skill-Based Agent Selection,Distribution Group,Distribution Group Seq,Group Fallback Time,Group Teams
Global Variable:    Name,Description,Agent Editable,Agent Viewable,Variable Type,Default Value,Reportable,Desktop Label
Desktop Profile:    Name,Description,Parent Site,Screen Popups,Last Agent Routing,Wrap Up Type,Auto Wrap Up Time,Agent Available After Outdial,Allow Auto Wrap Up Extension,Wrap Up Options,Wrap Up Codes,Idle Options,Idle Codes,Transfer Options,Transfer Targets,Buddy Team Option,Buddy Teams,Consult To Queue,Outdial Enabled,Outdial EP,Address Book,Dial Plan Enabled,Dial Plan,Outdial ANI,DN Validation Option,Validation Criteria,Agent Statistics,Queue Statistics Option,Selected Queues,Logged In Team Statistics,Team Statistics Option,Selected Teams,Agent Threshold Alerts Enabled,Agent Threshold Alerts
User:               Email,User Profile,Contact Center Enabled,Site,Teams,Skill Profile,Desktop Profile,Multimedia Profile,External Id,Default DN
Work Type:          Name,Description,Type            (IDLE_CODE | WRAP_UP_CODE)
```

## Value rules

- **Skill**
  - Type: `TEXT|PROFICIENCY|BOOLEAN|ENUM`. It cannot be changed after creation.
  - Name: starts with a letter, at most 80 characters.
  - Proficiency: 0–10. Boolean: True/False. ENUM values are pipe-separated.
- **Team**
  - Type: `AGENT|CAPACITY`. Site and Type cannot be changed later.
  - CAPACITY teams need a DN.
- **Queue**
  - Channel: `TELEPHONY|EMAIL|CHAT`.
  - Routing Type: `LONGEST_AVAILABLE_AGENT|SKILLS_BASED`. It is telephony only and fixed at creation.
  - Skill-Based Agent Selection: `LONGEST_AVAILABLE_AGENT|BEST_AVAILABLE_AGENT`. BEST needs a proficiency skill.
  - Leave Group Fallback Time blank for group 1.
  - Group Teams: `team` or `team: site`.
- **Entry Point**
  - Channel: `TELEPHONY|CHAT|EMAIL|SOCIAL_CHANNEL`. The article spells it "SOCIAL CHANNEL", so check the template.
  - Social Channel Type: `SMS|WHATSAPP|FACEBOOK MESSENGER`.
  - Asset Name is required for chat and email when Webex Connect is used.
- **Global Variable**
  - Name: `[A-Za-z0-9_]`, at most 80 characters.
  - Type: `BOOLEAN|STRING|INTEGER|DECIMAL|DATE TIME`.
  - Desktop Label: at most 50 characters. String default: at most 256 characters.
- **Desktop Profile**
  - Wrap Up Type: `MANUAL|AUTO`.
  - Option columns take `ALL|SPECIFIC`; the Buddy, Queue and Team stats options also take `NONE`.
  - DN Validation: `UNRESTRICTED|PROVISIONED VALUE|VALIDATION CRITERIA`.
- **Multimedia Profile**
  - Type: `BLENDED|BLENDED_REALTIME|EXCLUSIVE`.
  - Voice: 0–1. Chat, Email and Social: 0–5 each.
- **User**
  - Contact Center Enabled: `On|Off`.
  - Desktop Profile is required when Site and Teams are set.
