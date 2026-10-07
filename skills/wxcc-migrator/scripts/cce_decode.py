#!/usr/bin/env python3
"""
cce_decode.py - Turn a UCCE/PCCE ICMDBA configuration export (*.raw files) into
human-readable CSV/JSON.

The .raw files are SQL Server `bcp` NATIVE-format dumps of the ICM config tables
(one file per table, file name = abbreviated table name, e.g. SkilGrou.raw =
Skill_Group). There is no header and no delimiter, so a column layout is needed
for every table. Layouts live in references/cce_schemas.json.

Sub-commands
  decode  <export_dir> <out_dir> [--schemas FILE]
        Decode every known table to <out_dir>/<File>.csv + .json, write a preview
        (strings + hex) for unknown tables, and a manifest + summary.
  walk    <raw_file> "Col:TYPE Col:TYPE ..." [--offset N]
        Step through the FIRST record with a candidate layout and print each value.
        Use it to work out a layout for a table that is not in the schema file yet.
  profile <raw_file> "Col:TYPE ..."
        Parse the WHOLE file with a candidate layout; on success print the distinct
        values per column, on failure show the row and bytes where it broke.

  roster  <decoded_dir>
        Write <decoded_dir>/_agent_roster.csv (agent, name, login, teams, supervised
        teams). Also runs automatically at the end of `decode`.

Types: I4 I2 I1 (fixed ints)  C1 (fixed char(1))  DT (fixed datetime)  F8 (float)
       VC (varchar, 2-byte len, FFFF = NULL)  FN (nullable fixed, 1-byte len, FF = NULL)
       TXT (text/image, 4-byte len)
"""
import argparse, collections, csv, datetime, json, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SCHEMAS = os.path.join(HERE, '..', 'references', 'cce_schemas.json')
SENSITIVE = {'Password'}          # never written in clear text


# ---------------------------------------------------------------- bcp native reader
def _dt(b):
    days, ticks = struct.unpack('<iI', b)
    t = datetime.datetime(1900, 1, 1) + datetime.timedelta(days=days, seconds=ticks / 300)
    return t.strftime('%Y-%m-%d %H:%M:%S')


def read_value(d, p, t):
    """Return (value, new_offset). Raises ValueError on malformed data."""
    n = len(d)
    if t == 'I4':
        if p + 4 > n: raise ValueError('I4 past EOF')
        return struct.unpack_from('<i', d, p)[0], p + 4
    if t == 'I2':
        if p + 2 > n: raise ValueError('I2 past EOF')
        return struct.unpack_from('<h', d, p)[0], p + 2
    if t == 'I1':
        if p + 1 > n: raise ValueError('I1 past EOF')
        return d[p], p + 1
    if t == 'C1':
        if p + 1 > n: raise ValueError('C1 past EOF')
        return d[p:p + 1].decode('latin-1'), p + 1
    if t == 'DT':
        if p + 8 > n: raise ValueError('DT past EOF')
        return _dt(d[p:p + 8]), p + 8
    if t == 'F8':
        if p + 8 > n: raise ValueError('F8 past EOF')
        return struct.unpack_from('<d', d, p)[0], p + 8
    if t == 'VC':
        if p + 2 > n: raise ValueError('VC prefix past EOF')
        ln = struct.unpack_from('<H', d, p)[0]
        if ln == 0xFFFF: return None, p + 2
        if p + 2 + ln > n: raise ValueError('VC length %d past EOF' % ln)
        return d[p + 2:p + 2 + ln].decode('latin-1'), p + 2 + ln
    if t == 'FN':
        if p >= n: raise ValueError('FN past EOF')
        ln = d[p]
        if ln == 0xFF: return None, p + 1
        if ln not in (1, 2, 4, 8) or p + 1 + ln > n:
            raise ValueError('FN bad length byte 0x%02x' % ln)
        b = d[p + 1:p + 1 + ln]
        v = {1: lambda: b[0], 2: lambda: struct.unpack('<h', b)[0],
             4: lambda: struct.unpack('<i', b)[0], 8: lambda: _dt(b)}[ln]()
        return v, p + 1 + ln
    if t == 'TXT':
        if p + 4 > n: raise ValueError('TXT prefix past EOF')
        ln = struct.unpack_from('<I', d, p)[0]
        if ln == 0xFFFFFFFF: return None, p + 4
        if p + 4 + ln > n: raise ValueError('TXT length past EOF')
        return d[p + 4:p + 4 + ln].hex(), p + 4 + ln
    raise ValueError('unknown type ' + t)


def parse_table(d, cols):
    rows, p = [], 0
    while p < len(d):
        start, r = p, {}
        for name, t in cols:
            try:
                r[name], p = read_value(d, p, t)
            except ValueError as e:
                raise ValueError('row %d (byte %d) column %s: %s' % (len(rows), start, name, e))
        rows.append(r)
    return rows


def parse_layout(s):
    return [c.split(':', 1) for c in s.split()]


# ---------------------------------------------------------------- helpers for unknown tables
def strings_preview(d, minlen=3, limit=60):
    out, cur, start = [], bytearray(), 0
    for i, b in enumerate(d):
        if 0x20 <= b < 0x7f:
            if not cur: start = i
            cur.append(b)
        else:
            if len(cur) >= minlen: out.append((start, cur.decode()))
            cur = bytearray()
    if len(cur) >= minlen: out.append((start, cur.decode()))
    return out[:limit]


def hexdump(d, length=256):
    lines = []
    for off in range(0, min(len(d), length), 16):
        chunk = d[off:off + 16]
        hx = ' '.join('%02x' % b for b in chunk)
        tx = ''.join(chr(b) if 0x20 <= b < 0x7f else '.' for b in chunk)
        lines.append('%08x  %-47s  %s' % (off, hx, tx))
    return '\n'.join(lines)


# ---------------------------------------------------------------- commands
def cmd_decode(a):
    schemas = json.load(open(a.schemas))['tables']
    os.makedirs(a.out_dir, exist_ok=True)
    prev_dir = os.path.join(a.out_dir, '_unknown_preview')
    manifest, version = [], None
    for fn in sorted(os.listdir(a.export_dir)):
        path = os.path.join(a.export_dir, fn)
        if not os.path.isfile(path) or fn.startswith('.'): continue
        base, ext = os.path.splitext(fn)
        d = open(path, 'rb').read()
        if fn == 'Version':
            version = ' '.join(d.decode('latin-1').split())
            manifest.append(dict(file=fn, table='(export version)', bytes=len(d), rows='', status='info', note=version))
            continue
        if ext.lower() != '.raw':
            manifest.append(dict(file=fn, table='', bytes=len(d), rows='', status='skipped', note='not a .raw file'))
            continue
        if len(d) == 0:
            manifest.append(dict(file=fn, table=schemas.get(base, {}).get('table', ''), bytes=0, rows=0,
                                 status='empty', note='table has no rows'))
            continue
        if base in schemas:
            sc = schemas[base]
            try:
                rows = parse_table(d, sc['columns'])
            except ValueError as e:
                manifest.append(dict(file=fn, table=sc['table'], bytes=len(d), rows='', status='ERROR', note=str(e)))
                continue
            cols = [c for c, _ in sc['columns']]
            for r in rows:
                for c in cols:
                    if c in SENSITIVE and r[c] is not None: r[c] = '***masked***'
            with open(os.path.join(a.out_dir, base + '.csv'), 'w', newline='', encoding='utf-8') as f:
                w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
            json.dump({'table': sc['table'], 'source_file': fn, 'rows': rows},
                      open(os.path.join(a.out_dir, base + '.json'), 'w'), indent=1, default=str)
            unknown = sum(1 for c in cols if c[:1] == 'c' and c[1:].isdigit())
            manifest.append(dict(file=fn, table=sc['table'], bytes=len(d), rows=len(rows), status='decoded',
                                 note='%d columns (%d not yet named)' % (len(cols), unknown)))
        else:
            os.makedirs(prev_dir, exist_ok=True)
            with open(os.path.join(prev_dir, base + '.txt'), 'w') as f:
                f.write('# %s  (%d bytes)  - no layout in cce_schemas.json yet\n\n' % (fn, len(d)))
                f.write('## printable strings (offset: text)\n')
                for off, s in strings_preview(d): f.write('%6d: %s\n' % (off, s))
                f.write('\n## first 256 bytes\n' + hexdump(d) + '\n')
            manifest.append(dict(file=fn, table='?', bytes=len(d), rows='', status='needs-layout',
                                 note='preview in _unknown_preview/%s.txt' % base))
    with open(os.path.join(a.out_dir, '_manifest.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['file', 'table', 'bytes', 'rows', 'status', 'note'])
        w.writeheader(); w.writerows(manifest)
    st = collections.Counter(m['status'] for m in manifest)
    roster = write_roster(a.out_dir)
    with open(os.path.join(a.out_dir, '_DECODE_SUMMARY.md'), 'w') as f:
        f.write('# CCE export decode summary\n\nSource: `%s`  \nExport schema version: %s\n\n' % (a.export_dir, version))
        f.write('| Status | Files |\n|---|---|\n' + ''.join('| %s | %d |\n' % kv for kv in sorted(st.items())))
        f.write('\n## Decoded tables\n\n| File | Table | Rows | Note |\n|---|---|---|---|\n')
        for m in manifest:
            if m['status'] == 'decoded': f.write('| %s | %s | %s | %s |\n' % (m['file'], m['table'], m['rows'], m['note']))
        if roster is not None:
            f.write('\nAgent roster (Agent + Person + teams, %d active agents): `_agent_roster.csv`\n' % roster)
        f.write('\n## Needs a layout (non-empty, not decoded)\n\n')
        for m in manifest:
            if m['status'] in ('needs-layout', 'ERROR'):
                f.write('- %s (%s bytes) - %s\n' % (m['file'], m['bytes'], m['note']))
    print('decoded=%d empty=%d needs-layout=%d errors=%d -> %s' % (
        st['decoded'], st['empty'], st['needs-layout'], st['ERROR'], a.out_dir))
    return 1 if st['ERROR'] else 0


def write_roster(out_dir):
    """Join Agent + Person + Agent_Team(_Member/_Supervisor) into _agent_roster.csv: the
    "who is who" view people ask for first. Returns the row count, or None if a table is missing."""
    def rows(base):
        p = os.path.join(out_dir, base + '.json')
        return json.load(open(p))['rows'] if os.path.exists(p) else None
    agents, persons, teams = rows('Agent'), rows('Person'), rows('AgenTeam')
    if agents is None or persons is None or teams is None: return None
    person = {r['PersonID']: r for r in persons}
    team = {r['AgentTeamID']: r['EnterpriseName'] for r in teams}
    member, supervises = collections.defaultdict(set), collections.defaultdict(set)
    for r in rows('AgTeMe') or []: member[r['SkillTargetID']].add(team.get(r['AgentTeamID'], r['AgentTeamID']))
    for r in rows('AgTeSu') or []: supervises[r['SupervisorSkillTargetID']].add(team.get(r['AgentTeamID'], r['AgentTeamID']))
    out = []
    for ag in sorted(agents, key=lambda r: str(r.get('PeripheralNumber') or '')):
        if ag.get('Deleted') == 'Y': continue
        p, sid = person.get(ag['PersonID'], {}), ag['SkillTargetID']
        out.append({'AgentID': ag.get('PeripheralNumber'), 'FirstName': p.get('FirstName'), 'LastName': p.get('LastName'),
                    'LoginName': p.get('LoginName'), 'Email': p.get('Email') or '',
                    'Teams': '|'.join(sorted(member[sid])), 'Supervisor': ag.get('SupervisorAgent') or 'N',
                    'SupervisesTeams': '|'.join(sorted(supervises[sid]))})
    cols = ['AgentID', 'FirstName', 'LastName', 'LoginName', 'Email', 'Teams', 'Supervisor', 'SupervisesTeams']
    with open(os.path.join(out_dir, '_agent_roster.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(out)
    return len(out)


def cmd_roster(a):
    n = write_roster(a.decoded_dir)
    if n is None: print('Agent/Person/AgenTeam not decoded in %s' % a.decoded_dir); return 1
    print('%d agents -> %s' % (n, os.path.join(a.decoded_dir, '_agent_roster.csv')))
    return 0


def cmd_walk(a):
    d = open(a.raw_file, 'rb').read()
    p = a.offset
    for name, t in parse_layout(a.layout):
        try:
            v, q = read_value(d, p, t)
        except ValueError as e:
            print('  STOP %-20s %-3s @%d: %s' % (name, t, p, e)); break
        print('  %-24s %-3s @%-5d %-18s %r' % (name, t, p, d[p:q].hex()[:18], v)); p = q
    print('  next @%d: %s' % (p, ' '.join('%02x' % b for b in d[p:p + 40])))
    print('         %r' % d[p:p + 40])


def cmd_profile(a):
    d = open(a.raw_file, 'rb').read()
    cols = parse_layout(a.layout)
    try:
        rows = parse_table(d, cols)
    except ValueError as e:
        print('FAILED:', e)
        msg = str(e); start = int(msg.split('byte ')[1].split(')')[0])
        print(hexdump(d[start:start + 160]))
        return 1
    print('OK: %d rows, all %d bytes consumed' % (len(rows), len(d)))
    for c, t in cols:
        vals = collections.Counter(str(r[c]) for r in rows)
        print('  %-26s %-3s distinct=%-4d %s' % (c, t, len(vals), list(vals.items())[:5]))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    p = sp.add_parser('decode'); p.add_argument('export_dir'); p.add_argument('out_dir')
    p.add_argument('--schemas', default=DEFAULT_SCHEMAS)
    p = sp.add_parser('walk'); p.add_argument('raw_file'); p.add_argument('layout'); p.add_argument('--offset', type=int, default=0)
    p = sp.add_parser('profile'); p.add_argument('raw_file'); p.add_argument('layout')
    p = sp.add_parser('roster'); p.add_argument('decoded_dir')
    a = ap.parse_args()
    sys.exit({'decode': cmd_decode, 'walk': cmd_walk, 'profile': cmd_profile, 'roster': cmd_roster}[a.cmd](a) or 0)


if __name__ == '__main__':
    main()
