import sys, json, runpy
from pathlib import Path
sys.path.insert(0, '/home/tiare/.codex/skills/nature-figure/scripts')
from audit_panel_alignment import require_matplotlib_panel_alignment
import matplotlib
matplotlib.use('Agg')
from matplotlib.figure import Figure
P=Path('/home/tiare/Desktop/JTPC');Q=P/'docs/qa';Q.mkdir(exist_ok=True)
original=Figure.savefig
seen=set()
def save(self,filename,*a,**kw):
 p=Path(filename)
 if p.suffix.lower()=='.pdf' and str(p.resolve()) not in seen:
  seen.add(str(p.resolve()))
  result=require_matplotlib_panel_alignment(self,json_out=Q/(p.stem+'.alignment.json'),strict=True)
  print('ALIGNMENT',p,result.get('verdict'))
 return original(self,filename,*a,**kw)
Figure.savefig=save
for row in json.loads((P/'docs/plot_sources.json').read_text()):
 runpy.run_path(str(P/row['script']),run_name='__main__')
