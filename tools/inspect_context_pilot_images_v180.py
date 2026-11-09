"""Read-only image inventory; no containers, downloads, mounts or daemon changes."""
import json
from pathlib import Path
import docker
from proworksim.software_benchmark_candidates_v054 import reference,write_new

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/software-benchmark-v180/full-task-design-r1'


def main():
    plan=json.loads((OUT/'plan.json').read_bytes())
    client=docker.DockerClient(base_url='unix://'+str(ROOT/'runs/software-panel-v053/docker/docker.sock'),timeout=20)
    rows=[]
    try:
        for task in plan['tasks']:
            value={'instance_id':task['instance_id'],'expected_actor_image':task['actor_image_id']}
            try:
                img=client.images.get(task['actor_image_id'])
                value.update(local_actor_image_present=True,observed_image_id=img.id,
                    exact_id_matches=img.id==task['actor_image_id'])
            except docker.errors.ImageNotFound:value['local_actor_image_present']=False
            p=Path(task['public_test_entry']['baseline_mapping']['path'])
            value['baseline_mapping_present']=p.is_file()
            rows.append(value)
    finally:client.close()
    value={'plan':reference(OUT/'plan.json'),'rows':rows,'new_containers':0,'downloads':0,
        'images_present':sum(r['local_actor_image_present'] for r in rows),
        'fresh_public_or_official_controls_run':False,'shared_host_configuration_changed':False}
    write_new(OUT/'local-image-inventory.json',value)
    print(json.dumps({k:v for k,v in value.items() if k!='rows'}))


if __name__=='__main__':main()
