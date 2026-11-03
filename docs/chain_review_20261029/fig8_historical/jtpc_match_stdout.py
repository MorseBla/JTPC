from pathlib import Path
import json,re,hashlib
base=Path('/home/tiare/Desktop/SM_memory/build/JTPC_DAC_audit_20261029/remote_snapshot/JPAP 1')
root=Path('/home/tiare/Desktop/JTPC')
parsed=[]
for f in (base/'motivation/run_stdout').rglob('*.log'):
 s=f.read_text(errors='replace')
 commands=[l for l in s.splitlines() if l.startswith('Executing:') and 'logs/main_temp/' in l]
 if not commands: continue
 parts={}
 for task in [1,2,3]:
  ls=re.findall(r'^T'+str(task)+r'\s+[^\n]+',s,re.M)
  if ls:
   parts[task]={'period':[float(l.split()[5]) for l in ls], 'rtr':[float(l.split()[3]) for l in ls]}
  else:
   per=re.findall(r'\x1b\['+str(13+task)+r';1H(T'+str(task)+r'[^\x1b]+)',s)
   rtr=re.findall(r'\x1b\['+str(8+task)+r';1H(T'+str(task)+r'[^\x1b]+)',s)
   parts[task]={'period':[float(l.split()[2]) for l in per], 'rtr':[float(l.split()[4]) for l in rtr]}
 parsed.append((f,s,commands,parts))
rows=[]
for method,prefix in [('FC','FC_GPU'),('DFS','DFS'),('JTPC','LQR')]:
 for power in [11000,11500,12000,12500,13000]:
  target=f'logs/main_temp/{method}/hist_stereo_mm/setpoint_{power}_0.90_0.90_0.90'
  vals={(t,m):[float(v) for v in (root/f'experiment/6.2/{target}/{prefix}_t{t}_{m}.txt').read_text().split()] for t in [1,2,3] for m in ['period','rtr']}
  matches=[];partial=[]
  for f,s,commands,parts in parsed:
   if not any(target in c for c in commands):continue
   diffs=[];lengths=True
   for (t,m),data in vals.items():
    got=parts[t][m];lengths &= len(got)==len(data)
    diffs.append(max((abs(a-b) for a,b in zip(data,got)),default=999))
   item=dict(file=str(f),stdout_n=len(parts[1]['period']),log_n=len(vals[1,'period']),max_difference=max(diffs),skip_initial_lock='[GPU] Skip initial GPU lock' in s)
   if lengths and max(diffs)<=0.0011:matches.append(item)
   else:partial.append(item)
  rows.append(dict(method=method,power=power,matches=matches,other_candidates=sorted(partial,key=lambda x:x['max_difference'])))
Path('/tmp/jtpc_fig8_stdout_search.json').write_text(json.dumps(rows,indent=2)+'\n')
for r in rows:
 print(r['method'],r['power'],'MATCH',[(Path(x['file']).parent.name,Path(x['file']).name,x['max_difference']) for x in r['matches']])
 if not r['matches']:print(' nearest',r['other_candidates'][:1])
