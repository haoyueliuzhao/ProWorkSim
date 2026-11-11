"""Extend observed entities with acknowledged whole-file writes and aliases.

The added code material is derived from the actual argument plus its successful
receipt. It is never fabricated as a read_file observation.
"""
import ast,copy,re
from .software_evidence_entities_v198 import EvidenceEntities
from .software_context_graph_v196 import obj,source_ref,safe_path
from .software_context_compression_v175 import digest

class EvidenceBindings(EvidenceEntities):
    def __init__(self,snapshot,**kwargs):
        self.write_materials=[];self.aliases=[];super().__init__(snapshot,**kwargs)
        sources=snapshot['sources'];actions={c['id']:(sid,i,c) for sid,s in sources.items() for i,c in enumerate(s['message'].get('tool_calls',[]))}
        for ack_id,s in sources.items():
            message=s['message'];body=obj(message.get('content'));call=actions.get(message.get('tool_call_id'))
            if not call or body.get('ok') is not True:continue
            action_id,i,c=call;tool=c['function']['name'];args=obj(c['function'].get('arguments'));result=body.get('result',{})
            if tool not in {'write_file','create_file'} or not isinstance(args.get('text'),str) or not safe_path(args.get('path')):continue
            reference=source_ref(result)
            if not reference or args['path'] not in result.get('paths',result.get('changed_paths',[])):continue
            path,text=args['path'],args['text'];material={'path':path,'reference':reference,'action_source':action_id,'ack_source':ack_id,
                'call_index':i,'text_sha256':digest(text),'source_type':'acknowledged_complete_write','parsed':False}
            self.write_materials.append(material)
            previous=self.full_files.get((path,digest(reference)))
            if previous and previous['text']!=text:
                material['failure']='conflicting_complete_read_and_write_sources';continue
            try:tree=ast.parse(text)
            except (SyntaxError,ValueError):material['failure']='visible_written_text_not_parseable';continue
            material['parsed']=True;file=self.file(path,reference);src=[action_id,ack_id]
            self.entities[file]['attrs'].update(definition_seen=True,content_sha256=digest(text),source_ids=src,source_type='acknowledged_complete_write')
            self.full_files[(path,digest(reference))]={'file':file,'text':text,'tree':tree,'sources':src,'reference':reference,
                'argument_source':action_id,'argument_call_index':i,'ack_source':ack_id}
            lines=text.splitlines(keepends=True);offset=[0]
            for line in lines:offset.append(offset[-1]+len(line))
            def visit(nodes,parents=()):
                for node in nodes:
                    if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):continue
                    qual='.'.join((*parents,node.name));signature=ast.dump(node.args,include_attributes=False) if hasattr(node,'args') else ','.join(ast.unparse(x) for x in node.bases)
                    symbol=self.entity('Symbol',{'repo':self.repo,'revision':self.revision(reference),'path':path,'qualified_name':qual,'signature':signature},
                        source_ids=src,lines=[node.lineno,node.end_lineno],syntax_kind=type(node).__name__,source_type='acknowledged_complete_write')
                    origins=[{'source_id':action_id,'channel':'arguments','call_index':i,'pointer':'/text','span':[offset[node.lineno-1],offset[node.end_lineno]]},
                        {'source_id':ack_id,'channel':'body','pointer':'/result/source_reference'}]
                    self.edge(file,symbol,'declares',src,proof='complete_argument_plus_successful_write_receipt',reference=reference,spans=origins)
                    if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name.startswith('test_'):
                        td=self.entity('TestDefinition',{'repo':self.repo,'revision':self.revision(reference),'node_id':path+'::'+qual.replace('.', '::')},
                            body_seen=True,collection_verified=False,definition_entity=symbol,source_ids=src,
                            identity_evidence='visible_static_test_function_not_runtime_collection')
                        self.edge(symbol,td,'declares',src,proof='complete_test_definition_source',reference=reference,spans=origins)
                    visit(node.body,(*parents,node.name))
            visit(tree.body)
        # An alias declaration is a literal Reference, not proof of dispatch.
        for (path,version),f in list(self.full_files.items()):
            for node in ast.walk(f['tree']):
                if not isinstance(node,(ast.Import,ast.ImportFrom)):continue
                for alias in node.names:
                    declared=getattr(node,'module',None);level=getattr(node,'level',0)
                    binding=alias.asname or (alias.name if isinstance(node,ast.ImportFrom) else alias.name.split('.')[0])
                    eid=self.entity('Reference',{'repo':self.repo,'revision':self.revision(f['reference']),'path':path,
                        'import_alias':binding,'module':declared,'imported_name':alias.name,'level':level,'line':node.lineno},
                        reason='import_alias_runtime_target_unresolved',source_ids=f['sources'],qualified_name=None)
                    proof={'path':path,'reference':f['reference'],'alias':binding,'module':declared,'name':alias.name,'level':level,
                        'entity_id':eid,'source_ids':f['sources'],'statement_lines':[node.lineno,node.end_lineno]}
                    self.aliases.append(proof)
                    self.edge(f['file'],eid,'references',f['sources'],proof='literal_import_alias_not_runtime_binding',reference=f['reference'],
                        spans=[{'source_id':sid,'observed_complete_statement_lines':[node.lineno,node.end_lineno]} for sid in f['sources']])
                    if isinstance(node,ast.ImportFrom):
                        package=path.split('/')[:-1];prefix=package[:len(package)-level+1] if level else []
                        module='/'.join(prefix+(declared or '').split('.')).strip('/')
                        for (target_path,target_version),target in self.full_files.items():
                            if target_version==version and target_path in {module+'.py',module+'/__init__.py'}:
                                definitions=[e['id'] for e in self.entities.values() if e['kind']=='Symbol' and e['identity'].get('path')==target_path and e['identity'].get('qualified_name')==alias.name and e['identity']['revision']['workspace_reference']==f['reference']]
                                for target_id in definitions:
                                    self.edge(eid,target_id,'resolves_to',f['sources']+target['sources'],status='Inferred',
                                        proof='observed_files_static_alias_candidate_not_runtime',reference=f['reference'])
        for event_id,event in snapshot['events'].items():
            if event['kind']!='artifact':continue
            values={}
            for sid in event['sources']:
                r=obj(sources[sid]['message'].get('content')).get('result',{})
                for key in ['patch_id','delivery_id','source_sha256','files_sha256']:
                    if r.get(key):values[key]=r[key]
            for eid in self.event_bindings.get(event_id,[]):
                if self.entities[eid]['kind']=='Artifact':self.entities[eid]['attrs']['observed_aliases']=values

    def as_json(self):
        result=super().as_json();result.update(version='v199-source-bound-entities-r1',write_materials=copy.deepcopy(self.write_materials),
            import_aliases=copy.deepcopy(self.aliases),no_synthetic_read_observations=True)
        return result
