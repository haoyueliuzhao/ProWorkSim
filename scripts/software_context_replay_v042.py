"""P0-A v042: original 32 rejected prefixes, independently reshaped copies.

Original v040 requests must first reproduce their recorded native hashes. Only
copies get the new run_tests homepage, reading schema and paging instruction.
No page-read action is inserted into any old trajectory; this is CPU shape work.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import time

from proworksim.harness_port import TOOLS as PRIVATE_TOOLS
from proworksim.software_context_replay_v042 import (
    encode_request, load_native_measurement, measure_request, reference,
)
from proworksim.software_context_v034 import observation_messages, project_software_request as original_project
from proworksim.software_organization_v042 import (
    PAGE_BODY_CHARACTERS, READ_TEST_RESULT_TOOL, TOOLS,
    build_test_report, project_observation, project_role_task, test_result_page,
)
from proworksim.storage import atomic_write, digest, json_bytes, read_json
from scripts.software_context_replay_v041 import archived_requests

VERSION = "software-context-replay-v0.42"
SOURCE = Path(__file__).resolve().parents[1]
CONTROL_SOURCES = (
    "scripts/software_context_replay_v042.py", "scripts/software_context_replay_v041.py",
    "src/proworksim/software_context_replay_v042.py", "src/proworksim/software_context_replay_v041.py",
    "src/proworksim/software_context_v042.py", "src/proworksim/software_context_v041.py",
    "src/proworksim/software_context_v034.py", "src/proworksim/software_context_v028.py",
    "src/proworksim/software_organization_v042.py", "src/proworksim/software_organization_v040.py",
    "src/proworksim/candidate_runtime_v015.py", "src/proworksim/training.py", "src/proworksim/harness_sdk.py",
)


def reshape_archived_request(request, witness, test_events):
    """Return a new request shape and exact transformation receipts, never edits."""
    original_digest = digest(json_bytes(request))
    shaped = copy.deepcopy(request)
    changes, reports = [], []
    observations = list(observation_messages(request))
    member = witness["member"]
    if not observations or any(p["observation"].get("actor_id") != member for _, p in observations):
        raise ValueError("Each archived request copy must belong to one known member")
    for index, payload in observation_messages(shaped):
        original_observation = copy.deepcopy(payload["observation"])
        payload["observation"] = project_observation(original_observation)
        payload["role_task"] = project_role_task(payload["role_task"])
        shaped["messages"][index]["content"] = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        changes.append({"kind": "current_paging_interface_and_instruction", "message_index": index,
            "original_observation_sha256": digest(json_bytes(original_observation)),
            "new_observation_sha256": digest(json_bytes(payload["observation"]))})
    old_names = [tool["function"]["name"] for tool in shaped["tools"]]
    if READ_TEST_RESULT_TOOL["name"] in old_names:
        raise ValueError("Expected an original v040 request without the new page-read tool")
    run_definition = next(tool for tool in TOOLS if tool["name"] == "run_tests")
    for tool in shaped["tools"]:
        if tool["function"]["name"] == "run_tests":
            tool["function"] = copy.deepcopy(run_definition)
    private_names = {tool["name"] for tool in PRIVATE_TOOLS}
    insertion = next((i for i, tool in enumerate(shaped["tools"])
        if tool["function"]["name"] in private_names), len(shaped["tools"]))
    shaped["tools"].insert(insertion, {"type": "function", "function": copy.deepcopy(READ_TEST_RESULT_TOOL)})
    changes.append({"kind": "new_public_tool_schema", "new_tool_index": insertion,
        "original_tools_sha256": digest(json_bytes(request["tools"])),
        "new_tools_sha256": digest(json_bytes(shaped["tools"]))})
    latest_observation = observations[-1][1]["observation"]
    for index, message in enumerate(shaped["messages"]):
        if message.get("role") != "tool" or message.get("name") != "run_tests":
            continue
        envelope = json.loads(message["content"])
        if envelope.get("ok") is not True:
            continue
        visible = envelope.get("result")
        if not isinstance(visible, dict) or not visible.get("source_reference"):
            raise ValueError("A successful historical test requires its original visible result")
        event = test_events.get(envelope["command_id"])
        if (not event or event.get("actor_id") != member or event.get("kind") != "test"
                or event.get("action_id") != envelope["action_id"]
                or event.get("source_reference") != visible["source_reference"]
                or event.get("files_sha256") != visible.get("files_sha256")):
            raise ValueError("Historical test envelope must bind its actual world event and source")
        event_identity = {key: latest_observation[key] for key in
                          ("world_id", "instance_id", "branch_id", "project_id")}
        event_identity.update(actor_id=member, test_event_sequence=event["sequence"],
                              operation_id=event["operation_id"])
        report = build_test_report(visible, actor_id=member, event_identity=event_identity)
        page = test_result_page(report)
        envelope["result"] = page
        message["content"] = json.dumps(envelope, ensure_ascii=False, allow_nan=False)
        changes.append({"kind": "test_visible_body_replaced_by_homepage_in_copy_only", "message_index": index,
            "original_tool_call_id": message["tool_call_id"], "report_id": report["report_id"],
            "original_visible_sha256": digest(json_bytes(visible)), "homepage_sha256": digest(json_bytes(page)),
            "body_sha256": report["body_sha256"], "source_reference": copy.deepcopy(visible["source_reference"]),
            "world_wrapper_unchanged": {k: v for k, v in envelope.items() if k != "result"}
                == {k: v for k, v in json.loads(request["messages"][index]["content"]).items() if k != "result"}})
        reports.append(report)
    if digest(json_bytes(request)) != original_digest:
        raise ValueError("Offline shaping mutated the archived request")
    return shaped, {"changes": changes, "report_copies": reports, "original_request_sha256": original_digest,
        "reshaped_request_sha256": digest(json_bytes(shaped)), "new_page_read_actions": 0,
        "scope": "Only copied request shapes. Reports are CPU artifacts, not newly published historical world facts or actual member reading. No original model action, result or record is edited."}


def save_encoding(folder, prefix, request, encoding, projection=None):
    items = {prefix + '-request.json': json_bytes(request),
        prefix + '-native-prompt.txt': encoding['rendered_prompt'].encode(),
        prefix + '-input-ids.json': json_bytes(encoding['input_ids']),
        prefix + '-encoding.json': json_bytes({k:v for k,v in encoding.items()
            if k not in {'rendered_prompt','input_ids','native_messages'}})}
    if projection is not None:
        items[prefix + '-projection.json'] = json_bytes(projection)
    result={}
    for name, data in items.items():
        path=folder/name
        atomic_write(path,data)
        result[name]=reference(path)
    return result


def replay(run_root, output):
    run_root,output=Path(run_root).resolve(),Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    source_before={name:digest((SOURCE/name).read_bytes()) for name in CONTROL_SOURCES}
    measurement=load_native_measurement(run_root/'plan.json')
    plan=read_json(run_root/'plan.json')
    rows=[]
    started=time.time()
    for worker, units in plan['assignments'].items():
        for unit in units:
            episode=run_root/worker/'actual/episodes'/unit['slot_id']
            state_path = episode/'prepared/world/control/state.json'
            state = read_json(state_path)
            test_events = {e['operation_id']:e for e in state['software_events'] if e['kind']=='test'}
            for archived,witness in archived_requests(episode):
                old,old_projection=original_project(archived,render=measurement.render,
                    tokenizer=measurement.tokenizer,context_limit=16384)
                old_encoding=encode_request(old,measurement)
                preparation=witness['recorded_preparation']
                checks={
                    'selected_request':old_projection['selected_request_sha256']==preparation['selected_request_sha256'],
                    'prompt_tokens':old_encoding['prompt_tokens']==preparation['prompt_tokens'],
                    'rendered_prompt':old_encoding['rendered_prompt_sha256']==preparation['rendered_prompt_sha256'],
                    'input_ids':old_encoding['input_ids_sha256']==preparation['input_ids_sha256'],
                    'output_reservation':old_encoding['reserved_output_tokens']==preparation['reserved_output_tokens'],
                    'context_limit':old_encoding['context_limit']==preparation['context_limit'],
                }
                if not all(checks.values()):
                    raise ValueError('Original frozen request did not reproduce before shaping')
                shaped,transform=reshape_archived_request(archived,witness,test_events)
                transform["historical_test_event_source"] = reference(state_path)
                measured=measure_request(shaped,measurement)
                new=measured['new']
                enc=new['encoding']
                protected=new['protected_encoding']
                folder=output/witness['slot_id']/witness['member']
                folder.mkdir(parents=True,exist_ok=False)
                files={}
                for prefix,request,encoding,projection in (
                    ('archived-original',archived,encode_request(archived,measurement),None),
                    ('v040-selected',old,old_encoding,old_projection),
                    ('v042-reshaped',shaped,measured['original']['encoding'],None),
                    ('v042-selected',new['selected'],enc,new['projection']),
                    ('v042-protected',new['protected_selected'],protected,None)):
                    files.update(save_encoding(folder,prefix,request,encoding,projection))
                atomic_write(folder/'transformation.json',json_bytes(transform))
                files['transformation.json']=reference(folder/'transformation.json')
                row={**witness,'old_record_reproduced':True,'old_reproduction_checks':checks,
                    'old_selected_prompt_tokens':old_encoding['prompt_tokens'],
                    'new_selected_prompt_tokens':enc['prompt_tokens'],'new_headroom_tokens':enc['headroom_tokens'],
                    'new_fits':enc['fits'],'protected_prompt_tokens':protected['prompt_tokens'],
                    'protected_headroom_tokens':protected['headroom_tokens'],
                    'protected_headroom_after_margin_tokens':protected['headroom_after_margin_tokens'],
                    'protected_margin_fits':protected['margin_fits'],
                    'passed':enc['fits'] and protected['margin_fits'],
                    'new_selected_request_sha256':new['projection']['selected_request_sha256'],
                    'new_input_ids_sha256':enc['input_ids_sha256'],
                    'new_page_read_actions':0,'converted_test_results':len(transform['report_copies']),
                    'original_format_feedback_count':sum(m.get('role')=='user' and '"public_format_feedback"' in str(m.get('content')) for m in archived['messages']),
                    'artifacts':files}
                atomic_write(folder/'record.json',json_bytes(row))
                rows.append(row)
    after={name:digest((SOURCE/name).read_bytes()) for name in CONTROL_SOURCES}
    value={'version':VERSION,'kind':'P0-A-original-32-copied-page-protocol-shapes','checked_prefixes':len(rows),
        'old_records_reproduced':sum(r['old_record_reproduced'] for r in rows),
        'fit_prefixes':sum(r['new_fits'] for r in rows),
        'protected_margin_fit_prefixes':sum(r['protected_margin_fits'] for r in rows),
        'passed':len(rows)==32 and all(r['passed'] for r in rows) and source_before==after,
        'maximum_new_prompt_tokens':max(r['new_selected_prompt_tokens'] for r in rows),
        'maximum_protected_prompt_tokens':max(r['protected_prompt_tokens'] for r in rows),
        'min_headroom_tokens':min(r['new_headroom_tokens'] for r in rows),
        'min_protected_headroom_after_margin_tokens':min(r['protected_headroom_after_margin_tokens'] for r in rows),
        'context_limit':16384,'reserved_output_tokens':2048,'protected_margin_tokens':1024,
        'page_body_unicode_characters':PAGE_BODY_CHARACTERS,'source_files':source_before,
        'source_unchanged_during_measurement':source_before==after,'native_measurement_identity':measurement.identity,
        'rows':rows,'new_model_calls':0,'new_backward_calls':0,'model_weights_loaded':False,
        'new_historical_page_read_actions':0,'started_at':started,'ended_at':time.time(),
        'scope':'Offline copied-prefix shapes under a new paging Gamma, not model trajectories, extra historical actions or behavioral counterfactuals. Both selected hard capacity and protected 1024-token engineering margin must pass; single 3072-character candidate.'}
    atomic_write(output/'qualification.json',json_bytes(value))
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root',default=str(SOURCE/'runs/software-organization-v040'))
    parser.add_argument('--output',default=str(SOURCE/'runs/v042-controls/context-replay'))
    args=parser.parse_args()
    os.environ['CUDA_VISIBLE_DEVICES']=''
    value=replay(args.run_root,args.output)
    print(json.dumps({k:value[k] for k in ('passed','checked_prefixes','fit_prefixes','protected_margin_fit_prefixes','maximum_new_prompt_tokens','maximum_protected_prompt_tokens')}))


if __name__=='__main__':
    main()
