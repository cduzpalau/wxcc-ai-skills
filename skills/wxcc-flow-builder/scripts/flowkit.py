#!/usr/bin/env python3
"""flowkit - build, lint and emit Webex Contact Center FlowV2 JSON from a Python spec.

Standard library only. CLI-agnostic: any agent (Claude Code, Codex, Gemini, Antigravity) can run it.

Usage:
  python3 flowkit.py build <spec.flow.py> -o build/<Flow>.flowv2.json [--full]
  python3 flowkit.py lint  <flow.json>
  python3 flowkit.py compact <flow.json> -o <out.json>     # strip redundant fields from an existing flow

A spec is a Python file that receives `Flow` (and helpers) as globals and assigns `flow = Flow(...)`.
See ../examples/MPSA.flow.py.

Exit code: 0 = lint clean (warnings allowed), 1 = lint errors.
"""
import argparse, json, os, re, runpy, sys, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
PORTS = json.load(open(os.path.join(HERE, "..", "references", "ports.json")))["activities"]

TTS_CONNECTOR = "Cisco Cloud Text-to-Speech"
# Fields the platform accepts but does not need (verified by dry-run validation 2026-10-07).
TTS_FULL_ONLY = {"connector_name": TTS_CONNECTOR, "connector_type": TTS_CONNECTOR,
                 "toggleLanguage": True, "prompts": None}


class Flow:
    def __init__(self, name, description="", voice="en-US-Wavenet-C", speaking_rate=1.0, volume_db=0.0,
                 contact_type="telephony"):
        self.name, self.description, self.contact_type = name, description, contact_type
        self.voice, self.speaking_rate, self.volume_db = voice, speaking_rate, volume_db
        self.variables, self.nodes, self.edges = [], [], []
        self.ev_nodes, self.ev_edges = [], []
        self._target = "main"

    # ---------------- variables ----------------
    def var(self, name, typ, value="", cad=False, label="", reportable=False, secure=False, desc=""):
        """typ: STRING | INTEGER | BOOLEAN | DECIMAL | DATETIME | JSON. Values are passed as strings."""
        self.variables.append({
            "name": name, "description": desc, "type": typ, "value": str(value).lower() if isinstance(value, bool) else str(value),
            "isCAD": cad, "desktopLabel": label if cad else "", "isAgentEditable": False, "source": "",
            "isReportable": reportable, "overwrite": False, "isSecure": secure,
            "id": f"var-{name}", "isExternalized": False, "resourceType": ""})
        return self

    def secure_var(self, name, typ="STRING", value="", desc=""):
        """Sensitive data (OTP, PIN, national ID): hidden from desktop and reporting."""
        return self.var(name, typ, value, cad=False, reportable=False, secure=True, desc=desc)

    # ---------------- node primitives ----------------
    def event_flow(self):
        """Subsequent node()/edge() calls go to eventFlows. Call main_flow() to switch back."""
        self._target = "event"
        return self

    def main_flow(self):
        self._target = "main"
        return self

    def node(self, name, activity, desc, node_type="action", **props):
        assert desc, f"{name}: description is mandatory (FC1007)"
        p = {"name": name, "description": desc, "activityName": activity, **props}
        n = {"id": f"node-{name}", "name": name, "activityType": node_type, "properties": p}
        (self.ev_nodes if self._target == "event" else self.nodes).append(n)
        return name

    def edge(self, frm, to, *conds):
        """One edge per condition. Use "" for the success port of ivr-collectdigits / queue-lookup.
        properties.value carries the branch value (Flow Orchestration guide; UI-built flows set it on every edge).
        The edge id is the PATCH merge key."""
        lst = self.ev_edges if self._target == "event" else self.edges
        for c in conds:
            lst.append({"id": f"{'event-' if self._target == 'event' else ''}edge-{len(lst)+1}",
                        "from": frm, "to": to, "condition": c, "properties": {"value": c} if c else {}})
        return self

    def _tts(self, prompt_id, text):
        return {"connector": TTS_CONNECTOR, "toggle": True, "voiceLanguage": self.voice,
                "voiceLanguage_name": self.voice, "speakingRate": self.speaking_rate,
                "volumeGainDb": self.volume_db,
                "promptsTts": [{"name": prompt_id, "type": "tts", "value": text}],
                **TTS_FULL_ONLY}

    # ---------------- activities ----------------
    def start(self, name="NewPhoneContact", desc="Inbound voice contact"):
        """Name it NewPhoneContact so {{NewPhoneContact.ANI}} resolves."""
        return self.node(name, "start", desc, node_type="start", flowType={
            "eventSourceName": "WebexContactCenter", "eventClassificationName": "VoiceInteractions",
            "eventSpecificationName": "ContactStartWorkflow"})

    def play(self, name, prompt_id, text, desc, interruptible=True):
        return self.node(name, "play-message", desc, activityType="core",
                         interruptible=interruptible, **self._tts(prompt_id, text))

    def music(self, name, desc, prompt="defaultmusic_on_hold.wav", seconds=45):
        return self.node(name, "play-music", desc, activityType="core", audioRadioGroup="staticAudio",
                         prompt=prompt, promptDynamic=None, duration=str(seconds), skip=0)

    def setv(self, name, desc, *assigns):
        """assigns: (variable, TYPE, value). Values may be literals ("Verified") or Pebble ("{{ N + 1 }}").
        Clear a variable with "" or "''" -> emitted as "{{ '' }}" (an empty literal is rejected).
        Emits the Flow Designer UI shape (entries keyed by srcVariable, copied from a Cisco-built flow);
        entries keyed by "variable" pass the MCP validator but open EMPTY in Flow Designer."""
        arr = []
        for v, t, val in assigns:
            val = "{{ '' }}" if str(val) in ("", "''") else str(val)
            arr.append({"setTo": "set-to-literal", "srcVariable": v, "srcVariableType": t,
                        "literal": val, "expr": val, "literal_invalid_error": False,
                        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.name}/{name}/{v}"))})
        e0 = arr[0]
        return self.node(name, "set-variable", desc, activityType="logic", activityId="set-variable",
                         setTo="set-to-literal", srcVariable=e0["srcVariable"],
                         srcVariableType=e0["srcVariableType"], literal=e0["literal"], expr=e0["expr"],
                         literal_invalid_error=False, setVariablesArray=arr)

    def cond(self, name, expression, desc):
        """Wrap the WHOLE expression: '{{ A == true and B > 3 }}'."""
        assert expression.strip().startswith("{{") and expression.strip().endswith("}}"), \
            f"{name}: wrap the entire expression in {{{{ }}}} (FC1009)"
        return self.node(name, "condition-activity", desc, activityType="logic", expression=expression)

    def business_hours(self, name, bh_id, desc):
        return self.node(name, "business-hours", desc, activityType="logic",
                         businessHoursRadioGroup="staticBusinessHours", businessHoursId=bh_id)

    def collect(self, name, prompt_id, text, desc, min_digits=1, max_digits=10, timeout=5,
                inter_digit=5, terminator="#", interruptible=True):
        """Digits land in output {{<name>.DigitsEntered}} - copy them with setv(). No retry input: loop yourself."""
        return self.node(name, "ivr-collectdigits", desc, activityType="core", interruptible=interruptible,
                         entryTimeout=timeout, interDigitTimeout=inter_digit, minDigits=min_digits,
                         maxDigits=max_digits, terminatorSymbol=terminator, **self._tts(prompt_id, text))

    def menu(self, name, prompt_id, text, desc, options, timeout=5, interruptible=True):
        """options: {"1": "Label", "2": "Label"}. Edge conditions are the digit strings."""
        return self.node(name, "ivr-menu", desc, activityType="core", interruptible=interruptible,
                         entryTimeout=timeout, menuLinks=list(options),
                         menuOptions=[{"label": l, "digit": d} for d, l in options.items()],
                         **self._tts(prompt_id, text))

    def http(self, name, path, desc, method="POST", body="", timeout_ms=5000, retries=1, connector_id=None,
             parse=None):
        """Connector-based HTTP Request (the only form Flow Designer keeps as http-request-v2).
        path: request path relative to the Control Hub connector's base URL.
        connector_id: None leaves the node UNCONFIGURED (expected FC1015 'Connector not configured') - put the
                      connector instructions in desc.
        parse: {"FlowVar": "$.json.path"} -> outputVariableArray with jsonPathExp (shape copied from a node
               configured in Flow Designer). Response is also available as {{<name>.httpResponseBody}}.
        Unauthenticated mode (authenticated:false + httpRequestUrl) is NOT offered: any Flow Designer save or
        PATCH converts it to the legacy http-request activity."""
        assert 100 <= timeout_ms <= 60000, f"{name}: httpResponseTimeout is in milliseconds (100-60000)"
        props = dict(activityType="logic", activityId="http-request-v2", authenticated=True,
                     connectorId=connector_id, httpRequestPath=path, httpRequestUrl=None,
                     httpRequestMethod=method, httpContentType="Application/JSON",
                     httpResponseTimeout=timeout_ms, retryAttempts=retries, httpRequestBody=body,
                     httpRequestHeaders={}, httpQueryParameters={}, httpRequestBodyFormData=None,
                     httpRequestBodyGQL=None, httpRequestBodyFiles=None, flowDecryptAccess=False)
        if parse:
            props.update(contentType="JSON", outputVariableArray=[
                {"outputVariable": v, "jsonPathExp": p} for v, p in parse.items()])
        return self.node(name, "http-request-v2", desc, **props)

    def virtual_agent(self, name, agent_name, desc):
        """Ports ENDED / ESCALATE / error. Outputs in {{<name>.MetaData}} (JSON)."""
        return self.node(name, "ivr-virtualassistantvoice", desc, activityType="core",
                         configIdRadioGroup="staticConfigId", connector="NATIVE_ADVANCED_VIRTUAL_AGENT",
                         virtualAgentId=agent_name, variableSelection=None, eventName="", eventData="",
                         terminationDelay=30, speakingRate=1, volumeGain=0, pitch=0, transcript=True,
                         recordAutonomous=False, recordScripted=False)

    def queue(self, name, queue_id, queue_label, desc):
        """Only one exit: 'default'."""
        return self.node(name, "queue-contact", desc, activityType="core", queueRadioGroup="staticQueue",
                         destination=queue_id, destination_name=queue_label, toggle=False,
                         toggleAgentAvailability=False, priority=None, skills=None, fallbackQueue=None)

    def queue_lookup(self, name, queue_id, desc, lookback_min=15):
        """Outputs {{<name>.PIQ}} and {{<name>.EWT}}. Success port is "".
        queue_id must be a STATIC queue ID: Flow Designer blanks a {{variable}} destination on save."""
        return self.node(name, "queue-lookup", desc, activityType="core", destination=queue_id,
                         ewtLookbackMinutes=lookback_min)

    def callback(self, name, dn_expr, queue_id, desc):
        return self.node(name, "callback", desc, activityType="core", callbackDn=dn_expr,
                         toggleCallbackDestination=False, callbackQueue=queue_id, callbackAni=None)

    def disconnect(self, name, desc):
        return self.node(name, "disconnect-contact", desc, node_type="end", activityType="core")

    def event(self, spec_name="GlobalErrorHandling", desc="Global error handler"):
        """Event node inside event_flow(). spec_name from wxcc-list-event-specifications."""
        assert self._target == "event", "call event_flow() first"
        n = {"id": f"event-{spec_name}", "name": spec_name, "activityType": "event", "properties": {
            "name": spec_name, "description": desc, "activityName": "event",
            "eventSourceName": "WebexContactCenter", "eventClassificationName": "VoiceInteractions",
            "eventSpecificationName": spec_name}}
        self.ev_nodes.append(n)
        return spec_name

    def retarget(self, old_to, new_to):
        """Redirect every main-flow edge pointing at old_to (handy for inserting a pre-step)."""
        for e in self.edges:
            if e["to"] == old_to and e["from"] != new_to:
                e["to"] = new_to
        return self

    # ---------------- output ----------------
    def to_json(self, full=False):
        # Top-level fields per the Flow Orchestration guide (contactType, preferences); version/status are server-managed.
        flow = {"schemaVersion": "2.0", "name": self.name, "flowType": "FLOW", "contactType": self.contact_type,
                "description": self.description, "variables": self.variables, "nodes": self.nodes,
                "edges": self.edges, "eventFlows": {"nodes": self.ev_nodes, "edges": self.ev_edges},
                "preferences": [{"name": "hideSecureCADWarning", "type": "Boolean", "value": "false"}]}
        return flow if full else compact(flow)


def compact(flow):
    """Drop fields the validator does not need, to keep the inline MCP payload small."""
    drop = set(TTS_FULL_ONLY) | {"voiceLanguage_name", "_renderRequestTimestamp", "activityVersionNumber",
                                 "flowDecryptAccess", "connector:name", "connector:type"}
    out = json.loads(json.dumps(flow))
    for n in out["nodes"] + out.get("eventFlows", {}).get("nodes", []):
        for k in list(n["properties"]):
            if k in drop:
                del n["properties"][k]
    for v in out["variables"]:
        if not v.get("description"):
            v.pop("description", None)
    return out


# ---------------- lint ----------------
CONDITION_ALIASES = {"done": "out", "defaultBranch": "default"}  # normalized server-side (Flow Orchestration guide)
REF_RE = re.compile(r"\{\{(.*?)\}\}", re.S)
IDENT_RE = re.compile(r"(?<![\w.'\"])([A-Za-z_]\w*)(?:\.(\w+))?")
PEBBLE_WORDS = {"and", "or", "not", "true", "false", "null", "none", "is", "in", "if", "else",
                "jsonPath", "length", "upper", "lower", "trim", "default", "abs", "round", "contains"}


def lint(flow):
    errors, warnings = [], []
    var_names = {v["name"] for v in flow.get("variables", [])}

    for v in flow.get("variables", []):
        if v.get("isSecure") and (v.get("isCAD") or v.get("isReportable")):
            errors.append(f"var {v['name']}: isSecure requires isCAD=false and isReportable=false")

    def check_graph(nodes, edges, label, root_types):
        by_name = {}
        for n in nodes:
            if n["name"] in by_name:
                errors.append(f"[{label}] duplicate node name {n['name']} (FC1022)")
            by_name[n["name"]] = n
        out, ids = {}, set()
        for e in edges:
            if e.get("id") in ids:
                errors.append(f"[{label}] duplicate edge id {e.get('id')} (ids are unique per process / PATCH key)")
            ids.add(e.get("id"))
            e = dict(e, condition=CONDITION_ALIASES.get(e["condition"], e["condition"]))
            for side in ("from", "to"):
                if e[side] not in by_name:
                    errors.append(f"[{label}] edge {e.get('id')} {side} unknown node '{e[side]}'")
            out.setdefault(e["from"], []).append(e)
        for name, n in by_name.items():
            p = n["properties"]
            act = p.get("activityName")
            if not p.get("description"):
                errors.append(f"{name}: missing description (FC1007)")
            spec = PORTS.get(act)
            if spec is None:
                warnings.append(f"{name}: activity '{act}' not in ports.json - ports not checked")
                continue
            allowed = set(spec["allowed"]) | (set(p.get("menuLinks", [])) if act == "ivr-menu" else set())
            required = set(spec["required"]) | (set(p.get("menuLinks", [])) if act == "ivr-menu" else set())
            used = [e["condition"] for e in out.get(name, [])]
            for c in used:
                if c not in allowed:
                    errors.append(f"{name} ({act}): condition {c!r} invalid - allowed {sorted(allowed)}")
            for c in required - set(used):
                errors.append(f"{name} ({act}): port {c!r} not connected")
            for c in set(used):
                if used.count(c) > 1:
                    errors.append(f"{name}: port {c!r} has {used.count(c)} edges")
            for k in spec.get("required_props", []):
                if p.get(k) in (None, ""):
                    errors.append(f"{name} ({act}): required property '{k}' missing (FC1015)")
            if act == "queue-lookup" and "{{" in str(p.get("destination", "")):
                errors.append(f"{name}: queue-lookup destination must be a static queue ID "
                              f"(Flow Designer blanks {p['destination']} on save)")
            if act == "http-request-v2":
                if not p.get("authenticated", True):
                    errors.append(f"{name}: authenticated:false is converted to legacy http-request by Flow "
                                  f"Designer - use a connector (or leave connectorId empty with instructions)")
                elif not p.get("connectorId"):
                    warnings.append(f"{name}: no connectorId - expected FC1015 'Connector not configured' "
                                    f"until an admin selects one")
                for i, o in enumerate(p.get("outputVariableArray") or []):
                    if set(o) != {"outputVariable", "jsonPathExp"}:
                        errors.append(f"{name}: outputVariableArray[{i}] must be {{outputVariable, jsonPathExp}}")
                    elif o["outputVariable"] not in var_names:
                        errors.append(f"{name}: parses into undeclared variable '{o['outputVariable']}'")
            if act == "set-variable":
                for i, sv in enumerate(p.get("setVariablesArray") or []):
                    if "srcVariable" not in sv:
                        errors.append(f"{name}: setVariablesArray[{i}] uses {sorted(sv)} - Flow Designer needs "
                                      f"'srcVariable' (+srcVariableType) or the node opens empty")
                    elif sv["srcVariable"] not in var_names:
                        errors.append(f"{name}: sets undeclared variable '{sv['srcVariable']}'")
                    if sv.get("literal", "") == "" and sv.get("expr", "") in ("", None):
                        errors.append(f"{name}: empty value for {sv.get('srcVariable')} - use {{{{ '' }}}}")
        # reachability
        roots = [n["name"] for n in nodes if n["activityType"] in root_types]
        seen, stack = set(), list(roots)
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack += [e["to"] for e in out.get(cur, [])]
        for name in by_name:
            if name not in seen:
                errors.append(f"[{label}] {name} unreachable from {roots} (FC1004)")
        return by_name

    main = check_graph(flow["nodes"], flow["edges"], "main", {"start"})
    ev = flow.get("eventFlows") or {}
    evn = check_graph(ev.get("nodes", []), ev.get("edges", []), "event", {"event"}) if ev.get("nodes") else {}
    node_names = set(main) | set(evn)

    # variable references
    for n in flow["nodes"] + ev.get("nodes", []):
        blob = json.dumps(n["properties"])
        for expr in REF_RE.findall(blob):
            expr = re.sub(r"'[^']*'|\\\"[^\\\"]*\\\"", "", expr)  # strip string literals
            for ident, attr in IDENT_RE.findall(expr):
                if ident in PEBBLE_WORDS or ident in var_names or ident.startswith("Global_") or ident.isdigit():
                    continue
                if ident == "NewPhoneContact":
                    continue
                if ident in node_names and attr:
                    warnings.append(f"{n['name']}: references output {ident}.{attr} - expect FC1038 from the MCP "
                                    f"validator (false positive: it also flags Cisco's published flows)")
                    continue
                errors.append(f"{n['name']}: '{ident}' referenced but not declared (FC1038)")
    return sorted(set(errors)), sorted(set(warnings))


def summary(flow):
    ev = flow.get("eventFlows") or {}
    return (f"nodes={len(flow['nodes'])} edges={len(flow['edges'])} vars={len(flow['variables'])} "
            f"event_nodes={len(ev.get('nodes', []))} bytes={len(json.dumps(flow, separators=(',', ':')))}")


def report(flow):
    errs, warns = lint(flow)
    print(summary(flow))
    for w in warns:
        print("WARN ", w)
    for e in errs:
        print("ERROR", e)
    print(f"lint: {len(errs)} error(s), {len(warns)} warning(s)")
    return 1 if errs else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("spec"); b.add_argument("-o", "--out", required=True)
    b.add_argument("--full", action="store_true", help="keep redundant UI fields")
    l = sub.add_parser("lint"); l.add_argument("flow")
    c = sub.add_parser("compact"); c.add_argument("flow"); c.add_argument("-o", "--out", required=True)
    a = ap.parse_args(argv)

    if a.cmd == "build":
        g = runpy.run_path(a.spec, init_globals={"Flow": Flow})
        if "flow" not in g or not isinstance(g["flow"], Flow):
            sys.exit("spec must assign `flow = Flow(...)`")
        data = g["flow"].to_json(full=a.full)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        json.dump(data, open(a.out, "w"), separators=(",", ":"))
        print(f"wrote {a.out}")
        return report(data)
    data = json.load(open(a.flow))
    if a.cmd == "lint":
        return report(data)
    out = compact(data)
    json.dump(out, open(a.out, "w"), separators=(",", ":"))
    print(f"wrote {a.out}")
    return report(out)


if __name__ == "__main__":
    sys.exit(main())
