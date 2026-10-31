#!/usr/bin/env python3
"""Usage: inline_trace.py UNIT MANGLED_FUNC OUTDIR [DEBUGGER] [RETROWIN32]. Writes OUTDIR/inline_trace.txt."""
import sys,os,re,json,subprocess
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..'))
unit,fn,out=sys.argv[1:4]
obj=[u for u in json.load(open('objdiff.json'))['units'] if u['name']==unit][0]['base_path']
c=subprocess.run(['ninja','-t','commands',obj],capture_output=True,text=True).stdout.strip().split('\n')[-1]
c=re.sub(r'^.*sjiswrap\.exe ','',c); c=re.sub(r' && .*$','',c); c=c.replace('-MMD','')
c=re.sub(r'-o \S+','-o /tmp/inline_trace.o',c)
os.makedirs(out,exist_ok=True)
env=dict(os.environ,INLINE_TRACE='1')
subprocess.run(['python3',sys.argv[4] if len(sys.argv)>4 else '../mwcc-debugger/mwcc_debugger.py','-e',sys.argv[5] if len(sys.argv)>5 else 'retrowin32','-a',c,fn,out],env=env,timeout=1800)
