#!/usr/bin/env python3
"""
run_migration.py - One-shot pipeline: decode -> transform -> validate.

usage: run_migration.py <cce_export_dir> <run_dir> [any cce_to_wxcc.py option ...]

Creates
  <run_dir>/1-decoded/      readable CSV/JSON per CCE table + _DECODE_SUMMARY.md
  <run_dir>/2-wxcc-bulk/    numbered bulk CSVs, migration_report.md, validation_report.md, ...
"""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(args):
    print('$ ' + ' '.join(os.path.basename(x) if i == 1 else x for i, x in enumerate(args)), flush=True)
    return subprocess.call(args)


def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(2)
    src, run_dir, extra = sys.argv[1], sys.argv[2], sys.argv[3:]
    dec, bulk = os.path.join(run_dir, '1-decoded'), os.path.join(run_dir, '2-wxcc-bulk')
    py = sys.executable
    if run([py, os.path.join(HERE, 'cce_decode.py'), 'decode', src, dec]) != 0:
        print('decode reported errors - fix the layout in references/cce_schemas.json first'); sys.exit(1)
    if run([py, os.path.join(HERE, 'cce_to_wxcc.py'), dec, bulk] + extra) != 0:
        sys.exit(1)
    rc = run([py, os.path.join(HERE, 'validate_wxcc_csv.py'), bulk])
    print('\nNext: read %s/migration_report.md and validation_report.md' % bulk)
    sys.exit(rc)


if __name__ == '__main__':
    main()
