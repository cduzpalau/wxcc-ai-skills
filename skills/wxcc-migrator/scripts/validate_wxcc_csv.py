#!/usr/bin/env python3
"""
validate_wxcc_csv.py - Pre-flight check of generated WxCC Bulk Operations CSVs.

usage: validate_wxcc_csv.py <bulk_dir> [--existing-site NAME ...] [--existing-team NAME ...]

Checks: exact headers, row limit, required values, enum values, naming rules,
duplicate keys, numeric ranges and cross-file references (skills used in profiles,
teams in queues/users, entry points in mappings, sites, profiles).
Writes <bulk_dir>/validation_report.md. Exit code 1 if any ERROR.
"""
import argparse, collections, csv, glob, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wxcc_bulk_spec import HEADERS, ENUMS, ROW_LIMIT, DEFAULT_WORK_TYPES  # noqa: E402


def read(path):
    with open(path, newline='', encoding='utf-8') as f:
        r = list(csv.reader(f))
    return (r[0], [dict(zip(r[0], row)) for row in r[1:]]) if r else ([], [])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('bulk_dir')
    ap.add_argument('--existing-site', action='append', default=[])
    ap.add_argument('--existing-team', action='append', default=[])
    a = ap.parse_args()
    issues = []                                     # (level, file, row, message)
    E = lambda f, r, m: issues.append(('ERROR', f, r, m))
    W = lambda f, r, m: issues.append(('WARN', f, r, m))
    data, fname = {}, {}
    # placeholders the transform had to use (written by cce_to_wxcc.py); absent if CSVs came from elsewhere
    ctx_path = os.path.join(a.bulk_dir, '_run_context.json')
    ctx = json.load(open(ctx_path)) if os.path.exists(ctx_path) else {}
    for msg in ctx.get('defaults_used', []): W('_run_context.json', 0, msg)
    if ctx and not ctx.get('existing'):
        W('_run_context.json', 0, 'no tenant export (--existing) - create/update diff not performed; name collisions will UPDATE')
    generated = set(ctx.get('generated_emails', []))
    for path in sorted(glob.glob(os.path.join(a.bulk_dir, '[0-9][0-9]*_*.csv'))):
        fn = os.path.basename(path)
        key = re.sub(r'^\d+b?_', '', fn[:-4])
        if key == 'entry_points_digital': key_spec = 'entry_points'
        else: key_spec = key
        if key_spec not in HEADERS:
            W(fn, 0, 'unknown object type, skipped'); continue
        hdr, rows = read(path)
        if hdr != HEADERS[key_spec]:
            E(fn, 1, 'header mismatch. expected: %s' % ','.join(HEADERS[key_spec]))
        if len(rows) > ROW_LIMIT:
            E(fn, 0, '%d rows > %d limit - split the file' % (len(rows), ROW_LIMIT))
        if os.path.getsize(path) > 5 * 1024 * 1024:
            E(fn, 0, 'file larger than 5 MB')
        for i, r in enumerate(rows, 2):
            for (k, col), allowed in ENUMS.items():
                if k == key_spec and r.get(col) not in allowed and r.get(col, '') != '':
                    E(fn, i, '%s="%s" not in %s' % (col, r.get(col), sorted(allowed)))
        data.setdefault(key, []).extend(rows); fname[key] = fn

    def names(key, col='Name'):
        return {r[col] for r in data.get(key, []) if r.get(col)}

    # ---- per object rules
    for r_i, r in enumerate(data.get('skill_definitions', []), 2):
        f = fname['skill_definitions']
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _\-.]{0,79}', r['Name']): E(f, r_i, 'skill name "%s" invalid (letter first, <=80)' % r['Name'])
        if r['Type'] == 'ENUM' and not r['List Values For Enum']: E(f, r_i, 'ENUM skill without values')
        if not r['Service Level Threshold'].isdigit(): E(f, r_i, 'Service Level Threshold must be an integer')
    for key in ('skill_definitions', 'teams', 'entry_points', 'entry_points_digital', 'auxiliary_codes', 'global_variables',
                'desktop_profiles', 'multimedia_profiles', 'sites'):
        c = collections.Counter(r['Name'] for r in data.get(key, []))
        for n, k in c.items():
            if k > 1 and key in fname: E(fname[key], 0, 'duplicate Name "%s" (%d rows) - bulk upsert would overwrite' % (n, k))
    stype = {r['Name']: r['Type'] for r in data.get('skill_definitions', [])}
    sp_names = set()
    for i, r in enumerate(data.get('skill_profiles', []), 2):
        f = fname['skill_profiles']; sp_names.add(r['Name'])
        if not r['Skill Name']: continue
        t = stype.get(r['Skill Name'])
        if not t: E(f, i, 'skill "%s" not defined in skill_definitions' % r['Skill Name']); continue
        v = r['Skill Values']
        if t == 'PROFICIENCY' and not (v.isdigit() and 0 <= int(v) <= 10): E(f, i, 'proficiency "%s" not 0-10' % v)
        if t == 'BOOLEAN' and v.lower() not in ('true', 'false'): E(f, i, 'boolean value "%s"' % v)
    sites = names('sites') | set(a.existing_site)
    mmps = names('multimedia_profiles')
    teams = names('teams') | set(a.existing_team)
    for i, r in enumerate(data.get('teams', []), 2):
        f = fname['teams']
        if r['Site'] not in sites: E(f, i, 'site "%s" not defined' % r['Site'])
        if r['Multimedia Profile'] and r['Multimedia Profile'] not in mmps: E(f, i, 'multimedia profile not defined')
        if r['Type'] == 'CAPACITY' and not r['DN']: E(f, i, 'CAPACITY team needs a DN')
    for i, r in enumerate(data.get('sites', []), 2):
        if r['Multimedia Profile'] and r['Multimedia Profile'] not in mmps: E(fname['sites'], i, 'multimedia profile not defined')
    for i, r in enumerate(data.get('multimedia_profiles', []), 2):
        f = fname['multimedia_profiles']
        try:
            if int(r['Voice']) not in (0, 1): E(f, i, 'Voice must be 0/1')
            for c in ('Chat', 'Email', 'Social'):
                if not 0 <= int(r[c]) <= 5: E(f, i, '%s must be 0-5' % c)
        except ValueError:
            E(f, i, 'non-numeric channel capacity')
    eps = names('entry_points') | names('entry_points_digital')
    for i, r in enumerate(data.get('entry_point_mappings', []), 2):
        f = fname['entry_point_mappings']
        if r['Entry Point'] not in eps: E(f, i, 'entry point "%s" not defined' % r['Entry Point'])
        if not re.fullmatch(r'\+?\d+', r['Dialed Number']): E(f, i, 'dialed number "%s" not numeric' % r['Dialed Number'])
        elif not r['Dialed Number'].startswith('+') or len(r['Dialed Number']) < 8:
            W(f, i, 'dialed number "%s" is not E.164 - must exist in the tenant PSTN inventory' % r['Dialed Number'])
    seen_dn = collections.Counter(r['Dialed Number'] for r in data.get('entry_point_mappings', []))
    for dn, k in seen_dn.items():
        if k > 1: E(fname['entry_point_mappings'], 0, 'dialed number %s mapped %d times' % (dn, k))
    qparents, qgroups = {}, collections.defaultdict(list)
    for i, r in enumerate(data.get('queues', []), 2):
        f = fname['queues']
        if r['Distribution Group']:
            qgroups[r['Name']].append((i, r))
            for t in [x.split(':')[0].strip() for x in r['Group Teams'].split('|') if x]:
                if t not in teams: E(f, i, 'queue %s: team "%s" not defined' % (r['Name'], t))
            if not r['Group Teams']: E(f, i, 'distribution group without teams')
        else:
            if r['Name'] in qparents: E(f, i, 'queue "%s" defined twice' % r['Name'])
            qparents[r['Name']] = r
            if r['Routing Type'] == 'SKILLS_BASED' and not r['Skill-Based Agent Selection']:
                E(f, i, 'SKILLS_BASED queue needs Skill-Based Agent Selection')
            if r['Channel Type'] == 'TELEPHONY' and not r['Default Music in Queue']:
                W(f, i, 'telephony queue without Default Music in Queue')
    for q in qparents:
        if not qgroups.get(q): E(fname['queues'], 0, 'queue "%s" has no distribution group' % q)
        seqs = [int(r['Distribution Group Seq']) for _, r in qgroups.get(q, [])]
        if seqs and seqs != list(range(1, len(seqs) + 1)): E(fname['queues'], 0, 'queue "%s" group seq not 1..n' % q)
    for q in qgroups:
        if q not in qparents: E(fname['queues'], 0, 'distribution group rows for undefined queue "%s"' % q)
    for i, r in enumerate(data.get('auxiliary_codes', []), 2):
        if r['Work Type'] not in DEFAULT_WORK_TYPES.values():
            W(fname['auxiliary_codes'], i, 'work type "%s" must already exist in the tenant' % r['Work Type'])
    for i, r in enumerate(data.get('global_variables', []), 2):
        f = fname['global_variables']
        if not re.fullmatch(r'[A-Za-z0-9_]{1,80}', r['Name']): E(f, i, 'variable name "%s" invalid (alnum/_ only)' % r['Name'])
        if len(r['Desktop Label']) > 50: E(f, i, 'Desktop Label > 50 chars')
        if r['Variable Type'] == 'STRING' and len(r['Default Value']) > 256: E(f, i, 'default value > 256 chars')
    dps = names('desktop_profiles')
    emails = collections.Counter()
    for i, r in enumerate(data.get('users', []), 2):
        f = fname['users']; emails[r['Email'].lower()] += 1
        if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', r['Email']): E(f, i, 'invalid email "%s"' % r['Email'])
        if r['Email'].lower() in generated or r['Email'].lower().endswith('@example.com'):
            W(f, i, 'placeholder e-mail %s' % r['Email'])
        if r['Site'] and r['Site'] not in sites: E(f, i, 'site "%s" not defined' % r['Site'])
        for t in [x for x in r['Teams'].split('|') if x]:
            if t not in teams: E(f, i, 'team "%s" not defined' % t)
        if (r['Site'] or r['Teams']) and not r['Desktop Profile']: E(f, i, 'Desktop Profile required when Site/Teams set')
        if r['Desktop Profile'] and r['Desktop Profile'] not in dps: W(f, i, 'desktop profile "%s" must already exist' % r['Desktop Profile'])
        if r['Skill Profile'] and r['Skill Profile'] not in sp_names: E(f, i, 'skill profile "%s" not defined' % r['Skill Profile'])
        if r['Multimedia Profile'] and r['Multimedia Profile'] not in mmps: E(f, i, 'multimedia profile not defined')
        if not r['Teams']: W(f, i, 'user %s has no team (cannot log in to Agent Desktop)' % r['Email'])
    for e, k in emails.items():
        if k > 1: E(fname['users'], 0, 'email %s appears %d times' % (e, k))

    # ---- report
    errs = [x for x in issues if x[0] == 'ERROR']; warns = [x for x in issues if x[0] == 'WARN']
    out = ['# Bulk CSV validation report\n', '**%d errors, %d warnings** across %d files.\n' % (len(errs), len(warns), len(fname)),
           '| Object | File | Rows |', '|---|---|---|']
    for k, f in fname.items(): out.append('| %s | `%s` | %d |' % (k, f, len(data[k])))
    for lvl, lst in (('Errors', errs), ('Warnings', warns)):
        out.append('\n## %s\n' % lvl)
        if not lst: out.append('None.')
        grouped = collections.defaultdict(list)
        for _, f, r, m in lst: grouped[f].append((r, m))
        for f, items in grouped.items():
            out.append('**%s** (%d)' % (f, len(items)))
            for r, m in items[:25]: out.append('- row %s: %s' % (r, m))
            if len(items) > 25: out.append('- ... %d more' % (len(items) - 25))
    open(os.path.join(a.bulk_dir, 'validation_report.md'), 'w').write('\n'.join(out) + '\n')
    print('validation: %d errors, %d warnings -> %s' % (len(errs), len(warns), os.path.join(a.bulk_dir, 'validation_report.md')))
    for lvl, f, r, m in errs[:20]: print('  ERROR %s row %s: %s' % (f, r, m))
    sys.exit(1 if errs else 0)


if __name__ == '__main__':
    main()
