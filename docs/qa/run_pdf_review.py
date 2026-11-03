from pathlib import Path
import json,subprocess,sys
import fitz
from PIL import Image,ImageDraw
P=Path('/home/tiare/Desktop/JTPC');Q=P/'docs/qa';skills=Path('/home/tiare/.codex/skills/nature-figure/scripts')
files=[]
for sec in ['6.1','6.2','6.3']: files+=sorted((P/f'experiment/{sec}/Figures/replotted').glob('*.pdf'))
files.append(P/'experiment/6.2/Figures/fig7b_power_RTR090.pdf')
summary=[];thumbnails=[]
for pdf in files:
 result=subprocess.run([sys.executable,str(skills/'audit_figure_collisions.py'),str(pdf),'--json-out',str(Q/(pdf.stem+'.collision.json'))],capture_output=True,text=True)
 (Q/(pdf.stem+'.collision.txt')).write_text(result.stdout+result.stderr)
 text=subprocess.run([sys.executable,str(skills/'audit_pdf_text.py'),str(pdf),'--min-pt','5','--json'],capture_output=True,text=True)
 (Q/(pdf.stem+'.text.json')).write_text(text.stdout)
 r=json.loads((Q/(pdf.stem+'.collision.json')).read_text())
 doc=fitz.open(pdf);page=doc[0];ordinary=page.get_drawings();clip_by_seq={};clips={}
 for d in page.get_drawings(extended=True):
  level=d['level'];clips={k:v for k,v in clips.items() if k<level}
  if d['type']=='clip':clips[level]=fitz.Rect(d['scissor'])
  elif 'seqno' in d:
   clip=page.rect
   for rect in clips.values():clip=clip & rect
   clip_by_seq[d['seqno']]=clip
 reviewed=[]
 for finding in r['findings']:
  if finding['kind'] not in ['text-stroke','text-fill-edge']:continue
  visible=[];excluded=[]
  for index in finding.get('object_indexes',[]):
   drawing_index=index if finding['kind']=='text-stroke' or index < 1000 else index//1000
   if drawing_index>=len(ordinary):visible.append(index);continue
   d=ordinary[drawing_index];clip=clip_by_seq.get(d.get('seqno'),page.rect)
   if (fitz.Rect(finding['text_bbox']) & clip).is_empty:excluded.append({'index':index,'clip':list(clip)})
   else:visible.append(index)
  reviewed.append({'severity':finding['severity'],'text':finding['text'],'kind':finding['kind'],'all_objects_outside_visible_clip':not visible,'excluded':excluded,'remaining_indexes':visible})
 (Q/(pdf.stem+'.clip_review.json')).write_text(json.dumps(reviewed,indent=2))
 summary.append({'file':str(pdf.relative_to(P)),'raw_collision_exit':result.returncode,'raw_collision_summary':r['summary'],'font_exit':text.returncode,'unresolved_fail_findings':[x for x in reviewed if x['severity']=='FAIL' and not x['all_objects_outside_visible_clip']]})
 pix=page.get_pixmap(matrix=fitz.Matrix(1.5,1.5));img=Image.frombytes('RGB',[pix.width,pix.height],pix.samples);img.thumbnail((700,500));tile=Image.new('RGB',(720,535),'white');tile.paste(img,((720-img.width)//2,30));ImageDraw.Draw(tile).text((10,8),pdf.stem,fill='black');thumbnails.append(tile)
 (Q/(pdf.stem+'.preview.png')).write_bytes(page.get_pixmap(matrix=fitz.Matrix(1.5,1.5)).tobytes('png'))
contact=Image.new('RGB',(1440,535*((len(thumbnails)+1)//2)),(230,230,230))
for i,img in enumerate(thumbnails):contact.paste(img,((i%2)*720,(i//2)*535))
contact.save(Q/'contact.png')
(Q/'pdf_review_summary.json').write_text(json.dumps(summary,indent=2))
for x in summary:print(x['file'],x['raw_collision_summary'],'font',x['font_exit'],'unresolved_fail',len(x['unresolved_fail_findings']))
