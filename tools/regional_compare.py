#!/usr/bin/env python3
"""Measure named original-function overlap without emitting game bytes.

pip install pyelftools
python tools/regional_compare.py --baseline ../SMS-Decomp-JP-1.0 --baseline-version GMSJ01
Build both repositories first. This uses dtk original objects, report addresses,
and original DOL bytes. Relocation-masked matches are candidates only: relocation
destinations and referenced data can differ even when the instruction body agrees.
"""
import argparse
import csv
import hashlib
import io
import json
import struct
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from elftools.elf.elffile import ELFFile

# ELF32 PowerPC relocation fields. Unknown types are never masked or accepted.
MASKS = {1: (4, 0xffffffff), 2: (4, 0x03fffffc), 3: (2, 0xffff),
         4: (2, 0xffff), 5: (2, 0xffff), 6: (2, 0xffff),
         7: (4, 0xfffc), 8: (4, 0xfffc), 9: (4, 0xfffc),
         10: (4, 0x03fffffc), 11: (4, 0xfffc), 12: (4, 0xfffc),
         13: (4, 0xfffc), 26: (4, 0xffffffff), 32: (2, 0xffff),
         109: (4, 0x001fffff)}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load(root, version, label=None):
    root = Path(root).resolve()
    config = json.loads((root / f'build/{version}/config.json').read_text())
    report = json.loads((root / f'build/{version}/report.json').read_text())
    report_units = {u['name']: u for u in report['units']}
    dol = (root / f'orig/{version}/sys/main.dol').read_bytes()
    sections = []
    for i in range(18):
        off, addr, size = [struct.unpack_from('>I', dol, p + i * 4)[0]
                           for p in (0, 0x48, 0x90)]
        if size:
            assert off + size <= len(dol)
            sections.append(dict(offset=off, address=addr, size=size, code=i < 7))
    functions = []
    for unit in config['units']:
        elf = ELFFile(io.BytesIO((root / unit['object']).read_bytes()))
        syms = elf.get_section_by_name('.symtab')
        relocs = defaultdict(list)
        for sec in elf.iter_sections():
            if sec['sh_type'] == 'SHT_RELA':
                relocs[sec['sh_info']].extend(sec.iter_relocations())
        unit_name = 'mario/' + str(Path(unit['name']).with_suffix('')).replace('\\', '/')
        ru = report_units[unit_name]
        addresses = {s['name']: int(s.get('metadata', {}).get('virtual_address', 0))
                     for s in ru.get('sections', [])}
        for sym in syms.iter_symbols():
            if (sym['st_info']['type'] != 'STT_FUNC' or
                    not isinstance(sym['st_shndx'], int) or sym['st_size'] == 0):
                continue
            sec = elf.get_section(sym['st_shndx'])
            if not sec['sh_flags'] & 4:
                continue
            start, size = sym['st_value'], sym['st_size']
            assert start + size <= sec.data_size
            addr = addresses[sec.name] + start
            ds = next((s for s in sections if s['address'] <= addr and
                       addr + size <= s['address'] + s['size']), None)
            if ds is None:
                raise ValueError((version, unit['name'], sym.name, hex(addr)))
            offset = ds['offset'] + addr - ds['address']
            raw = dol[offset:offset + size]
            masked = bytearray(sec.data()[start:start + size])
            signature, unsupported = [], False
            for reloc in relocs[sym['st_shndx']]:
                off = reloc['r_offset'] - start
                if not 0 <= off < size:
                    continue
                typ = reloc['r_info_type']
                signature.append((off, typ))
                item = MASKS.get(typ)
                if item is None or off + item[0] > size:
                    unsupported = True
                    continue
                width, mask = item
                val = int.from_bytes(masked[off:off + width], 'big') & ~mask
                masked[off:off + width] = val.to_bytes(width, 'big')
            functions.append(dict(name=sym.name, unit=unit['name'],
                                  address=f'0x{addr:08X}', size=size,
                                  exact=sha256(raw),
                                  masked=None if unsupported else sha256(
                                      masked + repr(sorted(signature)).encode()),
                                  relocations=len(signature)))
    # Do not double-count aliases or overlapping symbol ranges.
    ordered = sorted(functions, key=lambda f: int(f['address'], 16))
    for prev, curr in zip(ordered, ordered[1:]):
        assert int(prev['address'], 16) + prev['size'] <= int(curr['address'], 16), (
            'Overlapping function symbols', prev['name'], curr['name'])
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    source_hasher = hashlib.sha256()
    for directory in ('src', 'include', 'libs'):
        for path in sorted((root / directory).rglob('*')):
            if path.is_file():
                source_hasher.update(path.relative_to(root).as_posix().encode() + b'\0')
                source_hasher.update(bytes.fromhex(sha256(path.read_bytes())))
    config_hashes = {str(p.relative_to(root)).replace('\\', '/'): sha256(p.read_bytes())
                     for p in [root / 'configure.py', root / f'config/{version}/config.yml',
                               root / f'config/{version}/symbols.txt', root / f'config/{version}/splits.txt']}
    return dict(version=label or version, build_version=version, functions=functions,
                dol_sha1=hashlib.sha1(dol).hexdigest(), dol_sha256=sha256(dol),
                source_revision=revision, source_tree_sha256=source_hasher.hexdigest(),
                configuration_sha256=config_hashes,
                code_bytes=sum(s['size'] for s in sections if s['code']))


def compare(base, target):
    bykey, byname = defaultdict(list), defaultdict(list)
    for f in base['functions']:
        bykey[(f['unit'], f['name'])].append(f)
        byname[f['name']].append(f)
    rows = []
    for f in target['functions']:
        candidates = bykey.get((f['unit'], f['name']), [])
        if len(candidates) != 1:
            candidates = byname.get(f['name'], [])
        b = candidates[0] if len(candidates) == 1 else None
        status = 'not_paired'
        if b:
            status = 'changed'
            if f['size'] == b['size'] and f['exact'] == b['exact']:
                status = 'byte_identical'
            elif f['size'] == b['size'] and f['masked'] and f['masked'] == b['masked']:
                status = 'relocation_masked_candidate'
        rows.append(dict(unit=f['unit'], name=f['name'], address=f['address'],
                         size=f['size'], baseline_address=b['address'] if b else '',
                         baseline_size=b['size'] if b else '', status=status))
    counts, sizes = Counter(r['status'] for r in rows), Counter()
    for r in rows:
        sizes[r['status']] += r['size']
    total = sum(r['size'] for r in rows)
    exact = sizes['byte_identical']
    masked = exact + sizes['relocation_masked_candidate']
    assert total <= target['code_bytes']
    return dict(baseline=base['version'], target=target['version'],
                baseline_dol_sha256=base['dol_sha256'], target_dol_sha256=target['dol_sha256'],
                baseline_source_revision=base['source_revision'],
                target_source_revision=target['source_revision'],
                baseline_source_tree_sha256=base['source_tree_sha256'],
                target_source_tree_sha256=target['source_tree_sha256'],
                baseline_configuration_sha256=base['configuration_sha256'],
                target_configuration_sha256=target['configuration_sha256'],
                functions=len(rows), function_bytes=total,
                executable_code_bytes=target['code_bytes'],
                coverage_percent=100 * total / target['code_bytes'],
                counts=dict(counts), bytes=dict(sizes),
                byte_identical_percent=100 * exact / total,
                including_masked_candidates_percent=100 * masked / total, rows=rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--baseline-version', default='GMSJ01')
    p.add_argument('--target', type=Path, default=Path('.'))
    p.add_argument('--target-version')
    p.add_argument('--output', type=Path, default=Path('assets/regional-comparison.json'))
    a = p.parse_args()
    region = json.loads((a.target / 'region.json').read_text())
    base = load(a.baseline, a.baseline_version)
    target = load(a.target, a.target_version or region['version'], region['inventory_version'])
    result = compare(base, target)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2) + '\n')
    with a.output.with_suffix('.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(result['rows'][0]))
        w.writeheader()
        w.writerows(result['rows'])
    print(f"{result['byte_identical_percent']:.4f}% byte-identical; "
          f"{result['including_masked_candidates_percent']:.4f}% including masked candidates")


if __name__ == '__main__':
    main()
