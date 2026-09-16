#!/usr/bin/env python3
"""Check pack structure, references, examples and dependency/traceability invariants.

Uses only the Python standard library. This intentionally does not replace a complete
OpenAPI/JSON Schema meta-validator or application tests; T00 must add those validators.
The example checker implements only the schema keywords used by this pack.
"""
from pathlib import Path
import argparse
import datetime
import json
import re
import uuid
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]
def read(name):return json.loads((ROOT/name).read_text())
def require(value,msg):
    if not value:raise AssertionError(msg)
def pointer(doc,ref):
    require(ref.startswith('#/'),f'External or unsupported reference: {ref}')
    node=doc
    for part in ref[2:].split('/'):
        node=node[part.replace('~1','/').replace('~0','~')]
    return node
def walk(node):
    yield node
    if isinstance(node,dict):
        for v in node.values():yield from walk(v)
    elif isinstance(node,list):
        for v in node:yield from walk(v)
def matches_type(value,typ):
    return {'object':isinstance(value,dict),'array':isinstance(value,list),
            'string':isinstance(value,str),'integer':isinstance(value,int) and not isinstance(value,bool),
            'number':isinstance(value,(int,float)) and not isinstance(value,bool),
            'boolean':isinstance(value,bool),'null':value is None}[typ]
def validate(value,schema,doc,path='$'):
    if '$ref' in schema:return validate(value,pointer(doc,schema['$ref']),doc,path)
    if 'anyOf' in schema:
        for branch in schema['anyOf']:
            try:validate(value,branch,doc,path);return
            except (AssertionError,ValueError,TypeError):pass
        raise AssertionError(f'{path}: no matching anyOf branch')
    typ=schema.get('type')
    if typ:
        require(any(matches_type(value,t) for t in ([typ] if isinstance(typ,str) else typ)),f'{path}: wrong type')
    if 'enum' in schema:require(value in schema['enum'],f'{path}: invalid enum')
    if isinstance(value,dict):
        for key in schema.get('required',[]):require(key in value,f'{path}: missing {key}')
        require(len(value)>=schema.get('minProperties',0),f'{path}: not enough properties')
        props=schema.get('properties',{})
        for key,val in value.items():
            if key in props:validate(val,props[key],doc,f'{path}.{key}')
            elif schema.get('additionalProperties') is False:raise AssertionError(f'{path}: unknown {key}')
            elif isinstance(schema.get('additionalProperties'),dict):validate(val,schema['additionalProperties'],doc,f'{path}.{key}')
    if isinstance(value,list):
        require(schema.get('minItems',0)<=len(value)<=schema.get('maxItems',10**9),f'{path}: array length')
        for i,val in enumerate(value):validate(val,schema.get('items',{}),doc,f'{path}[{i}]')
    if isinstance(value,str):
        require(schema.get('minLength',0)<=len(value)<=schema.get('maxLength',10**9),f'{path}: string length')
        if 'pattern' in schema:require(re.search(schema['pattern'],value),f'{path}: pattern mismatch')
        fmt=schema.get('format')
        if fmt=='uuid':uuid.UUID(value)
        elif fmt=='date':datetime.date.fromisoformat(value)
        elif fmt=='date-time':
            dt=datetime.datetime.fromisoformat(value.replace('Z','+00:00'))
            require(dt.tzinfo is not None,f'{path}: timestamp lacks timezone')
        elif fmt=='uri':require(bool(urlparse(value).scheme),f'{path}: invalid URI')
    if isinstance(value,(int,float)) and not isinstance(value,bool):
        if 'minimum' in schema:require(value>=schema['minimum'],f'{path}: below minimum')
        if 'maximum' in schema:require(value<=schema['maximum'],f'{path}: above maximum')

def main():
    api=read('contracts/openapi.json');ai=read('contracts/ai-output.schema.json')
    ts=read('plan/tasks.json')['tasks'];cs=read('plan/acceptance.json')['cases']
    tasks={t['id']:t for t in ts};cases={c['id']:c for c in cs}
    require(len(tasks)==len(ts),'Duplicate task ID');require(len(cases)==len(cs),'Duplicate acceptance ID')
    reqs={f'R{i:02d}' for i in range(1,16)}
    refs=0
    for doc in [api,ai]:
        for node in walk(doc):
            if isinstance(node,dict) and '$ref' in node:pointer(doc,node['$ref']);refs+=1
            if isinstance(node,dict) and 'required' in node and 'properties' in node:
                require(set(node['required'])<=set(node['properties']),'Required property not declared')
            if isinstance(node,dict) and 'pattern' in node:re.compile(node['pattern'])
    require(api['openapi']=='3.1.1','Unexpected OpenAPI version')
    operations={}
    for path,methods in api['paths'].items():
        for method,op in methods.items():
            require(op['operationId'] not in operations,'Duplicate operation ID')
            operations[op['operationId']]=op
            params=op.get('parameters',[])
            declared={p['name'] for p in params if p['in']=='path' and p.get('required')}
            require(declared==set(re.findall(r'{(\w+)}',path)),f'Bad path parameters for {path}')
            if method=='post':require(any(p['name']=='Idempotency-Key' and p['required'] for p in params),f'Missing idempotency: {path}')
            if path not in ['/health','/me']:
                require(any(p['name']=='X-Workspace-Id' and p['required'] for p in params),f'Missing scope: {path}')
            require(op['x-required-role'] in ['PUBLIC','REP','ADMIN'],'Invalid role')
    assigned_ops=set();covered_cases=set();covered_reqs=set()
    for task in ts:
        require(set(task['requirements'])<=reqs,f"Unknown task requirement: {task['id']}")
        require(set(task['acceptance_ids'])<=set(cases),f"Unknown case: {task['id']}")
        require(set(task['operation_ids'])<=set(operations),f"Unknown operation: {task['id']}")
        for name in task['read_first']:require((ROOT/name).is_file(),f'Missing task input {name}')
        for dep in task['depends_on']:require(dep in tasks,f'Unknown dependency {dep}')
        assigned_ops.update(task['operation_ids']);covered_cases.update(task['acceptance_ids']);covered_reqs.update(task['requirements'])
    require(assigned_ops==set(operations),f'Unassigned operations: {set(operations)-assigned_ops}')
    require(covered_cases==set(cases),'Unassigned acceptance cases')
    require(covered_reqs==reqs,'Unassigned requirements')
    for case in cs:
        require(set(case['requirements'])<=reqs,f"Unknown case requirement: {case['id']}")
        require(set(case['operation_ids'])<=set(operations),f"Unknown case operation: {case['id']}")
        require(case['given'] and case['when'] and case['then'],f"Incomplete acceptance: {case['id']}")
    require(set().union(*(set(c['requirements']) for c in cs))==reqs,'Requirement lacks acceptance')
    def ancestors(tid,seen=None):
        seen=set() if seen is None else set(seen)
        require(tid not in seen,'Dependency cycle')
        seen.add(tid);out=set()
        for dep in tasks[tid]['depends_on']:out.add(dep);out.update(ancestors(dep,seen))
        return out
    ancestors_map={tid:ancestors(tid) for tid in tasks}
    require('T13' not in ancestors_map['T14'],'Optional seed blocks core release')
    require(tasks['T13']['optional'],'Demo task must remain optional')
    for i,a in enumerate(ts):
        for b in ts[i+1:]:
            if a['id'] in ancestors_map[b['id']] or b['id'] in ancestors_map[a['id']]:continue
            for ap in a['owned_paths']:
                for bp in b['owned_paths']:
                    overlap=ap==bp or (ap.endswith('/') and bp.startswith(ap)) or (bp.endswith('/') and ap.startswith(bp))
                    require(not overlap,f"Parallel ownership collision: {a['id']} / {b['id']} at {ap} / {bp}")
    remaining=set(tasks);done=set();waves=[]
    while remaining:
        ready=sorted(t for t in remaining if set(tasks[t]['depends_on'])<=done)
        require(ready,'Dependency graph cannot advance');waves.append(ready);done.update(ready);remaining-=set(ready)
    example_count=0
    for section,doc,defs in [('api',api,api['components']['schemas']),('ai',ai,ai['$defs'])]:
        for ex in read('contracts/examples.json')[section]:
            ok=True
            try:validate(ex['value'],defs[ex['schema']],doc)
            except (AssertionError,ValueError,TypeError):ok=False
            require(ok==ex['valid'],f"Unexpected schema example result: {ex['name']}");example_count+=1
    machines=read('contracts/states.json')['machines']
    for name,m in machines.items():
        states=set(m['transitions'])
        require(m['initial'] in states,f'Missing initial state: {name}')
        require(set(m['terminal'])<=states,f'Missing terminal state: {name}')
        for src,dests in m['transitions'].items():require(set(dests)<=states,f'Unknown state transition: {name}')
        for end in m['terminal']:require(not m['transitions'][end],f'Terminal state has transition: {name}')
    for name,field in [('Job','status'),('Media','status'),('Import','status'),('Investigation','state'),('Visit','status'),('Action','status')]:
        require(set(api['components']['schemas'][name]['properties'][field]['enum'])==set(machines[name]['transitions']),f'State/schema drift: {name}')
    imp=read('contracts/imports.json')
    for kind in ['SALES','INVENTORY']:
        c=imp[kind];require(set(c['columns'])==set(c['fields']),f'Import fields drift: {kind}')
        require(set(c['logical_key'])<=set(c['columns']),f'Invalid import key: {kind}')
    tools=read('contracts/tools.json')
    tool_refs=[tools['result_envelope_schema_ref']]
    for tool in tools['tools']:
        tool_refs += [tool['input_schema_ref'],tool['data_schema_ref']]
        require(tool['business_mutations'] is False,'Agent tool can mutate business state')
    for tool_ref in tool_refs:
        name,fragment=tool_ref.split('#',1)
        pointer(read('contracts/'+name),'#'+fragment)
    links=0
    for file in ROOT.rglob('*.md'):
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',file.read_text()):
            if target.startswith(('https://','http://','#')):continue
            target=target.split('#',1)[0]
            require((file.parent/target).exists(),f'Broken local link: {file.relative_to(ROOT)} → {target}');links+=1
    result={'status':'passed','kind':'specification_integrity_only','application_tests':'not_run',
            'full_openapi_meta_validation':'required_in_T00_not_run_by_this_stdlib_check',
            'requirements':len(reqs),'tasks':len(tasks),'acceptance_cases':len(cases),
            'api_operations':len(operations),'api_schemas':len(api['components']['schemas']),
            'ai_definitions':len(ai['$defs']),'schema_refs_checked':refs,'schema_examples_checked':example_count,
            'typed_tool_contracts':len(tools['tools']),'tool_schema_refs_checked':len(tool_refs),
            'local_links_checked':links,'waves':waves}
    parser=argparse.ArgumentParser();parser.add_argument('--report');args=parser.parse_args()
    if args.report:
        p=Path(args.report);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
