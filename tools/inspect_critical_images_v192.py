"""Inspect only the24 preselected actor/grader image identities."""
import json
from pathlib import Path
import docker
from proworksim.software_benchmark_candidates_v054 import reference,write_new
from proworksim import software_benchmark_scope_v192 as scope

def main():
    plan=scope.load(reference(scope.PLAN_FILE));out=scope.ARTIFACT_ROOT/'local-images-r1'
    out.mkdir(parents=True,exist_ok=True)
    client=docker.DockerClient(base_url='unix://'+str(scope.ROOT/'runs/software-panel-v053/docker/docker.sock'),timeout=20)
    rows=[]
    try:
        for task,env in plan['environments'].items():
            row={'instance_id':task}
            for kind,key in (('actor','actor_image_id'),('grader','image_id')):
                try:
                    image=client.images.get(env[key]);row[kind]={'present':True,'expected':env[key],'observed':image.id,'exact':image.id==env[key]}
                except docker.errors.ImageNotFound:row[kind]={'present':False,'expected':env[key]}
            rows.append(row)
    finally:client.close()
    value={'plan':reference(scope.PLAN_FILE),'rows':rows,'all_present':all(r[k].get('exact') for r in rows for k in ('actor','grader')),
        'new_containers':0,'downloads':0,'shared_host_changes':0}
    ref=write_new(out/'summary.json',value);print(json.dumps({'summary':ref,'all_present':value['all_present']}))

if __name__=='__main__':main()
