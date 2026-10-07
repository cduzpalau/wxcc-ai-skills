#!/usr/bin/env python3
"""
cce_to_wxcc.py - Transform a decoded CCE configuration (output of `cce_decode.py decode`)
into Webex Contact Center Bulk Operations CSV files, plus a migration report.

usage:
  cce_to_wxcc.py <decoded_dir> <out_dir>
        [--site NAME] [--timezone America/New_York] [--email-domain example.com]
        [--dn-prefix +1919555] [--agent-user-profile NAME] [--supervisor-user-profile NAME]
        [--existing wxcc_config_export.txt] [--include-empty-queues] [--chat-capacity 3] [--email-capacity 1]

Mapping rules are documented in references/mapping.md. Everything that cannot be expressed
in a bulk CSV (flows, routing requirements, digital assets, phone numbers) goes into
migration_report.md and routing_requirements.json instead of being silently dropped.
"""
import argparse, collections, csv, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wxcc_bulk_spec import HEADERS, IMPORT_ORDER, DEFAULT_WORK_TYPES  # noqa: E402

# ------------------------------------------------------------------ constants / heuristics
ATTR_TYPES = {1: 'TEXT', 2: 'INTEGER', 3: 'BOOLEAN', 4: 'PROFICIENCY'}       # Attribute.AttributeDataType
PQ_REL = {1: '==', 2: '!=', 3: '<', 4: '<=', 5: '>', 6: '>='}                 # Precision_Queue_Term.AttributeRelation
# Cisco reserved / system reason codes (CCE + Finesse). Not migrated - WxCC has its own system codes.
SYSTEM_REASON_CODES = {-1, 0, 255, 999, 20001, 20002, 20003, 32760, 32761, 32762, 32763, 32764, 32765, 32766,
                       32767, 65533, 65534, 65535} | set(range(50001, 50050))
# ECC variable prefixes that are CVP / ECE / platform plumbing and have no meaning in WxCC
ECC_PLUMBING = ('BA', 'POD.', 'user.microapp.', 'user.cvp', 'user.sip.', 'user.suppress.', 'user.cisco.cmb',
                'user.ece.', 'user.media.')


def channel_of(mrd_name):
    n = (mrd_name or '').lower()
    if n in ('cisco_voice',) or 'voice' in n: return 'TELEPHONY'
    if 'outbound' in n: return 'OUTBOUND'
    if 'task' in n: return 'TASK'
    if any(k in n for k in ('sms', 'whatsapp', 'facebook', 'social')): return 'SOCIAL'
    if 'chat' in n or 'wim' in n: return 'CHAT'
    if 'mail' in n or 'eim' in n: return 'EMAIL'
    if n.endswith('_bc') or 'callback' in n or 'delayed' in n: return 'OTHER'
    return 'OTHER'


def social_type(mrd_name):
    n = (mrd_name or '').lower()
    return 'WHATSAPP' if 'whatsapp' in n else 'SMS' if 'sms' in n else 'FACEBOOK MESSENGER' if 'facebook' in n else ''


def clean_name(s, maxlen=80):
    s = re.sub(r'\s+', ' ', (s or '').strip())
    return s[:maxlen]


def var_name(ecc):
    n = re.sub(r'^(user[._])', '', ecc)
    n = re.sub(r'[^A-Za-z0-9_]', '_', n)
    if not n[:1].isalpha(): n = 'V_' + n
    return n[:80]


def load(decoded, base):
    p = os.path.join(decoded, base + '.json')
    return json.load(open(p))['rows'] if os.path.exists(p) else []


def write_csv(path, header, rows):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(header)
        for r in rows: w.writerow([('' if r.get(h) is None else r.get(h)) for h in header])


def parse_tenant_export(path):
    """Read the sectioned tenant export (=== TITLE === then JSON) into {section: set(names)}."""
    out, txt = {}, open(path, encoding='utf-8').read()
    parts = re.split(r'\n=+\n([A-Z][A-Z ()]+)\n=+\n', '\n' + txt)
    for i in range(1, len(parts) - 1, 2):
        title, body = parts[i].strip(), parts[i + 1].strip()
        try:
            j = json.loads(body)
        except Exception:
            continue
        items = j.get('resources') or j.get('data') or []
        names = set()
        for it in items:
            for k in ('name', 'email', 'dialledNumber'):
                if it.get(k): names.add(str(it[k])); break
        out[title] = names
    return out


# ------------------------------------------------------------------ main transform
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('decoded_dir'); ap.add_argument('out_dir')
    ap.add_argument('--site', help='WxCC site name (default: name of the CCE agent peripheral)')
    ap.add_argument('--timezone', help='default: America/New_York (flagged as a placeholder)')
    ap.add_argument('--email-domain', default='example.com',
                    help='used when Person has no e-mail: <LoginName>@<domain>')
    ap.add_argument('--dn-prefix', default='', help='prefix that turns CCE dialed numbers into tenant E.164 numbers')
    ap.add_argument('--agent-user-profile', help='default: "Standard Agent" (flagged as a placeholder)')
    ap.add_argument('--supervisor-user-profile', help='default: "Supervisor" (flagged as a placeholder)')
    ap.add_argument('--existing', help='tenant export (wxcc_config_export.txt) for create/update diff')
    ap.add_argument('--include-empty-queues', action='store_true')
    ap.add_argument('--chat-capacity', type=int, default=3)
    ap.add_argument('--email-capacity', type=int, default=1)
    ap.add_argument('--music', default='defaultmusic_on_hold.wav')
    a = ap.parse_args()
    if a.existing and not os.path.isfile(a.existing):
        sys.exit('--existing %s: file not found. Fix the path, or omit --existing and build the diff from the MCP list tools.'
                 % a.existing)
    # Rule "no silent placeholders": every default that stands in for a tenant value is recorded
    # here, warned about in migration_report.md, and handed to the validator via _run_context.json.
    defaults_used = []
    for opt, attr, val in (('--timezone', 'timezone', 'America/New_York'),
                           ('--agent-user-profile', 'agent_user_profile', 'Standard Agent'),
                           ('--supervisor-user-profile', 'supervisor_user_profile', 'Supervisor')):
        if getattr(a, attr) is None:
            setattr(a, attr, val)
            defaults_used.append('%s not given; used the default "%s". Confirm it exists in the tenant or re-run with %s.'
                                 % (opt, val, opt))
    D = lambda b: load(a.decoded_dir, b)
    os.makedirs(a.out_dir, exist_ok=True)
    warn, notes, skipped = list(defaults_used), [], collections.defaultdict(list)
    crosswalk = []

    alive = lambda r: r.get('Deleted', 'N') != 'Y'
    mrd = {r['MRDomainID']: r for r in D('MeRoDo')}
    periph = {r['PeripheralID']: r for r in D('Peripher')}
    rclient = {r['RoutingClientID']: r for r in D('RoutClie')}
    persons = {r['PersonID']: r for r in D('Person')}
    agents = {r['SkillTargetID']: r for r in D('Agent') if alive(r) and r.get('TemporaryAgent') != 'Y'}
    attrs = {r['AttributeID']: r for r in D('Attribut') if alive(r)}
    teams = {r['AgentTeamID']: r for r in D('AgenTeam') if alive(r)}
    sgs = {r['SkillTargetID']: r for r in D('SkilGrou') if alive(r)}
    pqs = {r['PrecisionQueueID']: r for r in D('PrecQueu') if alive(r)}
    calltypes = {r['CallTypeID']: r for r in D('CallType') if alive(r)}
    dns = {r['DialedNumberID']: r for r in D('DialNumb') if alive(r)}
    masters = {r['MasterScriptID']: r for r in D('MastScri') if alive(r)}

    # ---- site
    agent_periphs = collections.Counter(r['PeripheralID'] for r in agents.values())
    site = a.site or (periph.get(agent_periphs.most_common(1)[0][0], {}).get('EnterpriseName', 'Site-1')
                      if agent_periphs else 'Site-1')
    if len(agent_periphs) > 1:
        warn.append('Agents live on %d peripherals; all mapped to site "%s". Split with --site per run if needed.'
                    % (len(agent_periphs), site))

    # ---- membership indexes
    team_members = collections.defaultdict(set)
    for r in D('AgTeMe'):
        if r['AgentTeamID'] in teams and r['SkillTargetID'] in agents: team_members[r['AgentTeamID']].add(r['SkillTargetID'])
    agent_teams = collections.defaultdict(set)
    for t, ms in team_members.items():
        for m in ms: agent_teams[m].add(teams[t]['EnterpriseName'])
    supervisors = {r['SupervisorSkillTargetID'] for r in D('AgTeSu')}
    sup_teams = collections.defaultdict(set)
    for r in D('AgTeSu'):
        if r['AgentTeamID'] in teams: sup_teams[r['SupervisorSkillTargetID']].add(teams[r['AgentTeamID']]['EnterpriseName'])
    sg_members = collections.defaultdict(set)
    for r in D('SkGrMe'):
        if r['AgentSkillTargetID'] in agents: sg_members[r['SkillGroupSkillTargetID']].add(r['AgentSkillTargetID'])
    agent_attr = collections.defaultdict(dict)
    for r in D('AgenAttr'):
        if r['SkillTargetID'] in agents and r['AttributeID'] in attrs: agent_attr[r['SkillTargetID']][r['AttributeID']] = r['Value']
    outbound_sgs = {r['SkillTargetID'] for r in D('CaSkGr')}

    # ================================================================ 1. skills
    skills = []          # dict rows for CSV
    skill_type = {}      # name -> type
    for at in sorted(attrs.values(), key=lambda r: r['EnterpriseName']):
        t = ATTR_TYPES.get(at['AttributeDataType'], 'TEXT')
        if t == 'INTEGER':
            lo, hi = int(at['MinimumValue'] or 0), int(at['MaximumValue'] or 0)
            t = 'PROFICIENCY' if 0 <= lo and hi <= 10 else 'TEXT'
            warn.append('Attribute %s is INTEGER in CCE; mapped to %s.' % (at['EnterpriseName'], t))
        name = clean_name(at['EnterpriseName'])
        skills.append({'Name': name, 'Description': clean_name(at.get('Description') or 'Migrated from CCE attribute', 255),
                       'Service Level Threshold': 0, 'Type': t})
        skill_type[name] = t
        crosswalk.append(('Attribute', at['AttributeID'], at['EnterpriseName'], 'Skill', name))

    # skill groups that become queues get a boolean "membership" skill
    sg_queue = {}
    for sg in sorted(sgs.values(), key=lambda r: r['EnterpriseName']):
        nm = sg['EnterpriseName']
        ch = channel_of(mrd.get(sg['MRDomainID'], {}).get('EnterpriseName'))
        if sg.get('PrecisionQueueID') is not None:
            continue                                          # PQ shadow SG -> handled with PQs
        if sg.get('DefaultEntry') == 1:
            skipped['Skill Group'].append((nm, 'system default skill group')); continue
        if sg['SkillTargetID'] in outbound_sgs or 'outbound' in nm.lower() or ch == 'OUTBOUND':
            skipped['Skill Group'].append((nm, 'outbound campaign skill group -> rebuild as WxCC outbound campaign')); continue
        if ch in ('TASK', 'OTHER', 'SOCIAL'):
            skipped['Skill Group'].append((nm, 'channel %s (%s) has no bulk queue equivalent' % (ch, mrd.get(sg['MRDomainID'], {}).get('EnterpriseName')))); continue
        if not sg_members[sg['SkillTargetID']] and not a.include_empty_queues:
            skipped['Skill Group'].append((nm, 'no agent members (use --include-empty-queues to create anyway)')); continue
        sk = clean_name('SG_' + nm)
        skills.append({'Name': sk, 'Description': clean_name('Membership of CCE skill group %s' % nm, 255),
                       'Service Level Threshold': 0, 'Type': 'BOOLEAN'})
        skill_type[sk] = 'BOOLEAN'
        sg_queue[sg['SkillTargetID']] = dict(name=clean_name(nm), skill=sk, channel=ch, sg=sg)
        crosswalk.append(('Skill_Group', sg['SkillTargetID'], nm, 'Skill+Queue', sk + ' / ' + nm))

    # ================================================================ 2. per-agent skill sets
    def agent_skillset(aid):
        s = {}
        for atid, val in agent_attr[aid].items():
            nm = clean_name(attrs[atid]['EnterpriseName']); t = skill_type[nm]
            if t == 'BOOLEAN': s[nm] = 'True' if str(val).lower() in ('true', '1', 'y', 'yes') else 'False'
            elif t == 'PROFICIENCY': s[nm] = str(max(0, min(10, int(float(val)))))
            else: s[nm] = str(val)[:80]
        for sgid, q in sg_queue.items():
            if aid in sg_members[sgid]: s[q['skill']] = 'True'
        return s

    # ---- PQ evaluation (who is eligible) - used for distribution groups and multimedia profiles
    terms = collections.defaultdict(list)
    for t in D('PrQuTe'): terms[t['PrecisionQueueID']].append(t)
    steps = collections.defaultdict(list)
    for s in D('PrQuSt'):
        if alive(s): steps[s['PrecisionQueueID']].append(s)

    def term_ok(aid, t):
        at = attrs.get(t['AttributeID'])
        if not at: return False
        v = agent_attr[aid].get(t['AttributeID'])
        if v is None: return False
        want, rel = t['Value1'], PQ_REL.get(t['AttributeRelation'], '==')
        if ATTR_TYPES.get(at['AttributeDataType']) in ('PROFICIENCY', 'INTEGER'):
            x, y = float(v), float(want)
        else:
            x, y = str(v).lower(), str(want).lower()
        return {'==': x == y, '!=': x != y, '<': x < y, '<=': x <= y, '>': x > y, '>=': x >= y}[rel]

    def step_ok(aid, ts):
        res = None
        for t in sorted(ts, key=lambda t: t['TermOrder']):
            ok = term_ok(aid, t)
            if res is None: res = ok
            elif t['TermRelation'] == 2: res = res or ok       # OR
            else: res = res and ok                             # AND (1) / default
        return bool(res)

    pq_def = {}
    for pid, pq in sorted(pqs.items(), key=lambda kv: kv[1]['EnterpriseName']):
        ch = channel_of(mrd.get(pq['MRDomainID'], {}).get('EnterpriseName'))
        st = sorted(steps.get(pid) or [{'PrecisionQueueStepID': None, 'StepOrder': 1, 'WaitTime': None}],
                    key=lambda s: s['StepOrder'])
        step_terms = []
        for s in st:
            ts = [t for t in terms[pid] if t['PrecisionQueueStepID'] == s['PrecisionQueueStepID']] or \
                 ([t for t in terms[pid]] if len(st) == 1 else [])
            step_terms.append((s, ts))
        if any(t.get('ParenLevel') for t in terms[pid]):
            warn.append('PQ %s uses parentheses; flattened left-to-right - review routing_requirements.json' % pq['EnterpriseName'])
        eligible = {aid for aid in agents if any(step_ok(aid, ts) for _, ts in step_terms if ts)}
        pq_def[pid] = dict(pq=pq, channel=ch, steps=step_terms, eligible=eligible)
        crosswalk.append(('Precision_Queue', pid, pq['EnterpriseName'], 'Queue (SKILLS_BASED)', pq['EnterpriseName']))

    # ---- channels per agent -> multimedia profile
    agent_channels = collections.defaultdict(set)
    for aid in agents: agent_channels[aid].add('TELEPHONY')
    for sgid, q in sg_queue.items():
        for aid in sg_members[sgid]: agent_channels[aid].add(q['channel'])
    for pid, p in pq_def.items():
        if p['channel'] in ('TELEPHONY', 'CHAT', 'EMAIL'):
            for aid in p['eligible']: agent_channels[aid].add(p['channel'])

    def mmp_name(chs):
        order = [('TELEPHONY', 'Voice'), ('CHAT', 'Chat'), ('EMAIL', 'Email'), ('SOCIAL', 'Social')]
        return 'MMP_' + '_'.join(lbl for k, lbl in order if k in chs)
    mmps = {}
    for aid, chs in agent_channels.items():
        n = mmp_name(chs)
        mmps[n] = {'Name': n, 'Description': 'Generated from CCE skill group / PQ channels', 'Type': 'BLENDED',
                   'Voice': 1 if 'TELEPHONY' in chs else 0, 'Chat': a.chat_capacity if 'CHAT' in chs else 0,
                   'Email': a.email_capacity if 'EMAIL' in chs else 0, 'Social': 1 if 'SOCIAL' in chs else 0}
    default_mmp = collections.Counter(mmp_name(c) for c in agent_channels.values()).most_common(1)[0][0] if agent_channels else 'MMP_Voice'
    mmps.setdefault(default_mmp, {'Name': default_mmp, 'Description': 'Default', 'Type': 'BLENDED', 'Voice': 1, 'Chat': 0, 'Email': 0, 'Social': 0})

    # ---- skill profiles (deduplicated by identical skill set)
    sig_agents = collections.defaultdict(list)
    for aid in agents:
        ss = agent_skillset(aid)
        if ss: sig_agents[tuple(sorted(ss.items()))].append(aid)
    sp_rows, agent_sp, used = [], {}, collections.Counter()
    for sig, aids in sorted(sig_agents.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        tcount = collections.Counter(t for x in aids for t in agent_teams[x])
        base = 'SP_' + (tcount.most_common(1)[0][0] if tcount else 'NoTeam')
        used[base] += 1
        name = base if used[base] == 1 else '%s_%d' % (base, used[base])
        sp_rows.append({'Name': name, 'Description': clean_name('%d agent(s): %s' % (len(aids), ', '.join('%s=%s' % kv for kv in sig)), 255)})
        for sk, val in sig: sp_rows.append({'Name': name, 'Skill Name': sk, 'Skill Values': val})
        for x in aids: agent_sp[x] = name

    # ================================================================ 3. teams
    team_rows = []
    for t in sorted(teams.values(), key=lambda r: r['EnterpriseName']):
        team_rows.append({'Name': clean_name(t['EnterpriseName']), 'Site': site, 'Type': 'AGENT'})
        if not team_members[t['AgentTeamID']]: warn.append('Team %s has no agents in the export.' % t['EnterpriseName'])
        crosswalk.append(('Agent_Team', t['AgentTeamID'], t['EnterpriseName'], 'Team', t['EnterpriseName']))

    def teams_for(aids):
        return sorted({tm for x in aids for tm in agent_teams[x]})

    # ================================================================ 4. queues
    q_rows, routing_req = [], {'queues': [], 'entry_points': []}

    def add_queue(name, desc, ch, slt, sel, groups):
        tel = ch == 'TELEPHONY'
        q_rows.append({'Name': name, 'Description': clean_name(desc, 255), 'Channel Type': ch, 'Max Time In Queue': 3600,
                       'Service Level Threshold': slt, 'Timezone': a.timezone,
                       'Permit Monitoring': 'ON' if tel else '', 'Permit Recording': 'ON' if tel else '',
                       'Record All Calls': 'OFF' if tel else '', 'Pause or Resume Enabled': 'OFF' if tel else '',
                       'Recording Pause Duration': 10 if tel else '', 'Default Music in Queue': a.music if tel else '',
                       'Routing Type': 'SKILLS_BASED', 'Skill-Based Agent Selection': sel})
        for i, g in enumerate(groups, 1):
            q_rows.append({'Name': name, 'Distribution Group': 'Group%d' % i, 'Distribution Group Seq': i,
                           'Group Fallback Time': '' if i == 1 else g[1], 'Group Teams': '|'.join(g[0])})

    for pid, p in sorted(pq_def.items(), key=lambda kv: kv[1]['pq']['EnterpriseName']):
        pq, ch = p['pq'], p['channel']
        if ch not in ('TELEPHONY', 'CHAT', 'EMAIL'):
            skipped['Precision Queue'].append((pq['EnterpriseName'], 'channel %s has no bulk queue equivalent' % ch)); continue
        tms = teams_for(p['eligible'])
        if not tms:
            tms = sorted(r['Name'] for r in team_rows)
            warn.append('PQ %s: no agent in the export satisfies its terms; queue created with all teams in the '
                        'distribution group (skill requirements still gate routing).' % pq['EnterpriseName'])
        has_prof = any(ATTR_TYPES.get(attrs.get(t['AttributeID'], {}).get('AttributeDataType')) == 'PROFICIENCY'
                       for _, ts in p['steps'] for t in ts)
        add_queue(clean_name(pq['EnterpriseName']), pq.get('Description') or 'Migrated from CCE precision queue', ch,
                  pq['ServiceLevelThreshold'] or 20, 'BEST_AVAILABLE_AGENT' if has_prof else 'LONGEST_AVAILABLE_AGENT',
                  [(tms, '')])
        routing_req['queues'].append({
            'queue': clean_name(pq['EnterpriseName']), 'source': 'Precision_Queue %d' % pid, 'channel': ch,
            'agent_selection': 'BEST_AVAILABLE_AGENT' if has_prof else 'LONGEST_AVAILABLE_AGENT',
            'eligible_agents': len(p['eligible']), 'teams': tms,
            'skill_requirements_by_step': [{
                'step': s['StepOrder'], 'wait_seconds_before_next_step': s.get('WaitTime'),
                'requirements': [{'skill': clean_name(attrs[t['AttributeID']]['EnterpriseName']) if t['AttributeID'] in attrs else t['AttributeID'],
                                  'operator': PQ_REL.get(t['AttributeRelation'], '=='), 'value': t['Value1'],
                                  'join': {0: None, 1: 'AND', 2: 'OR'}.get(t['TermRelation'])} for t in sorted(ts, key=lambda t: t['TermOrder'])]}
                for s, ts in p['steps']]})

    for sgid, q in sorted(sg_queue.items(), key=lambda kv: kv[1]['name']):
        tms = teams_for(sg_members[sgid]) or sorted(r['Name'] for r in team_rows)
        add_queue(q['name'], q['sg'].get('Description') or 'Migrated from CCE skill group', q['channel'], 20,
                  'LONGEST_AVAILABLE_AGENT', [(tms, '')])
        routing_req['queues'].append({'queue': q['name'], 'source': 'Skill_Group %d' % sgid, 'channel': q['channel'],
                                      'agent_selection': 'LONGEST_AVAILABLE_AGENT', 'eligible_agents': len(sg_members[sgid]),
                                      'teams': tms, 'skill_requirements_by_step': [{'step': 1, 'requirements': [
                                          {'skill': q['skill'], 'operator': '==', 'value': 'true', 'join': None}]}]})
    queue_names = {r['Name'] for r in q_rows}

    # ================================================================ 5. entry points + mappings
    ct_dns = collections.defaultdict(list)
    for m in D('DiNuMa'):
        if m['DialedNumberID'] in dns and m['CallTypeID'] in calltypes: ct_dns[m['CallTypeID']].append(dns[m['DialedNumberID']])
    ct_script = collections.defaultdict(list)
    for m in D('CaTyMa'):
        if m['MasterScriptID'] in masters: ct_script[m['CallTypeID']].append(masters[m['MasterScriptID']]['EnterpriseName'])
    ep_rows, ep_digital, epm_rows, flow_rows, seen_dn = [], [], [], [], {}
    for ctid, ct in sorted(calltypes.items(), key=lambda kv: kv[1]['EnterpriseName']):
        if ct['EnterpriseName'] == 'BuiltIn': continue
        dl = ct_dns.get(ctid, [])
        if not dl:
            skipped['Call Type'].append((ct['EnterpriseName'], 'no dialed number maps to it (reached only from scripts/transfers)')); continue
        chans = collections.Counter(channel_of(mrd.get(d['MRDomainID'], {}).get('EnterpriseName')) for d in dl)
        ch = chans.most_common(1)[0][0]
        rcs = {rclient.get(d['RoutingClientID'], {}).get('EnterpriseName', '') for d in dl}
        name = clean_name(ct['EnterpriseName'])
        if ch == 'OUTBOUND' or any('outbound' in r.lower() for r in rcs) or 'outbound' in name.lower():
            skipped['Call Type'].append((name, 'outbound call type -> WxCC Outdial Entry Point / campaign')); continue
        if ch in ('TASK', 'OTHER'):
            skipped['Call Type'].append((name, 'channel %s not migrated' % ch)); continue
        row = {'Name': name, 'Description': clean_name(ct.get('Description') or 'Migrated from CCE call type', 255),
               'Service Level Threshold': ct.get('ServiceLevelThreshold') or 20, 'Timezone': a.timezone}
        if ch == 'TELEPHONY':
            row['Channel Type'] = 'TELEPHONY'; ep_rows.append(row)
        else:
            mrdname = mrd.get(dl[0]['MRDomainID'], {}).get('EnterpriseName')
            row['Channel Type'] = 'SOCIAL_CHANNEL' if ch == 'SOCIAL' else ch
            row['Social Channel Type'] = social_type(mrdname) if ch == 'SOCIAL' else ''
            ep_digital.append(row)
        crosswalk.append(('Call_Type', ctid, ct['EnterpriseName'], 'Entry Point (%s)' % row['Channel Type'], name))
        for d in dl:
            s = (d['DialedNumberString'] or '').strip()
            if ch != 'TELEPHONY': continue
            if not re.fullmatch(r'\+?\d+', s):
                skipped['Dialed Number'].append((s, 'not numeric - CCE internal routing label, no PSTN mapping')); continue
            num = (a.dn_prefix + s) if a.dn_prefix else s
            if num in seen_dn:
                if seen_dn[num] != name: warn.append('DN %s maps to %s and %s; kept the first.' % (num, seen_dn[num], name))
                continue
            seen_dn[num] = name
            epm_rows.append({'Dialed Number': num, 'Entry Point': name, 'Region': ''})
        flow_rows.append({'Entry Point': name, 'Channel': row['Channel Type'], 'CCE Call Type': ct['EnterpriseName'],
                          'CCE Routing Script(s)': ' | '.join(sorted(set(ct_script.get(ctid, [])))) or '(none mapped)',
                          'Dialed Numbers': ' | '.join(sorted({d['DialedNumberString'] for d in dl})),
                          'Candidate Queue': name if name in queue_names else '',
                          'Action': 'Rebuild routing script as a WxCC flow (Flow Designer / prompt-to-flow)'})
    if epm_rows and not a.dn_prefix:
        warn.append('Entry point mappings use raw CCE dialed numbers (internal 4-digit DNs). Re-run with '
                    '--dn-prefix or edit 08_entry_point_mappings.csv with numbers from your WxCC PSTN inventory.')
    routing_req['entry_points'] = flow_rows

    # ================================================================ 6. aux codes
    aux_rows, dual = [], []
    for rc in sorted(D('ReasCode'), key=lambda r: r['ReasonCode']):
        if not alive(rc): continue
        if rc['ReasonCode'] in SYSTEM_REASON_CODES:
            skipped['Reason Code'].append(('%s (%s)' % (rc['ReasonText'], rc['ReasonCode']), 'Cisco system reason code')); continue
        usage = rc.get('ReasonCodeUsage') or 0
        kind = 'wrapup' if usage & 2 else 'idle' if usage & 1 else None
        if not kind:
            skipped['Reason Code'].append((rc['ReasonText'], 'usage flag %s not Not-Ready/Wrap-up' % usage)); continue
        if usage & 3 == 3: dual.append(rc['ReasonText'])
        aux_rows.append({'Name': clean_name(rc['ReasonText']),
                         'Description': clean_name('CCE reason code %s. %s' % (rc['ReasonCode'], rc.get('Description') or ''), 255),
                         'Default': 'OFF', 'Work Type': DEFAULT_WORK_TYPES[kind]})
        crosswalk.append(('Reason_Code', rc['ReasonCode'], rc['ReasonText'], 'Aux Code (%s)' % kind, rc['ReasonText']))
    if dual:
        notes.append('%d reason codes are flagged for Not Ready AND Wrap-up in CCE (%s); created as wrap-up codes only, '
                     'because bulk import keys on Name (one object per name).' % (len(dual), ', '.join(sorted(dual))))

    # ================================================================ 7. global variables (ECC)
    gv_rows = []
    for e in sorted(D('ExCaVa'), key=lambda r: r['EnterpriseName']):
        n = e['EnterpriseName']
        if e.get('Enabled') == 'N':
            skipped['ECC Variable'].append((n, 'disabled in CCE')); continue
        if e.get('CiscoProvided') == 'Y' or n.startswith(ECC_PLUMBING):
            skipped['ECC Variable'].append((n, 'Cisco/CVP/ECE platform variable - no WxCC equivalent needed')); continue
        if e.get('ECCArray') == 'Y':
            warn.append('ECC %s is an array (%s); created as a single STRING.' % (n, e.get('MaximumArraySize')))
        vn = var_name(n)
        gv_rows.append({'Name': vn, 'Description': clean_name((e.get('Description') or 'Migrated from CCE ECC %s' % n) +
                                                              ' (max length %s)' % e['MaximumLength'], 255),
                        'Agent Editable': 'OFF', 'Agent Viewable': 'ON', 'Variable Type': 'STRING',
                        'Default Value': 'uninitialized', 'Reportable': 'OFF', 'Desktop Label': vn[:50]})
        crosswalk.append(('Expanded_Call_Variable', e['ExpandedCallVariableID'], n, 'Global Variable', vn))

    # ================================================================ 8. desktop profiles
    dp_rows, desk = [], {}
    for s in D('AgDeSe'):
        desk[s['AgentDeskSettingsID']] = clean_name(s['EnterpriseName'])
        dp_rows.append({'Name': clean_name(s['EnterpriseName']), 'Description': 'Migrated from CCE Agent Desk Settings',
                        'Parent Site': '', 'Wrap Up Type': 'MANUAL', 'Auto Wrap Up Time': '',
                        'Agent Available After Outdial': 'OFF', 'Allow Auto Wrap Up Extension': 'OFF',
                        'Wrap Up Options': 'ALL', 'Idle Options': 'ALL', 'Transfer Options': 'ALL',
                        'Buddy Team Option': 'ALL', 'Consult To Queue': 'ON', 'Outdial Enabled': 'OFF',
                        'Address Book': 'NONE', 'Dial Plan Enabled': 'OFF', 'DN Validation Option': 'UNRESTRICTED',
                        'Agent Statistics': 'ON', 'Queue Statistics Option': 'ALL', 'Logged In Team Statistics': 'ON',
                        'Team Statistics Option': 'ALL'})
        crosswalk.append(('Agent_Desk_Settings', s['AgentDeskSettingsID'], s['EnterpriseName'], 'Desktop Profile', s['EnterpriseName']))
    notes.append('Desktop profiles carry the CCE names with WxCC defaults (manual wrap-up, ALL codes/teams/queues). '
                 'CCE desk-setting flags are decoded but not yet named (see decoded/AgDeSe.csv) - review before go-live.')

    # ================================================================ 9. users
    u_rows, ch_users = [], []
    for aid, ag in sorted(agents.items(), key=lambda kv: kv[1]['PeripheralNumber'] or ''):
        p = persons.get(ag['PersonID'], {})
        email = (p.get('Email') or '').strip()
        if not email:
            login = (p.get('LoginName') or ag['PeripheralNumber']).strip()
            email = login.lower() if re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', login) else '%s@%s' % (login.split('@')[0].lower(), a.email_domain)
        is_sup = ag.get('SupervisorAgent') == 'Y' or aid in supervisors
        tms = sorted(agent_teams[aid] | (sup_teams[aid] if is_sup else set()))
        row = {'Email': email, 'User Profile': a.supervisor_user_profile if is_sup else a.agent_user_profile,
               'Contact Center Enabled': 'On', 'Site': site if tms else '', 'Teams': '|'.join(tms),
               'Skill Profile': agent_sp.get(aid, ''), 'Desktop Profile': desk.get(ag['AgentDeskSettingsID'], '') if tms else '',
               'Multimedia Profile': mmp_name(agent_channels[aid]), 'External Id': ag['PeripheralNumber'], 'Default DN': ''}
        if not tms: warn.append('Agent %s (%s) is in no team - Site/Teams left blank, cannot log in to Agent Desktop until assigned.' % (ag['PeripheralNumber'], email))
        u_rows.append(row)
        ch_users.append({'First Name': p.get('FirstName', ''), 'Last Name': p.get('LastName', ''),
                         'Display Name': ('%s %s' % (p.get('FirstName', ''), p.get('LastName', ''))).strip(),
                         'User ID/Email (Required)': email, 'CCE Login': p.get('LoginName', ''),
                         'CCE Agent ID': ag['PeripheralNumber'], 'Email source': 'CCE Person.Email' if p.get('Email') else ('CCE login name' if not email.endswith('@' + a.email_domain) else 'generated')})
        crosswalk.append(('Agent', aid, ag['PeripheralNumber'], 'User', email))
    gen = sum(1 for r in ch_users if r['Email source'] == 'generated')
    if gen: warn.append('%d of %d agents have no e-mail in CCE; generated <login>@%s. Replace with real Webex identities.' % (gen, len(ch_users), a.email_domain))

    # ================================================================ write CSVs
    data = {'auxiliary_codes': aux_rows, 'skill_definitions': skills, 'skill_profiles': sp_rows,
            'multimedia_profiles': sorted(mmps.values(), key=lambda r: r['Name']),
            'sites': [{'Name': site, 'Multimedia Profile': default_mmp}], 'teams': team_rows,
            'entry_points': ep_rows, 'entry_point_mappings': epm_rows, 'queues': q_rows,
            'global_variables': gv_rows, 'desktop_profiles': dp_rows, 'users': u_rows}
    files = []
    for i, key in enumerate(IMPORT_ORDER, 1):
        fn = '%02d_%s.csv' % (i, key)
        write_csv(os.path.join(a.out_dir, fn), HEADERS[key], data[key]); files.append((fn, key, data[key]))
        if key == 'entry_points' and ep_digital:
            write_csv(os.path.join(a.out_dir, '%02db_entry_points_digital.csv' % i), HEADERS[key], ep_digital)
    write_csv(os.path.join(a.out_dir, 'controlhub_users_to_create.csv'), list(ch_users[0].keys()) if ch_users else ['Email'], ch_users)
    write_csv(os.path.join(a.out_dir, 'flow_inventory.csv'), ['Entry Point', 'Channel', 'CCE Call Type', 'CCE Routing Script(s)',
                                                              'Dialed Numbers', 'Candidate Queue', 'Action'], flow_rows)
    write_csv(os.path.join(a.out_dir, 'crosswalk.csv'), ['CCE Table', 'CCE ID', 'CCE Name', 'WxCC Object', 'WxCC Name'],
              [dict(zip(['CCE Table', 'CCE ID', 'CCE Name', 'WxCC Object', 'WxCC Name'], c)) for c in crosswalk])
    json.dump(routing_req, open(os.path.join(a.out_dir, 'routing_requirements.json'), 'w'), indent=1, default=str)
    # read by validate_wxcc_csv.py so placeholders show up in validation_report.md too
    json.dump({'defaults_used': defaults_used, 'email_domain': a.email_domain, 'generated_emails': sorted(r['User ID/Email (Required)'].lower() for r in ch_users if r['Email source'] == 'generated'),
               'dn_prefix': a.dn_prefix, 'existing': a.existing},
              open(os.path.join(a.out_dir, '_run_context.json'), 'w'), indent=1)

    # ---- tenant diff (idempotency preview)
    diff = []
    if a.existing:
        ex = parse_tenant_export(a.existing)
        sec = {'queues': 'QUEUES (CONTACT SERVICE QUEUES)', 'skill_definitions': 'SKILLS', 'teams': 'TEAMS',
               'entry_points': 'ENTRY POINTS (INBOUND)', 'auxiliary_codes': 'AUXILIARY CODES',
               'global_variables': 'GLOBAL VARIABLES', 'desktop_profiles': 'DESKTOP PROFILES', 'users': 'USERS',
               'entry_point_mappings': 'DIALED NUMBER MAPPINGS', 'multimedia_profiles': 'MULTIMEDIA PROFILES'}
        for key, s in sec.items():
            names = ex.get(s, set())
            keycol = HEADERS[key][0]
            mine = {r.get(keycol) for r in data[key] if r.get(keycol)}
            diff.append((key, len(mine - names), len(mine & names), sorted(mine & names)))

    # ---- report
    R = []
    R.append('# CCE -> Webex Contact Center migration report\n')
    R.append('Generated from `%s`. Site: **%s**, timezone: **%s**.\n' % (a.decoded_dir, site, a.timezone))
    R.append('## Source inventory (active objects)\n')
    R.append('| CCE object | Count |\n|---|---|')
    for k, v in [('Agents', len(agents)), ('Agent teams', len(teams)), ('Attributes', len(attrs)),
                 ('Precision queues', len(pqs)), ('Skill groups', len(sgs)), ('Call types', len(calltypes)),
                 ('Dialed numbers', len(dns)), ('Reason codes', len(D('ReasCode'))), ('ECC variables', len(D('ExCaVa'))),
                 ('Routing scripts (master)', len(masters)), ('Agent desk settings', len(D('AgDeSe')))]:
        R.append('| %s | %d |' % (k, v))
    R.append('\n## Bulk upload files (load in this order)\n')
    R.append('| # | File | Object | Rows |\n|---|---|---|---|')
    for fn, key, rows in files:
        R.append('| %s | `%s` | %s | %d |' % (fn[:2], fn, key.replace('_', ' ').title(), len(rows)))
    if ep_digital:
        R.append('| 07b | `07b_entry_points_digital.csv` | Digital entry points (load after Webex Connect assets exist) | %d |' % len(ep_digital))
    R.append('\nBefore step 12 (Users): create/licence the people in `controlhub_users_to_create.csv` in Control Hub, '
             'and confirm the user profile names "%s" / "%s" exist in the tenant.\n' % (a.agent_user_profile, a.supervisor_user_profile))
    if diff:
        R.append('## Tenant diff (bulk import upserts by Name)\n')
        R.append('| Object | New | Already in tenant (will UPDATE) |\n|---|---|---|')
        for key, new, upd, names in diff:
            R.append('| %s | %d | %d %s |' % (key, new, upd, ('(' + ', '.join(names[:8]) + ')') if names else ''))
        R.append('')
    else:
        R.append('## Tenant diff (bulk import upserts by Name)\n')
        R.append('**Not performed**: no `--existing` tenant export was given, so every object is counted as a CREATE. '
                 'Any name that already exists in the tenant will be UPDATED (overwritten) on import. Before importing, '
                 're-run with `--existing <export>` or check the names with the MCP `list` tools.\n')
    R.append('## Needs a human / not in bulk CSV\n')
    R.append('- **Routing logic**: %d entry points need a flow. See `flow_inventory.csv` (CCE script per call type) and '
             '`routing_requirements.json` (skill requirements per queue, for the Queue Contact node).' % len(flow_rows))
    R.append('- **Phone numbers**: `08_entry_point_mappings.csv` must contain numbers from the WxCC PSTN inventory.')
    for w in warn: R.append('- %s' % w)
    for n in notes: R.append('- %s' % n)
    R.append('\n## Not migrated (by design)\n')
    for k, lst in skipped.items():
        R.append('<details><summary>%s - %d</summary>\n' % (k, len(lst)))
        for nm, why in lst: R.append('- `%s` - %s' % (nm, why))
        R.append('\n</details>\n')
    open(os.path.join(a.out_dir, 'migration_report.md'), 'w').write('\n'.join(R) + '\n')
    print('wrote %d bulk files to %s' % (len(files), a.out_dir))
    for fn, key, rows in files: print('  %-34s %4d rows' % (fn, len(rows)))
    print('  warnings: %d   skipped objects: %d' % (len(warn), sum(len(v) for v in skipped.values())))


if __name__ == '__main__':
    main()
