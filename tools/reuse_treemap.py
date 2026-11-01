#!/usr/bin/env python3
"""Render a saved regional comparison as an independent reuse treemap."""
import argparse
import importlib.util
import json
import re
from collections import defaultdict
from pathlib import Path

def module(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def reuse_page(root,comparison,report,label,baseline_label='JP 1.0',basename='reuse'):
    byunit=defaultdict(list)
    for row in comparison['rows']: byunit[row['unit']].append(row)
    lookup={u['name']:u for u in report['units']}
    units=[];synthetic=[]
    for name,rows in byunit.items():
        key='mario/'+str(Path(name).with_suffix('')).replace('\\','/')
        u=lookup[key];md=u.get('metadata',{});size=sum(r['size'] for r in rows)
        exact=sum(r['size'] for r in rows if r['status']=='byte_identical')
        incl=sum(r['size'] for r in rows if r['status'] in ['byte_identical','relocation_masked_candidate'])
        dem={f['name']:f.get('metadata',{}).get('demangled_name',f['name']) for f in u.get('functions',[])}
        fn=[[dem.get(r['name'],r['name']),r['size'],100 if r['status']=='byte_identical' else 99 if r['status']=='relocation_masked_candidate' else -1 if r['status']=='not_paired' else 0,r['address']] for r in rows]
        units.append(dict(n=key.removeprefix('mario/'),p=md.get('source_path',name),cat=(md.get('progress_categories') or ['other'])[0],c=size,m=exact,f=100*incl/size,fn=fn))
        synthetic.append(dict(name=key,metadata=md,measures=dict(total_code=size,matched_code=exact,fuzzy_match_percent=100*incl/size,matched_code_percent=100*exact/size)))
    total=dict(matched=comparison['byte_identical_percent'],fuzzy=comparison['including_masked_candidates_percent'],fns=comparison['functions'],mfn=comparison['counts'].get('byte_identical',0),units=len(units),done=sum(u['c']==u['m'] for u in units))
    data=dict(repo='https://github.com/'+json.loads((root/'region.json').read_text())['repository'],built='2026-10-31',catNames={c['id']:c['name'] for c in report['categories']},total=total,units=units)
    html=(root/'tools/progress_page.html').read_text(encoding='utf-8')
    html=re.sub(r'Sunshine [^<\n]* Decomp Map',f'Sunshine {label} Code Reuse vs {baseline_label}',html)
    html=html.replace('<div class="tools">','<nav style="margin:12px 0"><a href="reuse.html">Compare with JP 1.0</a> · <a href="progress.html">Decompilation progress</a></nav>\n<div class="tools">',1)
    html=html.replace('All functions match','All function bytes identical').replace('Partly matched (brighter is closer)','Includes relocation-masked candidates').replace('Not started','Changed / not paired')
    html=html.replace('"Complete", "--match"','"All bytes identical", "--match"').replace('"In progress", "--part"','"Mixed comparison results", "--part"')
    html=html.replace('code matched','byte-identical code').replace('functions match','functions byte-identical').replace('files complete','files byte-identical')
    html=html.replace(' fuzzy',' incl. masked').replace('"fuzzy"','"incl. masked candidates"').replace(' matched ·',' identical ·')
    html=html.replace('${f[2] < 0 ? "–" : pct(f[2])}', '${f[2] === 100 ? "Byte-identical" : f[2] === 99 ? "Relocation-masked candidate" : f[2] < 0 ? "Not paired" : "Changed"}')
    html=html.replace('<th class="num">Match</th>','<th class="num">Comparison</th>')
    note=f'Byte-weighted named-function comparison against {baseline_label}. Green = exact linked bytes. Blue = candidate with identical bytes outside relocation fields and identical relocation positions/types. Relocation targets and referenced data may differ; blue is not proven equivalent. Changed and unpaired functions remain distinct in the list. Coverage: '+f"{comparison['coverage_percent']:.4f}% of executable code bytes."
    html=html.replace('Click a box to see its functions. Hover for name and percentage. Use the search box to jump to a file.',note)
    blob=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
    html=html.replace('/*DATA*/null',blob,1)
    (root/f'assets/{basename}.html').write_text(html,encoding='utf-8')
    graph=module(root/'tools/progress_treemap.py','reuse_'+root.name)
    svg=graph.draw(synthetic,{})
    svg=svg.replace('% fuzzy','% incl. relocation-masked candidates').replace('% matched','% byte-identical')
    (root/f'assets/{basename}.svg').write_text(svg+'\n')

if __name__ == '__main__':
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comparison',type=Path,default=Path('assets/regional-comparison.json'))
    parser.add_argument('--baseline-label',default='JP 1.0')
    parser.add_argument('--basename',default='reuse')
    args=parser.parse_args()
    region=json.loads((root/'region.json').read_text())
    report=json.loads((root/f"build/{region['version']}/report.json").read_text())
    comparison=json.loads((root/args.comparison).read_text())
    reuse_page(root,comparison,report,region['label'],args.baseline_label,args.basename)
