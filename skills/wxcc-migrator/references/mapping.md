# Mapping reference: CCE / UCCX / others → Webex Contact Center

## Concept map (all platforms)

| Source concept (UCCE/PCCE · UCCX · Avaya · Genesys) | Webex CC destination | Notes |
|---|---|---|
| Dialed Number / Trigger / VDN / Route Point | Entry Point + Entry Point Mapping | The PSTN number must exist in the WxCC number inventory. |
| Call Type / Application | Entry Point (one per routed call type) | Reporting entry and the start of the flow. |
| Routing script / CRS script / vector / strategy | Flow (Flow Designer) | Not bulk-loadable. Rebuild it (see demo 1, prompt-to-flow). |
| Precision Queue / CSQ (skill-based) | Queue, Routing Type `SKILLS_BASED` | The PQ terms become skill requirements in the flow's Queue Contact node. |
| Skill Group / CSQ (resource-group) | Queue + BOOLEAN skill `SG_<name>` | Exact membership is kept through the skill, not through teams. |
| Attribute / Resource skill | Skill Definition | Proficiency 1–10 maps to 0–10, Boolean to BOOLEAN, Text to TEXT. |
| Agent_Attribute values | Skill Profile (deduplicated) | Each agent gets one profile. Agents with the same skill set share it. |
| Agent Team | Team (type AGENT) on a Site | Agents join teams in the Users CSV `Teams` column. |
| Peripheral (agent PG) | Site | The default is the peripheral name. Override with `--site`. |
| Agent + Person | User (Contact Center settings) | The Webex identity must exist in Control Hub first. |
| Supervisor flag / Agent_Team_Supervisor | User Profile = supervisor + supervised teams | The profile name is set with a flag. |
| Reason Code (Not Ready) | Auxiliary Code, Work Type "Default Idle Work Type" | Cisco system codes are skipped. |
| Reason Code (Wrap-up) | Auxiliary Code, Work Type "Default Wrapup Work Type" | |
| ECC / Peripheral variable | Global Variable (STRING) | Only business variables. CVP/ECE/BA plumbing is skipped. |
| Agent Desk Settings / Finesse settings | Desktop Profile | The name is mapped and WxCC defaults are used. Review before go-live. |
| Media Routing Domain | Channel type and Multimedia Profile | Voice→TELEPHONY, chat/WIM→CHAT, email/EIM→EMAIL, SMS/WhatsApp/Facebook→SOCIAL. |
| Business Hours / Holiday | Business Hours / Holiday List | Empty in the sample export. |
| Outbound campaign SGs and call types | Outdial EP / Campaign Manager | Listed in the report, not converted. |
| Task routing MRD / call types | — | Listed in the report, not converted. |

## CCE rules used by `cce_to_wxcc.py`

**Filters.** These are dropped everywhere: `Deleted='Y'`, temporary agents, the `BuiltIn` call type, auto-generated default skill groups (`DefaultEntry=1`, names like `PG.MRD.default.NNNNN`) and the PQ shadow skill groups (`PrecisionQueueID` set).

**Skills**
- Every attribute becomes a skill with the same name and type.
- Every skill group that becomes a queue adds a BOOLEAN skill `SG_<SkillGroup>`. Its members get `True`.

**Skill profiles**
- Each agent's skill set is built from its attribute values plus its SG_ skills.
- Agents with identical sets share one profile.
- Profiles are named `SP_<most common team>`, with `_2`, `_3` and so on for clashes.
- The Description lists the skills, so a reviewer can read it without opening the child rows.

**Queues from precision queues**
- `SKILLS_BASED` routing.
- Agent selection is `BEST_AVAILABLE_AGENT` if any term uses a proficiency attribute, otherwise `LONGEST_AVAILABLE_AGENT`.
- Distribution Group 1 holds the teams of the agents who meet the PQ terms today. If no agent meets them, it holds all teams, and the skill requirements still gate routing.
- PQ steps and terms go into `routing_requirements.json`, for the flow.

**Queues from skill groups**
- Created only for skill groups that have members, unless `--include-empty-queues` is set.
- Outbound, task, social and callback skill groups are skipped and listed in the report.

**Entry points**
- One entry point per call type that a dialed number reaches through `Dialed_Number_Map`.
- The channel is the majority media routing domain of those dialed numbers.
- Telephony entry points go to `07_entry_points.csv`. Chat, email and social ones go to `07b_entry_points_digital.csv`, to load after the Webex Connect assets exist.

**Entry point mappings**
- Numeric voice dialed numbers only.
- Each number is deduplicated across routing clients (CUCM/CVP A/B).
- `--dn-prefix` turns internal DNs into E.164 numbers.

**Aux codes**
- Usage bit 2 (wrap-up) wins over bit 1 (not ready), because bulk import keys on Name.
- The CCE numeric code is kept in the Description, for reporting continuity.

**Global variables**
- The `user.`/`user_` prefix is stripped and non-alphanumeric characters become `_`.
- Type STRING, default value `uninitialized`, Agent Viewable ON, Reportable OFF.

**Users**
- E-mail comes from `Person.Email`. If that is empty and the login name looks like an e-mail, the login name is used. Otherwise it is `<login>@--email-domain`, flagged.
- `External Id` = the CCE agent ID (PeripheralNumber).
- Supervisors also get their supervised teams.

**Multimedia profiles**
- One profile per channel set: Voice only, or Voice + Chat + Email, and so on.
- Capacities come from `--chat-capacity` and `--email-capacity`.
