from pathlib import Path
import json,runpy,shutil,sys,contextlib,io,hashlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib.figure import Figure
Figure.savefig=lambda *a,**k: None
P=Path('/home/tiare/Desktop/JTPC');T=Path('/tmp/jtpc_chain_review/plots');T.mkdir(parents=True,exist_ok=True)
plots=[('4','6.1','plot_fc.py'),('5','6.1','plot_dfs.py'),('6','6.1','plot_jtpc.py'),('7a','6.2','plot_rtr.py'),('7b','6.2','plot_power.py'),('8','6.2','plot_utility.py'),('9','6.3','plotting.py')]
original_open=Path.open;reads=set()
original_loadtxt=np.loadtxt
def loadtxt(path,*args,**kwargs):
 reads.add(str(Path(path).resolve()))
 return original_loadtxt(path,*args,**kwargs)
np.loadtxt=loadtxt
def traced(self,*args,**kwargs):
 if '/logs/' in str(self.resolve()) and (not args or args[0]=='r'):
  reads.add(str(self.resolve()))
 return original_open(self,*args,**kwargs)
result=[]
for figure,sec,name in plots:
 d=T/sec;d.mkdir(exist_ok=True)
 if not (d/'logs').exists():(d/'logs').symlink_to(P/f'experiment/{sec}/logs',target_is_directory=True)
 shutil.copy2(P/f'experiment/{sec}'/name,d/name)
 reads.clear();output=io.StringIO();Path.open=traced
 with contextlib.redirect_stdout(output),contextlib.redirect_stderr(output):ns=runpy.run_path(str(d/name),run_name='__main__')
 Path.open=original_open
 assert 'Missing:' not in output.getvalue() and 'SKIP' not in output.getvalue() and 'No directory' not in output.getvalue(),output.getvalue()
 files=[]
 for x in sorted(reads):
  f=Path(x);v=original_loadtxt(f);assert v.size and np.isfinite(v).all(),x
  files.append({'path':str(f.relative_to(P)),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'samples':int(v.size)})
 assert files,figure
 result.append({'figure':figure,'plot_script':f'experiment/{sec}/{name}','files':files,'missing':[]})
 print('Figure',figure,'input files',len(files),'all finite/nonempty')
Path('/tmp/jtpc_chain_review/log_to_plot_inputs.json').write_text(json.dumps(result,indent=2))
