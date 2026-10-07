---
name: wxcc-flow-builder
description: Build, lint and emit Webex Contact Center FlowV2 JSON from a Python spec with flowkit, then deploy it through the WxCC MCP server. Use when creating or changing a Flow Designer flow (voice IVR, queueing, OTP, AI Agent hand-off) from a design document or customer profile (<customer>.md).
---

# WxCC Flow Builder (flowkit)

**Sources, in order of authority:**
1. The official [Flow Orchestration guide](https://developer.webex.com/webex-contact-center/docs/api/guides/flow-orchestration): document format, edges, validate/import/save/patch.
2. `wxcc-describe-activity`: per-activity inputs, outputs and ports.
3. UI-built flows in the tenant, for shapes `describe` does not expose (set-variable).
4. Validator probes.

`FLOW_BUILDER_LEARNINGS.md` §11 marks every rule as documented or observed only.

Write flows as a short Python **spec**, not hand-written JSON. `flowkit.py` turns the spec into FlowV2 JSON and **lints it offline** against tested port rules, so most validator errors are caught before any MCP call.

```
.claude/skills/wxcc-flow-builder/
├── SKILL.md                 # this file
├── scripts/flowkit.py       # builders + lint + compact emit (stdlib only)
├── references/ports.json    # tested edge conditions per activity (update when the platform changes)
└── examples/MPSA.flow.py    # full reference spec: 57 nodes, OTP, AI Agent, overflow
```

## Workflow

1. **Spec.** Copy `examples/MPSA.flow.py` to `build/<Flow>.flow.py`. Replace the tenant ID constants at the top with values from `<customer>.md` §4, then the prompts, variables, nodes and edges.
2. **Build + lint.**
   ```bash
   python3 .claude/skills/wxcc-flow-builder/scripts/flowkit.py build build/<Flow>.flow.py -o build/<Flow>.flowv2.json
   ```
   Fix every `ERROR` and rebuild. `WARN` lines about `<node>.<output>` references are the known FC1038 behaviour (see below).
3. **Deploy.** Read the generated file and pass its content inline:
   - New flow: `wxcc-create-flow` with the **full** flow in one call. No skeleton step is needed (57 nodes / 50 KB worked in one call).
   - Existing flow: `wxcc-save-flow-draft` (`flow_id`) with the full rebuilt flow.
   - **Never use `wxcc-patch-flow-draft` on a flow that contains HTTP nodes.** Even a patch that touches only other nodes downgrades every `http-request-v2` node to legacy `http-request` and drops its URL and `error` edges (observed 2026-10-07).
   - Run a dry-run `wxcc-validate-flow` (`flow`) first **only** when the user wants a tenant check before committing. Otherwise local lint is enough.
4. **Validate the draft.** `wxcc-validate-flow` with `flow_id`. Compare with the expected-errors table below and fix only unexpected errors.
5. **Never publish.** No MCP tool publishes, and publishing is a human step in Flow Designer.

## Builder cheat-sheet (`f = Flow(name, description)`)

| Call | Activity | Edge conditions |
|---|---|---|
| `f.start("NewPhoneContact", desc)` | start | `out` |
| `f.setv(name, desc, (var, TYPE, value), ...)` | set-variable | `out`, `error` |
| `f.cond(name, "{{ expr }}", desc)` | condition-activity | `true`, `false`, `error` |
| `f.play(name, pid, text, desc, interruptible=True)` | play-message | `default`, `error` |
| `f.music(name, desc, prompt, seconds)` | play-music | `default`, `error` |
| `f.business_hours(name, bh_id, desc)` | business-hours | `workingHours`, `holidays`, `override`, `default`, `error` |
| `f.collect(name, pid, text, desc, min_digits, max_digits, timeout)` | ivr-collectdigits | `""` (valid), `timeout`, `invalid`, `error` |
| `f.menu(name, pid, text, desc, {"1": "Label", ...}, timeout)` | ivr-menu | the digits, `timeout`, `invalid`, `error` |
| `f.http(name, url, desc, method, body, timeout_ms)` | http-request-v2 | `default`, `error` (also `success`/`failure`/`timeout`/`out`) |
| `f.virtual_agent(name, agent_name, desc)` | ivr-virtualassistantvoice | `ENDED`, `ESCALATE`, `error` |
| `f.queue(name, queue_id, label, desc)` | queue-contact | `default` **only** |
| `f.queue_lookup(name, queue_id, desc)` | queue-lookup | `""` (normal), `insufficientdata`, `failure` |
| `f.callback(name, dn_expr, queue_id, desc)` | callback | `default`, `failure` |
| `f.disconnect(name, desc)` | disconnect-contact | none |
| `f.event_flow(); f.event("GlobalErrorHandling", desc)` … `f.main_flow()` | event | `out` |
| `f.var(...)`, `f.secure_var(...)` | variables | `secure_var` sets isSecure, hides from CAD and reporting |
| `f.edge(frm, to, *conds)` | edge per condition | |
| `f.retarget(old_to, new_to)` | redirect edges (e.g. insert a pre-queue step) | |

## Platform facts encoded in flowkit (do not rediscover)

- **Collect Digits** has no "store in variable" or "retries" input. Copy `{{<node>.DigitsEntered}}` with `setv`, and build retries with a counter + `cond` loop.
- **Get Queue Info** outputs `{{<node>.PIQ}}` / `{{<node>.EWT}}`. EWT is assumed to be milliseconds (confirm in test).
- **Virtual Agent** outputs `{{<node>.MetaData}}` (JSON). Read fields with `| jsonPath('$.field')`.
- **HTTP** response is `{{<node>.httpResponseBody}}`; parse with `jsonPath` in `setv`. `outputVariableArray` is **not** checked by the validator (it even accepts undeclared variables), so its shape is unverified.
- Name the start node **`NewPhoneContact`** so `{{NewPhoneContact.ANI}}` resolves.
- **Set Variable entries are keyed by `srcVariable`** (plus `srcVariableType` and an `id`), with the value in both `literal` and `expr` under `set-to-literal`. This shape is copied from a Cisco UI-built flow. Entries keyed by `variable` pass validation but open **empty** in Flow Designer, and lint now rejects them.
- Clear a variable with `""` or `"''"`; flowkit emits `{{ '' }}`. A literal `""` is rejected.
- TTS nodes need only `connector`, `toggle`, `voiceLanguage`, `promptsTts`. Compact output drops the rest (`--full` keeps them).
- `wxcc-save-flow-draft` keeps `http-request-v2` and `eventFlows` intact. The diagram `group` shows `http-request` for v2 nodes too; that is not a downgrade, so check `properties.activityName`.
- HTTP nodes carry the same default fields as a node dropped in Flow Designer (`httpRequestHeaders:{}`, `httpQueryParameters:{}`, `*Body*: null`).
- Every edge carries `properties.value = condition`, as UI-built flows do; the documented edge `id` is the PATCH key.
- The document carries `contactType: telephony` and `preferences`, per the official guide.

## Expected validator results (report, don't chase)

| Code | Cause | Action |
|---|---|---|
| FC1015 on `ivr-virtualassistantvoice` | AI Agent not yet created in AI Agent Studio | Unresolved external dependency in BUILD_REPORT |
| FC1038 "Variable '<NodeName>' is referenced but not declared" | **False positive.** The MCP validator flags every `<node>.<output>` reference, including those in Cisco's own published `Record_Agent_Greeting`. | Keep the references and report them as expected. If Flow Designer shows the Set Variable node empty, the entry shape is wrong (see above), not the reference |
| FC1007 | Missing description | Prevented by flowkit (mandatory `desc`) |

## Lint rules (`flowkit.py lint <flow.json>`)

Lint checks:
- edge conditions are valid for each activity, and every required port is connected (no dangling ports);
- no port has duplicate edges;
- every node is reachable (main flow from start, event flows from the event node);
- node names are unique;
- every node has a description;
- required properties are present;
- secure variables are not on the desktop (CAD) or reportable;
- every `{{ }}` reference is declared (flow variable, `Global_*`, `NewPhoneContact`, or a node output, which raises a warning).

When the live validator rejects something that lint accepted, update `references/ports.json` or `flowkit.py` and add the fact to `FLOW_BUILDER_LEARNINGS.md`.
