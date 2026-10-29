"""Export public immutable atomic source inputs from retained files, without network or wallets."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from reputation_platform.atomic_swap_report import ADAPTER, CLOCK_ADR, _campaign_lineage
from reputation_platform.swap_report import SwapEvidence

def export_atomic_swap_sources(root, *, plan, plan_sha256, registration_proof, http_map, output):
    root=Path(root).resolve()
    output=(root/output).resolve()
    if not output.is_relative_to(root/'runtime') or output.exists():
        raise ValueError('Use a new public runtime export directory')
    hashes={}
    missing=[]
    def public(name):
        value=Path(name)
        if value.is_absolute():
            value=value.relative_to(root)
        text=value.as_posix()
        if ('\\' in text or ':' in text or any(x in ('','.','..') for x in text.split('/'))
            or not text.startswith(('runtime/','configs/','docs/adr/','data/declarations/'))
            or any('.private' in x.lower() or x.lower() in ('secrets','auth','platform-config','.env') for x in value.parts)
            or re.search(r'(^|[-_])(signing|signed|send|authorization|password|secret|raw-transaction)([-_.]|$)',value.name,re.I)):
            raise ValueError('Nonpublic atomic evidence path')
        original=root/value
        if any(part.is_symlink() or part.is_junction() for part in (original,*original.parents) if part!=root):
            raise ValueError('Atomic evidence cannot pass through links or junctions')
        resolved=original.resolve()
        if not resolved.is_relative_to(root):
            raise ValueError('Atomic evidence escaped the workspace')
        return text,resolved
    def add(name, expected=None):
        text,path=public(name)
        raw=path.read_bytes()
        digest=hashlib.sha256(raw).hexdigest()
        if expected is not None and expected!=digest:
            raise ValueError('Atomic export source SHA changed: '+text)
        if text in hashes and hashes[text]!=digest:
            raise ValueError('Atomic source changed during export')
        hashes[text]=digest
        return json.loads(raw) if path.suffix=='.json' or text.endswith('.response.bin') and raw[:1] in (b'{',b'[') else None
    def add_ref(value):
        return add(value['path'],value['sha256'])
    def observation(name):
        obs=add(name)
        if obs.get('response_file'):
            if Path(obs['response_file']).name!=obs['response_file']:
                raise ValueError('Observation response is not a sibling file')
            add((Path(name).parent/obs['response_file']).as_posix(),obs['response_sha256'])
        return obs
    plan_name,_=public(plan)
    campaign=add(plan_name,plan_sha256)
    current=campaign
    while current.get('previous_plan'):
        current=add_ref(current['previous_plan'])
    campaign,clocks=_campaign_lineage(SwapEvidence(root,hashes),plan_name)
    if campaign.get('deadline_default_clock_policy')=='request-interval-v1':
        add(CLOCK_ADR)
    for ref in (campaign.get('source_snapshot'),campaign.get('identity_declaration_snapshot')):
        if ref:
            add_ref(ref)
            if ref.get('observation'):observation(ref['observation'])
    binding=campaign.get('protocol_binding')
    if isinstance(binding,dict) and set(binding)=={'path','sha256'}:
        binding=add_ref(binding)
    if binding:
        for ref in binding['source_refs']:add_ref(ref)
    # Public proof and operator configuration are explicit; no credential file is opened.
    proof_name,_=public(registration_proof)
    proof=add(proof_name)
    for ref in proof.get('source_refs',[]):add_ref(ref)
    if proof.get('rpc_configuration'):add_ref(proof['rpc_configuration'])
    for group in campaign['capability']['declaration_groups']:
        for name in group['source_references']:add(name)
    mapping=add(http_map)
    lineage_paths=set()
    cursor_name=plan_name
    cursor=campaign
    while True:
        lineage_paths.add(cursor_name)
        if not cursor.get('previous_plan'):break
        cursor_name=cursor['previous_plan']['path'];cursor=json.loads((root/cursor_name).read_bytes())
    if mapping.get('campaign_plan') not in lineage_paths:
        raise ValueError('HTTP map is not from this frozen campaign lineage')
    named={row['task_key']:row for row in mapping['tasks']}
    if len(named)!=len(mapping['tasks']) or not set(named)<=set(clocks):
        raise ValueError('Unplanned/duplicated HTTP mapping task')
    def rpc_refs(item):
        for phase in ('simulation','execution'):
            if phase not in item:continue
            part=item[phase]
            execution_plan=add(part['plan'])
            for ref in execution_plan.get('sources',[]):add_ref(ref)
            if part.get('intent_path'):add(part['intent_path'])
            for name in part['rpc_observations']:observation(name)
    def latest(candidates):
        result=[]
        for path in candidates:
            value=json.loads(path.read_bytes())
            times=[]
            for phase in ('simulation','execution'):
                for name in value.get(phase,{}).get('rpc_observations',[]):
                    _,obsfile=public(name)
                    if obsfile.is_file():times.append(json.loads(obsfile.read_bytes())['observed_at'])
            if times:result.append((max(times),path.as_posix(),value))
        return max(result,key=lambda x:(x[0],x[1])) if result else None
    tasks=[]
    ledger=[]
    directory=(root/plan_name).parent
    for task in campaign['tasks']:
        key=task['task_key']
        task_dir=directory/'tasks'/key
        names=named.get(key,{}).get('http_observations',[])
        if not names:
            names=[(task_dir/(task['task_id'].lower()+'-'+request['stage']+'.observation.json')).relative_to(root).as_posix()
                   for request in task['requests']
                   if (task_dir/(task['task_id'].lower()+'-'+request['stage']+'.observation.json')).is_file()]
        if len(names)>len(task['requests']):raise ValueError('Extra unplanned HTTP stage')
        item={'task_key':key,'http_observations':names}
        received=False
        for request,name in zip(task['requests'],names):
            obs=observation(name)
            if (obs['url']!=request['url'] or obs['method']!=request['method']
                or json.loads(obs['request_json'])!=request.get('json')):
                raise ValueError('Retained HTTP differs from frozen stage')
            received=received or obs.get('http_status') is not None
            intent=(root/name).with_name((root/name).name.replace('.observation.json','.request-intent.json'))
            if intent.is_file():add(intent)
        phase_dir=task_dir/'atomic-execution'/'run'
        executions=latest(phase_dir.glob('proof-rpc-*/source-item-execution.json')) if phase_dir.is_dir() else None
        simulations=latest([*phase_dir.glob('prepare-rpc-*/source-item-simulation*.json'),
                            *phase_dir.glob('observe-rpc-*/source-item-simulation*.json')]) if phase_dir.is_dir() else None
        selected=executions or simulations
        if selected:
            _,source_path,value=selected
            if value['task_key']!=key or value.get('http_observations')!=names:
                raise ValueError('Retained source item is not bound to this task HTTP')
            add(source_path)
            for phase in ('simulation','execution'):
                if value.get(phase):item[phase]=value[phase]
            rpc_refs(item)
        if names or selected:tasks.append(item)
        ledger.append({'task_id':task['task_id'],'task_key':key,'frozen_at':clocks[key].isoformat(),
                       'http_observed':bool(names),'http_response_received':received,
                       'retained_simulation':bool(item.get('simulation')),'retained_execution':bool(item.get('execution')),
                       'state':'RETAINED_EVIDENCE_REQUIRES_REPLAY' if names or selected else 'NOT_COLLECTED_UNKNOWN'})
    output.mkdir(parents=True,exist_ok=False)
    source={key:campaign[key] for key in ('candidate_key','name','registration_reference','registered_service')}
    source.update(schema_version='atomic-swap-evidence-v1',adapter=ADAPTER,campaign_plan=plan_name,
                  registration_proof=proof_name,tasks=tasks,sources=[{'path':name,'sha256':value} for name,value in sorted(hashes.items())])
    source_path=output/'source.json'
    source_path.write_text(json.dumps(source,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    summary={'schema_version':'atomic-source-export-ledger-v1','created_at':datetime.now(timezone.utc).isoformat(),
             'status':'DRAFT_SOURCE_NOT_A_PUBLISHED_REPORT','plan':{'path':plan_name,'sha256':plan_sha256},
             'planned_task_slots':len(ledger),'tasks_with_http_observations':sum(x['http_observed'] for x in ledger),
             'tasks_with_http_response':sum(x['http_response_received'] for x in ledger),
             'execution_source_items':sum(x['retained_execution'] for x in ledger),
             'missing_evidence_is_unknown':True,'source_sha256':hashlib.sha256(source_path.read_bytes()).hexdigest(),
             'software_provenance':'Report builder creates immutable .py.txt snapshots; no live implementation input.',
             'tasks':ledger,'missing':missing,'scores_computed':False,'network_requests':0,'wallet_operations':0}
    (output/'export-ledger.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return summary
