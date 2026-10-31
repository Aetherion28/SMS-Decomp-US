#!/usr/bin/env python3
"""slot_gaps.py UNIT FUNC DBGDIR

Lists our stack slots (from the debugger's variables.txt, in allocation order) next to
the offset the target uses for the same slot, and marks where the target has extra
(or fewer) bytes. UNIT is an objdiff unit (e.g. mario/Enemy/bosswanwan), FUNC a
decomp-diff -d substring, DBGDIR the debugger output directory for that function.
Run from the repository root after building the unit.
"""
import re,subprocess,sys,os
unit,fn,d=sys.argv[1],sys.argv[2],sys.argv[3]
R=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
diff=subprocess.run([sys.executable,'tools/decomp-diff.py','-u',unit,'-d',fn,'--no-collapse'],cwd=R,capture_output=True,text=True).stdout
pairs={}
for l in diff.splitlines():
    parts=l[9:].split('|')
    if len(parts)<2: continue
    def offs(s):
        s=s.replace('{','').replace('}','')
        r=re.findall(r'(0x[0-9a-f]+|\b\d+\b)\(r1\)',s)+re.findall(r'r1, (0x[0-9a-f]+|\d+)\s*$',s.strip())
        return [int(x,0) for x in r]
    a=offs(parts[0]);b=offs(parts[1])
    if len(a)==1 and len(b)==1: pairs.setdefault(b[0],set()).add(a[0])
first={}
for f in ['frontend-00-ast-initial-code.txt','frontend-01-ast-after-optimizations.txt','frontend-02-ast-final-code.txt']:
    try:
        line=None
        for l in open(d+'/'+f):
            m=re.match(r'^(\d+) ST_',l)
            if m: line=int(m.group(1))
            for v in re.findall(r'\[(@?\w+)\]',l): first.setdefault(v,line)
    except FileNotFoundError: pass
rows=[];sect=''
for l in open(d+'/variables.txt'):
    s=l.strip()
    if s.endswith(':'): sect=s[:-1]; continue
    m=re.match(r'\s*r1\+0x([0-9a-f]+)-0x([0-9a-f]+)\s+(?:\S+ ->\s+\S+\s+)?(\S+)',l)
    if not m: continue
    lo,hi,name=int(m.group(1),16),int(m.group(2),16),m.group(3)
    tg=set()
    for o in range(lo,hi):
        if o in pairs: tg|={t-o for t in pairs[o]}
    rows.append((sect,lo,hi,name,first.get(name,'-'),tg))
prev=None
for sect,lo,hi,name,line,tg in rows:
    mark=''
    if tg:
        dl=sorted(tg)[0]
        if prev is not None and dl!=prev: mark=f'   <<< target inserts {prev-dl:+d} bytes above this'
        prev=dl
        mark=f' delta={dl:#x}'+mark
    print(f'{sect[:4]} 0x{lo:03x}-0x{hi:03x} {name:12s} L{line}{mark}')
