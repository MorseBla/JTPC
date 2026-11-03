from pathlib import Path
import shutil,os,subprocess,json
root=Path('/tmp/jtpc_chain_review/mock');project=root/'JTPC';bin_dir=root/'commands';bin_dir.mkdir(parents=True,exist_ok=True)
source=Path('/home/tiare/Desktop/JTPC')
for section in ['6.1','6.2','6.3']:
 shutil.copytree(source/f'experiment/{section}/collection',project/f'experiment/{section}/collection',dirs_exist_ok=True)
for d in ['Scheduler/bin','application/bin','scripts']:(project/d).mkdir(parents=True,exist_ok=True)
shutil.copy2('/tmp/jtpc_chain_review/build/Scheduler/bin/scheduler',project/'Scheduler/bin/scheduler')
log=root/'trace.jsonl'
stub='''#!/usr/bin/python3
import os,sys,json
record={'program':os.path.basename(sys.argv[0]),'args':sys.argv[1:],'cwd':os.getcwd(),'skip_initial_lock':os.environ.get('JPAP_SKIP_INITIAL_GPU_LOCK'),'arrival_delay':os.environ.get('TASK_ARRIVAL_DELAY')}
fd=os.open(os.environ['CHAIN_TRACE'],os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600);os.write(fd,(json.dumps(record)+'\\n').encode());os.close(fd)
'''
for target in [project/'Scheduler/bin/server']+[project/'application/bin'/n for n in ['hist','stereo','mm','mm_test','particle']]+[bin_dir/n for n in ['make','sudo','pkill','ipcs','ipcrm','sleep']]:
 target.write_text(stub);target.chmod(0o755)
# sudo only delegates scheduler invocations; device, process and tegrastats commands stay inert.
with (bin_dir/'sudo').open('a') as f:f.write('''
args=sys.argv[1:]
while args and args[0].startswith('-'):args.pop(0)
if any(a.endswith('/bin/scheduler') for a in args):
 os.execvp(args[0],args)
''')
results=[]
for section,filename,sp in [('6.1','interrupt_test_FC.sh',None),('6.1','interrupt_test_DFS.sh',None),('6.1','interrupt_test_LQR.sh',None),('6.2','FC_GPU_main_temp.sh',None),('6.2','DFS_main_temp.sh',None),('6.2','LQR_main_temp.sh',None),('6.3','task_arrival_4task_test.sh',None),('6.2','FC_GPU_main_temp.sh','0.90 0.90 0.90'),('6.2','DFS_main_temp.sh','0.90 0.90 0.90')]:
 if log.exists():log.unlink()
 env=os.environ.copy();env.pop('SP',None);env['PATH']=str(bin_dir)+':'+env['PATH'];env['CHAIN_TRACE']=str(log)
 if sp:env['SP']=sp
 path=project/f'experiment/{section}/collection'/filename
 r=subprocess.run(['bash',str(path)],cwd='/tmp',env=env,text=True,capture_output=True,timeout=30)
 trace=[json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
 results.append({'section':section,'script':filename,'supplied_SP':sp,'exit_code':r.returncode,'stderr':r.stderr,'trace':trace})
 print(section,filename,'SP',sp,'exit',r.returncode,'workers',len([x for x in trace if x['program'] in ['hist','stereo','mm','mm_test','particle']]),r.stderr[:150],flush=True)
(root.parent/'mock_chain_results.json').write_text(json.dumps(results,indent=2))
