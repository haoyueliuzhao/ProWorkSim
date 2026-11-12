"""Syntax-grounded facts with exact UTF-8 offsets and explicit partial context.

Parsers never execute source text. Private-source assembly, fact identity and
source spans are separate; a complete local statement is not a complete file.
"""
from __future__ import annotations
import ast,copy,hashlib,json,time

def sha(x):
    return hashlib.sha256(x if isinstance(x,bytes) else json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

class SourceConflict(ValueError):pass

def document(text,*,scope,path,version,source_id,complete=True,evidence=None):
    raw=text.encode('utf-8')
    return {'text':text,'scope':list(scope),'path':path,'version':copy.deepcopy(version),'source_id':source_id,
        'source_hash':sha(raw),'complete':bool(complete),'evidence':copy.deepcopy(evidence or []),'offset_basis':'decoded_source_text_UTF8_bytes'}

class SourceAssembler:
    def __init__(self):self.pieces={}
    def add(self,*,scope,path,version,start,end,total,text,source_id,message_sha256):
        if not all(type(x)is int for x in (start,end,total)) or not 0<=start<=end<=total or end-start!=len(text):
            raise SourceConflict('Invalid original character interval')
        key=sha([scope,path,version]);existing=self.pieces.get(key,[])
        for p in existing:
            if p['total']!=total:raise SourceConflict('Conflicting source extent in one version')
            a,z=max(start,p['start']),min(end,p['end'])
            if a<z and text[a-start:z-start]!=p['text'][a-p['start']:z-p['start']]:raise SourceConflict('Conflicting overlap in one private version')
        part={'start':start,'end':end,'total':total,'text':text,'source_id':source_id,'message_sha256':message_sha256}
        self.pieces[key]=existing+[part];merged=''
        for p in sorted(self.pieces[key],key=lambda p:(p['start'],-p['end'])):
            if p['start']>len(merged):break
            if p['end']>len(merged):merged+=p['text'][len(merged)-p['start']:]
        if len(merged)==total:
            evidence=[{k:p[k] for k in ('source_id','message_sha256','start','end')} for p in self.pieces[key]]
            return document(merged,scope=scope,path=path,version=version,source_id='assembly:'+key,complete=True,evidence=evidence)
        return document(text,scope=scope,path=path,version=version,source_id=source_id,complete=False,
            evidence=[{'source_id':source_id,'message_sha256':message_sha256,'fragment_file_character_range':[start,end],'file_character_total':total}])

class SyntaxFacts:
    def __init__(self):
        import tree_sitter,tree_sitter_python
        self.language=tree_sitter.Language(tree_sitter_python.language());self.parser=tree_sitter.Parser(self.language)

    def extract(self,doc,method='A2'):
        started=time.process_time();raw=doc['text'].encode('utf-8')
        if sha(raw)!=doc['source_hash']:raise SourceConflict('Document bytes changed')
        rows=[];links=[];diagnostics=[]
        def emit(kind,a,z,*,parent=None,node_type=None,local_complete=True,roles=None):
            if not 0<=a<=z<=len(raw):raise SourceConflict('Parser offset outside original source')
            try:value=raw[a:z].decode('utf-8')
            except UnicodeDecodeError as e:raise SourceConflict('Parser split a UTF-8 character') from e
            span_id='span:'+sha([doc['scope'],doc['version'],doc['source_id'],doc['source_hash'],a,z])[:24]
            fid='fact:'+sha([doc['scope'],doc['version'],doc['path'],doc['source_hash'],kind,a,z])[:24]
            row={'fact_id':fid,'fact_type':kind,'syntax_node_type':node_type or kind,'source_id':doc['source_id'],'source_hash':doc['source_hash'],
                'version_id':copy.deepcopy(doc['version']),'scope':doc['scope'],'path':doc['path'],'start_byte':a,'end_byte':z,
                'value':value,'parent_fact_id':parent,'span_id':span_id,'completeness':'complete' if doc['complete'] and local_complete else 'partial',
                'node_syntax_complete':local_complete,'file_source_complete':doc['complete'],'qualified_scope_known':doc['complete'] and local_complete,
                'verification':'observed_syntax_only','roles':roles or []}
            rows.append(row);return fid
        if method=='A0':
            from .software_fact_context_v199 import code_spans
            for k,a,z in code_spans(doc['text']):emit(k,len(doc['text'][:a].encode()),len(doc['text'][:z].encode()),local_complete=False,node_type='legacy_lexical_excerpt')
        elif method in {'A1','A2'}:
            import libcst as cst
            from libcst.metadata import MetadataWrapper,ByteSpanPositionProvider,ParentNodeProvider
            def cst_extract(text,offset,local_source_complete):
                module=cst.parse_module(text);wrapper=MetadataWrapper(module);positions=wrapper.resolve(ByteSpanPositionProvider);parents=wrapper.resolve(ParentNodeProvider)
                selected={}
                small=(cst.BaseSmallStatement,cst.FunctionDef,cst.ClassDef)
                extra=(cst.BooleanOperation,cst.Comparison,cst.UnaryOperation,cst.Call,cst.IfExp,cst.NamedExpr,
                       cst.Lambda,cst.ListComp,cst.SetComp,cst.DictComp,cst.GeneratorExp,cst.Decorator)
                for node,pos in positions.items():
                    roles=[];parent=parents.get(node)
                    if isinstance(parent,(cst.Assign,cst.AnnAssign,cst.AugAssign,cst.NamedExpr)) and getattr(parent,'value',None) is node:roles.append('assigned_value')
                    if isinstance(parent,cst.AssignTarget) or (isinstance(parent,(cst.AnnAssign,cst.AugAssign,cst.NamedExpr)) and getattr(parent,'target',None) is node):roles.append('binding_target')
                    if isinstance(parent,cst.BooleanOperation) and node in (parent.left,parent.right):roles.append('boolean_operand')
                    take=isinstance(node,small) or (method=='A2' and (isinstance(node,extra) or roles))
                    if not take or pos.length==0:continue
                    a,z=offset+pos.start,offset+pos.start+pos.length
                    if z>offset+len(text.encode()):continue
                    fid=emit(type(node).__name__,a,z,node_type=type(node).__name__,local_complete=local_source_complete,roles=roles)
                    selected[node]=fid
                for node,fid in selected.items():
                    p=parents.get(node)
                    while p is not None and p not in selected:p=parents.get(p)
                    if p in selected:
                        parent=selected[p];row=next(r for r in rows if r['fact_id']==fid);row['parent_fact_id']=parent
                        links.append({'from':parent,'to':fid,'relation':'syntax_contains','verification':'Confirmed_syntax_not_causality'})
            try:
                if not doc['complete']:raise ValueError('Partial source; full module completeness is not claimed')
                cst_extract(doc['text'],0,True)
            except (cst.ParserSyntaxError,ValueError) as error:
                rows.clear();links.clear();diagnostics.append({'kind':'partial_or_unparseable_module','detail':str(error)[:180]})
                # Tree-sitter identifies literal local statement boundaries; no
                # wrapper or dedented synthetic file becomes a source of facts.
                tree=self.parser.parse(raw);stack=[tree.root_node];ranges=[]
                while stack:
                    node=stack.pop();stack.extend(reversed(node.named_children))
                    if node.type in {'assignment','augmented_assignment','return_statement','assert_statement','import_statement','import_from_statement'} and not node.has_error and not node.is_missing:
                        ranges.append((node.start_byte,node.end_byte))
                used=[]
                for a,z in sorted(set(ranges),key=lambda p:(p[0],-p[1])):
                    if any(x<=a and z<=y for x,y in used):continue
                    segment=raw[a:z].decode('utf-8')
                    # A completed statement has its exact original bytes. Its
                    # missing enclosing source remains Partial, even if it parses.
                    try:cst_extract(segment+'\n',a,True);used.append((a,z))
                    except (cst.ParserSyntaxError,ValueError):continue
                for r in rows:r.update(completeness='partial',file_source_complete=doc['complete'],qualified_scope_known=False)
        elif method=='A3':
            tree=self.parser.parse(raw);types={'assignment','augmented_assignment','named_expression','call','conditional_expression','boolean_operator','not_operator',
                'comparison_operator','list_comprehension','dictionary_comprehension','set_comprehension','generator_expression','lambda','decorator','function_definition',
                'class_definition','return_statement','assert_statement','import_statement','import_from_statement'}
            stack=[(tree.root_node,None)]
            while stack:
                node,parent=stack.pop();fid=parent
                if node.type in types and not node.has_error and not node.is_missing:
                    fid=emit(node.type,node.start_byte,node.end_byte,parent=parent,local_complete=not tree.root_node.has_error)
                    if parent:links.append({'from':parent,'to':fid,'relation':'syntax_contains','verification':'Confirmed_syntax_not_causality'})
                stack.extend((ch,fid) for ch in reversed(node.named_children))
            if tree.root_node.has_error:diagnostics.append({'kind':'tree_sitter_parse_error','facts_are_partial':True})
        else:raise ValueError('Unknown frozen extraction method')
        # An identical syntax span/type appears once, retaining separate spans
        # for distinct roles or versions instead of substring similarity merging.
        rows=list({r['fact_id']:r for r in rows}.values())
        spans={r['span_id']:{'span_id':r['span_id'],'source_id':r['source_id'],'source_hash':r['source_hash'],'start_byte':r['start_byte'],
            'end_byte':r['end_byte'],'offset_basis':doc['offset_basis'],'evidence':doc['evidence']} for r in rows}
        return {'method':method,'facts':rows,'evidence_spans':spans,'relations':links,'diagnostics':diagnostics,
            'CPU_seconds':time.process_time()-started,'raw_source_preserved':True,'source_hash':doc['source_hash']}

def byte_point(raw,offset):
    prefix=raw[:offset];return (prefix.count(b'\n'),len(prefix.rsplit(b'\n',1)[-1]))

def edit_range(old,new):
    a=0
    while a<min(len(old),len(new)) and old[a]==new[a]:a+=1
    while a and a<len(new) and new[a]&0xC0==0x80:a-=1
    suffix=0
    while suffix<min(len(old)-a,len(new)-a) and old[-1-suffix]==new[-1-suffix]:suffix+=1
    b=len(old)-suffix;c=len(new)-suffix
    while b<len(old) and old[b]&0xC0==0x80:b+=1;c+=1
    return a,b,c

class IncrementalSyntax:
    def __init__(self):self.engine=SyntaxFacts();self.cache={};self.parses=0;self.incremental_parses=0;self.last_ranges=[]
    def fork(self):
        new=object.__new__(IncrementalSyntax);new.engine=self.engine;new.cache=dict(self.cache);new.parses=self.parses;new.incremental_parses=self.incremental_parses;new.last_ranges=[];return new
    def parse(self,key,text,*,incremental=True):
        raw=text.encode('utf-8');previous=self.cache.get(key);ranges=[]
        if incremental and previous and previous[0]==raw:return previous[1],{'cache_hit':True,'edit_range':None,'structural_ranges':[]}
        if incremental and previous:
            before,tree=previous;tree=tree.copy();a,b,c=edit_range(before,raw)
            tree.edit(start_byte=a,old_end_byte=b,new_end_byte=c,start_point=byte_point(before,a),old_end_point=byte_point(before,b),new_end_point=byte_point(raw,c))
            updated=self.engine.parser.parse(raw,tree);ranges=[(r.start_byte,r.end_byte) for r in tree.changed_ranges(updated)];self.incremental_parses+=1
            edited=[a,c] # changed_ranges may be empty for same-shaped identifier changes.
        else:updated=self.engine.parser.parse(raw);edited=[0,len(raw)]
        self.parses+=1;self.cache[key]=(raw,updated);self.last_ranges=ranges
        return updated,{'cache_hit':False,'edit_range':edited,'structural_ranges':ranges}
