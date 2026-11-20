"""Read-only evidence consolidation and local Markdown/DOCX audit publication.

No API, Docker, GPU, scoring or source-result mutation. Standard-library OOXML.
"""
import json,sqlite3,collections,datetime,hashlib,re,zipfile,csv
from pathlib import Path
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo
from proworksim.software_benchmark_candidates_v054 import reference,checked
R=Path(__file__).resolve().parents[1];OUT=R/'artifacts/experiment-audit-20261120';DOC=R/'docs/experiments/recent-experiment-audit-v217-v221-20261120'
SOURCES={
 'E01':'artifacts/software-benchmark-v217/final-report-r4/summary.json',
 'E02':'artifacts/software-benchmark-v217/final-report-r4/canonical-panels.json',
 'E03':'artifacts/software-benchmark-v217/final-report-r4/confirmation.json',
 'E04':'artifacts/software-benchmark-v217/fixture-recovery-r1/canonical-overlay.json',
 'E05':'artifacts/software-benchmark-v217/resilience-r1/recovery-receipt.json',
 'E06':'artifacts/software-benchmark-v218/results-r1/summary.json',
 'E07':'artifacts/software-benchmark-v219/results-r1/summary.json',
 'E08':'artifacts/software-benchmark-v219/results-r1/panels.json',
 'E09':'artifacts/software-benchmark-v219/protocol-r1/candidate-tasks.json',
 'E10':'artifacts/software-benchmark-v220/trace-audit-r1/summary.json',
 'E11':'artifacts/software-benchmark-v220/trace-audit-r1/episodes.json',
 'E12':'artifacts/software-benchmark-v220/validation-protocol-r1/protocol.json',
 'E13':'artifacts/software-benchmark-v220/validation-protocol-r1/freeze.json',
 'E14':'artifacts/software-benchmark-v221/research-and-admission-r1/admission.json',
 'E15':'artifacts/software-benchmark-v221/offline-navigation-r3/summary.json',
 'E16':'artifacts/software-benchmark-v221/research-and-admission-r1/source-freeze.json',
 'E17':'artifacts/software-benchmark-v221/research-and-admission-r1/sources.json',
 'E18':'src/proworksim/software_organization_selector_v217.py',
 'E19':'src/proworksim/software_organization_selector_v216.py',
 'E20':'src/proworksim/software_organization_space_v210.py'}
def read(p):return json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def source_link(code):return f'[{code}](../../{SOURCES[code]})'
def docx_from_markdown(md,path):
 W='http://schemas.openxmlformats.org/wordprocessingml/2006/main';REL='http://schemas.openxmlformats.org/package/2006/relationships';OFF='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
 ET.register_namespace('w',W);ET.register_namespace('r',OFF)
 def el(parent,tag,attrs=None,text=None):
  e=ET.SubElement(parent,'{'+W+'}'+tag,{'{'+W+'}'+k:str(v) for k,v in (attrs or {}).items()});e.text=text;return e
 root=ET.Element('{'+W+'}document');body=el(root,'body');paragraphs=0;tables=0;plain=[]
 def strip(s):
  s=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'\1 [\2]',s);return s.replace('**','').replace('`','')
 def paragraph(parent,text,style=None):
  nonlocal paragraphs
  text=strip(text);p=el(parent,'p');pr=el(p,'pPr')
  if style:el(pr,'pStyle',{'val':style})
  run=el(p,'r');t=el(run,'t',text=text);t.set('{http://www.w3.org/XML/1998/namespace}space','preserve');paragraphs+=1;plain.append(text);return p
 lines=md.splitlines();i=0
 while i<len(lines):
  line=lines[i]
  if not line.strip():i+=1;continue
  if line.startswith('|'):
   rows=[]
   while i<len(lines) and lines[i].startswith('|'):
    cells=[x.strip() for x in lines[i].strip().strip('|').split('|')]
    if not all(re.fullmatch(r':?-{3,}:?',x) for x in cells):rows.append(cells)
    i+=1
   n=len(rows[0]);assert all(len(r)==n for r in rows)
   table=el(body,'tbl');props=el(table,'tblPr');el(props,'tblW',{'w':9360,'type':'dxa'});el(props,'tblLayout',{'type':'fixed'});borders=el(props,'tblBorders')
   for side in ('top','left','bottom','right','insideH','insideV'):el(borders,side,{'val':'single','sz':4,'color':'D4D9DF'})
   grid=el(table,'tblGrid')
   widths=[9360//n]*n
   for width in widths:el(grid,'gridCol',{'w':width})
   for j,row in enumerate(rows):
    tr=el(table,'tr');trpr=el(tr,'trPr');el(trpr,'cantSplit')
    if j==0:el(trpr,'tblHeader')
    for width,text in zip(widths,row):
     tc=el(tr,'tc');pr=el(tc,'tcPr');el(pr,'tcW',{'w':width,'type':'dxa'})
     if j==0:el(pr,'shd',{'fill':'E8EEF5'})
     paragraph(tc,text,'TableText')
   tables+=1;paragraph(body,'');continue
  if line.startswith('# '):paragraph(body,line[2:],'Title')
  elif line.startswith('## '):paragraph(body,line[3:],'Heading1')
  elif line.startswith('### '):paragraph(body,line[4:],'Heading2')
  elif line.startswith('- '):paragraph(body,'• '+line[2:])
  else:paragraph(body,line)
  i+=1
 sect=el(body,'sectPr');el(sect,'pgSz',{'w':11906,'h':16838});el(sect,'pgMar',{'top':1080,'right':1273,'bottom':1080,'left':1273,'header':450,'footer':450,'gutter':0})
 footerref=el(sect,'footerReference',{'type':'default'});footerref.set('{'+OFF+'}id','rIdFooter')
 styles=ET.Element('{'+W+'}styles');defaults=el(styles,'docDefaults');rpd=el(defaults,'rPrDefault');rp=el(rpd,'rPr');el(rp,'rFonts',{'ascii':'Calibri','hAnsi':'Calibri','eastAsia':'宋体'});el(rp,'sz',{'val':22});el(rp,'lang',{'val':'en-US','eastAsia':'zh-CN'});ppd=el(defaults,'pPrDefault');pp=el(ppd,'pPr');el(pp,'spacing',{'after':110,'line':285,'lineRule':'auto'})
 for sid,size,bold in [('Normal',22,False),('Title',34,True),('Heading1',28,True),('Heading2',24,True),('TableText',18,False)]:
  st=el(styles,'style',{'type':'paragraph','styleId':sid});el(st,'name',{'val':sid});pr=el(st,'pPr');el(pr,'spacing',{'after':100 if sid!='TableText' else 50,'before':180 if sid.startswith('Heading') else 0})
  if sid.startswith('Heading') or sid=='Title':el(pr,'keepNext');el(pr,'outlineLvl',{'val':0 if sid=='Heading1' else 1})
  rp=el(st,'rPr');el(rp,'sz',{'val':size})
  if bold:el(rp,'b')
 footer=ET.Element('{'+W+'}ftr');p=el(footer,'p');el(el(p,'pPr'),'jc',{'val':'center'});el(el(p,'r'),'t',text='实验审计汇总 · ');field=el(p,'fldSimple',{'instr':'PAGE'});el(el(field,'r'),'t',text='1')
 def xml(e):return ET.tostring(e,encoding='utf-8',xml_declaration=True)
 types='''<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/></Types>'''
 top=f'<Relationships xmlns="{REL}"><Relationship Id="rId1" Type="{OFF}/officeDocument" Target="word/document.xml"/></Relationships>'
 drels=f'<Relationships xmlns="{REL}"><Relationship Id="rIdStyles" Type="{OFF}/styles" Target="styles.xml"/><Relationship Id="rIdFooter" Type="{OFF}/footer" Target="footer1.xml"/></Relationships>'
 with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
  for name,data in {'[Content_Types].xml':types,'_rels/.rels':top,'word/document.xml':xml(root),'word/styles.xml':xml(styles),'word/footer1.xml':xml(footer),'word/_rels/document.xml.rels':drels}.items():z.writestr(name,data)
 with zipfile.ZipFile(path) as z:
  assert z.testzip() is None
  for name in z.namelist():ET.fromstring(z.read(name))
  extracted=[x.text or '' for x in ET.fromstring(z.read('word/document.xml')).iter('{'+W+'}t')]
 assert extracted==plain
 return {'paragraphs_including_table_cells':paragraphs,'tables':tables,'xml_package_and_text_consistency':True,'office_visual_pagination_checked':False}

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 inputs={k:reference(R/v) for k,v in SOURCES.items()}
 for ref in inputs.values():checked(ref)
 s217=read(R/SOURCES['E01']);s218=read(R/SOURCES['E06']);s219=read(R/SOURCES['E07']);cost=read(R/SOURCES['E10']);nav=read(R/SOURCES['E14']);future=read(R/SOURCES['E12'])
 p217=read(R/SOURCES['E02']);p218=read(R/'artifacts/software-benchmark-v218/results-r1/panels.json');p219=read(R/SOURCES['E08'])
 assert len(p217)==24 and len(p218)==1 and len(p219)==5
 ids217={r['instance_id'] for r in p217};ids218={r['instance_id'] for r in p218};ids219={r['instance_id'] for r in p219}
 assert not ids217&(ids218|ids219) and not ids218&ids219
 ledger=[];fp={};cutoff=datetime.datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
 with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:
  for version in ('v217','v218','v219'):
   rows=c.execute('select status,count(*),sum(tokens),sum(cost) from requests where slot like ? group by status',(version+':%',)).fetchall();assert len(rows)==1 and rows[0][0]=='settled'
   _,n,t,m=rows[0];ledger.append({'version':version,'requests':n,'tokens':t,'cost_nanoyuan':m,'CNY_upper':m/1e9})
   fingerprints=collections.Counter()
   for (body,) in c.execute("select body from requests where slot like ? and status='settled'",(version+':%',)):
    u=json.loads(body);fingerprints[(u.get('provider_model'),u.get('system_fingerprint'))]+=1
   fp[version]=[{'model':k[0],'fingerprint':k[1],'requests':v} for k,v in fingerprints.items()]
  total=c.execute("select sum(cost) from requests where status='settled'").fetchone()[0]
  unsettled=c.execute("select count(*) from requests where status!='settled'").fetchone()[0]
  live=c.execute("select id,status from slots where status!='closed' and (id like 'v217:%' or id like 'v218:%' or id like 'v219:%')").fetchall()
 assert total==689700074720 and unsettled==0 and not live
 assert sum(r['tokens'] for r in ledger)==232976440 and sum(r['requests'] for r in ledger)==4163
 assert sum(r['cost_nanoyuan'] for r in ledger)==375992977040
 assert total-sum(r['cost_nanoyuan'] for r in ledger)==313707097680
 phase_rows=[]
 for ph in ('dev1','dev2','confirm'):
  v=s217['phases'][ph];phase_rows.append({'version':'v217','phase':ph,'states':v['states'],'arms':v['arms'],'code':v['code_pass'],'legal':v['delivery_pass'],'mean_logical_tokens':v['mean_logical_tokens']})
 phase_rows += [{'version':'v218','phase':'dev2','states':1,'arms':2,'code':2,'legal':0,'mean_logical_tokens':s218['mean_logical_tokens']},{'version':'v219','phase':'dev1','states':1,'arms':3,'code':0,'legal':0,'mean_logical_tokens':sum(o['logical_tokens'] for r in p219 if r['phase']=='dev1' for o in r['outcomes'].values())/3},{'version':'v219','phase':'confirm','states':4,'arms':9,'code':2,'legal':2,'mean_logical_tokens':sum(o['logical_tokens'] for r in p219 if r['phase']=='confirm' for o in r['outcomes'].values())/9}]
 facts={'cutoff_Asia_Shanghai':cutoff,'scope':'v217 through v221; audit publication only','new_model_calls':0,'new_scoring_calls':0,'phase_rows':phase_rows,'ledger':ledger,'provider_identity_observations':fp,'recent_distinct_scored_tasks':len(ids217|ids218|ids219),'recent_continuations':55,'recent_tokens':232976440,'recent_CNY_upper':375.99297704,'prior_CNY_upper':313.70709768,'shared_CNY_upper':total/1e9,'remaining_CNY':1100-total/1e9,'unsettled_requests':0,'active_recent_slots':live,'selection_comparisons':{'v217':s217['policies'],'v219':s219['policies']},'do_not_pool_success_rates':True,'counting_note':'v219 is recovery of six v218 identities; 5 completed panels are distinct from the one completed v218 task, but not six new unique tasks.'}
 save(OUT/'audit-facts.json',facts);save(OUT/'source-manifest.json',{'cutoff':cutoff,'sources':inputs,'current_ledger_read_only':True,'full_ledger_not_exported':True})
 with (OUT/'phase-results.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(phase_rows[0]));w.writeheader();w.writerows(phase_rows)
 body=build_text(facts,s217,s218,s219,cost,nav,future)
 DOC.with_suffix('.md').write_text(body)
 check=docx_from_markdown(body,DOC.with_suffix('.docx'));check.update({'source_hashes_verified':len(inputs),'cash_reconciled':True,'new_model_calls':0,'outputs':{'markdown':reference(DOC.with_suffix('.md')),'word':reference(DOC.with_suffix('.docx'))}});save(OUT/'publication-check.json',check)
 package=OUT/'audit-package-v217-v221-20261120.zip';packaged={}
 with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as z:
  for file in (DOC.with_suffix('.md'),DOC.with_suffix('.docx'),OUT/'audit-facts.json',OUT/'phase-results.csv',OUT/'source-manifest.json',OUT/'publication-check.json'):
   z.write(file,'report/'+file.name)
  for code,ref in inputs.items():
   source=checked(ref);name='evidence/'+code+'-'+source.name;z.write(source,name);packaged[code]={'archive_path':name,**ref}
  z.writestr('evidence-index.json',json.dumps(packaged,ensure_ascii=False,indent=2))
  z.writestr('README.txt','Scope: v217-v221 audit summary, no new experiment. report/ contains Word, Markdown and accounting. evidence/ contains the exact 20 cited source snapshots. SHA256 and original server paths are in evidence-index.json. Full raw requests, workspaces and scorer logs remain on the project server; this package does not contain the complete runs directory. Cost figures are frozen peak-tariff ledger upper bounds, not supplier invoices. Word XML/text validated; visual pagination not rendered.\n')
 with zipfile.ZipFile(package) as z:
  assert z.testzip() is None
  for row in packaged.values():assert hashlib.sha256(z.read(row['archive_path'])).hexdigest()==row['sha256']
 save(OUT/'package-check.json',{'source_snapshot_count':len(inputs),'all_archive_source_hashes_verified':True,'package':reference(package)})
 print(json.dumps({'package':str(package),'markdown':str(DOC.with_suffix('.md')),'word':str(DOC.with_suffix('.docx')),'tables':check['tables'],'facts':str(OUT/'audit-facts.json'),'cash':facts['shared_CNY_upper']},ensure_ascii=False))

def build_text(f,s217,s218,s219,cost,nav,future):
 L=['# 近期组织策略与项目图实验审计汇总','', '范围：v217至v221，2026年11月19日至20日。数据截至 '+f['cutoff_Asia_Shanghai']+'。','',
'## 一 审计结论','',
'**工程链路已有实质进展，项目图与C/N的算法收益尚未得到验证。** 最近三批收费运行已结束；当前没有在途请求。两批冻结确认分别只有13题和4题，且存在历史曝光、单次生成及候选差异不足，不能外推完整SWE-bench Verified成绩。','',
'本轮可支持的判断是：真实责任调整、共享预算、候选续跑、官方评分和策略更新已实际执行；候选解析与部分错误分类问题已修复；图辅助定位已完成工程实现。尚不能支持“图提高正确率”“N带来探索收益”或“热缓存加速等于整体Token节省”。','',
'建议审计结论：运行与追溯链限定通过；科学增益暂不通过；下一步维持小规模、单因素清楚的验证。v220的16条B/V回合只冻结方案、未启动；v221的图定位另设对照，不能混入旧方案。 [E01、E07、E12、E14]','',
'## 二 实验怎样运行以及比较什么','',
'底层仍是OpenHands，PROJECT在其上增加成员身份、私有工作区、责任/复核、固定补丁、版本证据及正式交付规则。本批使用DeepSeek Flash非思考模式、两个实际成员，共享每条完整任务500万输入加输出Token；不训练模型。成员职责由实际工作安排决定，并非始终固定为开发者和复核者。队内按受管调度逐次行动，不同任务可并发。','',
'先让模型拆分公开题目并开始工作，在已有代码和公开测试、仍有未完成义务时保存共同检查点；再形成KEEP及至多两个合法调整候选。每个候选从同一检查点独立续跑一次。改变责任必须实际offer/accept，提示建议不等于执行。C1、C2是每题候选编号，不是跨题固定组织模式。','',
'| 条件 | 实际含义 |','|---|---|',
'| KEEP | 保持已有分包、责任和依赖；可补齐验证设置并继续修复、交付，不等于单Agent。 |',
'| q0 | 在该题合法候选中均匀选择，不学习。 |',
'| L_CN | 依据工作台账特征，使用C与N学习选择。 |',
'| P_C | 加入真实项目关系特征，仅使用贡献反馈C。 |',
'| P_CN | 使用项目关系特征，同时使用C与N；本批主要方法。 |','',
'五种策略共用同题候选结果。确认阶段按事前冻结概率加权，再对任务等权平均；**不是为五种策略各独立运行一套任务，也不是把全部候选混合平均。** 没有完整候选评分的面板不能填0进入学习。 [E02、E03、E08、E18]','',
'效用U＝合法且正确交付（0或1）−0.1×完整任务Token/500万。C＝候选U减当前策略的平均U；N＝max(log(均匀参照概率/当前概率),0)。N表示欠覆盖，不是代码创新度、成员数量或历史交流次数。C/N经过固定变换生成目标分布，再拟合七维共享选择器；不改变模型权重。初始均匀策略下N为0符合定义。 [E18—E20]','',
'模型返回的名称均为deepseek-flash，4163个近期请求记录到相同system_fingerprint；这支持接口身份一致，但不等于独立核验了供应商权重。API没有可核验的固定生成seed；登记seed控制调度/选择，不保证不同回合产生相同随机序列。','',
'## 三 每轮完成情况与范围变化','',
'| 版本 | 原计划与实际范围 | 结果与状态 |','|---|---|',
'| v217 | 28主状态＋4备用；32个准备状态中24个合格，41条续跑，低于84条上限 | 开发11状态19条，确认13状态22条；两次真实更新；补评后无评分未知。 |',
'| v218 | 8题、最多24条；只有1题形成完整面板、运行2条 | 5题生成器格式/合法性失败，1题前缀未准入，1题前缀技术中断；新增1次更新，确认0题。 |',
'| v219 | 恢复v218的6个状态、最多15条；5个完整面板12条 | 5题复用原检查点并离线修复提案；技术中断题独立重跑一次前缀后未取得结构候选；新增1次更新，确认4题。 |',
'| v220 | 不运行新任务 | 完成12条轨迹及662次续跑请求归因，冻结16条定向验证方案。 |',
'| v221 | 不运行新模型评测 | 新图定位/证据工具通过CPU、真实SDK脚本控制和4个历史快照离线检查。 |','',
'v217实际未满足全部原计划状态数；没有凑够84条是合法候选数量及准入规则的结果。v218和v219有重复任务身份，不能把恢复视为新增6个不同题目。近期收费批共有55条续跑，覆盖30个有评分的不同任务；各轮实现、选择与准备规则不同，以下分批报告，不合并成功率。 [E01、E06—E09]','',
'| 批次／阶段 | 有评分状态 | 续跑 | 代码通过 | 合法正确交付 | 平均完整任务万Token |','|---|---:|---:|---:|---:|---:|']
 names={'dev1':'开发1','dev2':'开发2','confirm':'冻结确认'}
 for x in f['phase_rows']:L.append(f"| {x['version']} {names[x['phase']]} | {x['states']} | {x['arms']} | {x['code']}/{x['arms']} | {x['legal']}/{x['arms']} | {x['mean_logical_tokens']/10000:.2f} |")
 L+=['','本表清点实际回合，拥有更多候选的题出现更多次；正式选择策略比较见下一节。完整任务Token＝共同前缀P＋候选生成G＋本条续跑L，物理账本不重复支付共享P/G。 [E01、E06—E08]','',
'## 四 冻结确认对策略收益的证据','',
'### v217的13题确认','',
'| 策略 | 加权代码正确率 | 加权合法交付率 | 平均完整任务万Token | 平均效用 |','|---|---:|---:|---:|---:|']
 for q,x in s217['policies'].items():L.append(f"| {q} | {100*x['code_quality']:.2f}% | {100*x['quality']:.4f}% | {x['tokens']/10000:.4f} | {x['utility']:.6f} |")
 L+=['','所有策略代码正确率相同，相当于9/13。P_CN交付率比KEEP低约2.54个百分点，未超过台账L_CN。相对均匀q0的交付增益仅约0.0276个百分点，平均约少126 Token。13题有8题只有KEEP，只有5题能够真正比较选择；合法交付的候选差异仅发生在1题。删除该题后，P_CN相对q0的平均效用差约0.000000627。不能据这个面板宣布图/CN有效。 [E01—E03]','',
'### v219的4题确认','',
'| 策略 | 加权代码正确率 | 加权合法交付率 | 平均完整任务万Token | 平均效用 |','|---|---:|---:|---:|---:|']
 for q,x in s219['policies'].items():L.append(f"| {q} | {100*x['code_quality']:.2f}% | {100*x['quality']:.2f}% | {x['tokens']/10000:.4f} | {x['utility']:.6f} |")
 L+=['','P_CN相对KEEP平均少约6.1% Token，但正确率/交付率没有提高，且Token略多于均匀q0。这个结果支持“有些调整更省成本”，尚不支持“学到的选择器优于简单参照”。例如一个候选更快提交但代码错误，成本效用仍可能偏好它；正确性和成本应分别报告。 [E07、E08]','',
'当前这条主线的选择器更新次数累计为4：v217两次、v218一次、v219一次。后两轮因窗口无合格样本，各跳过了一次计划更新。v219从v218第三次更新起步，没有把已经完成的SymPy-13757两条再用于新学习；确认成绩不反向拟合参数。尤其v218新增开发2条、v219新增开发3条均没有合法成功交付，因此这两轮新增C信号只来自Token成本差异，没有新的成功交付正例；N仍按参照欠覆盖计算。参数更新完成不等于学到了提高成功率的规律。单候选状态、每候选单次生成和样本选择限制了因果解释，没有进行正式显著性或非劣效检验。','',
'## 五 Token归因和失败机制','',
'v220完整核对v219的12条续跑：662个请求，实际39,812,572 Token（输入39,645,558、输出167,014）。它与v219全批690请求的差额来自新恢复前缀及生成器。','',
'| 当前调用目的 | 请求数 | 输入万Token | 输出万Token | 占续跑Token |','|---|---:|---:|---:|---:|']
 labels={'locating_reading':'定位搜索读取','organization_and_delivery':'组织与交付','tests_and_feedback':'测试和反馈','peer_communication':'消息与补丁交接','editing':'代码修改','private_notes':'私有笔记','wait_done':'等待／结束','history_summary':'历史摘要','other_or_invalid_output':'其他／不可解析'}
 for k,v in sorted(cost['groups'].items(),key=lambda x:-x[1]['tokens']):L.append(f"| {labels[k]} | {v['requests']} | {v['input_tokens']/10000:.3f} | {v['output_tokens']/10000:.3f} | {v['tokens']/cost['continuation_tokens']:.2%} |")
 L+=['',
'这是按当前响应操作分类的整请求usage，已经包含输出。它不是内容来源归因：发消息时输入包含整个历史，伙伴消息在后续其他操作中再次出现。因此6.66%不能称为通信内容占比，也不是通信可节省量的上界或下界；不能把定位35.42%全部当作可消除成本。 [E10、E11]','',
'50次求解侧测试请求中，严格同成员/同版本/同选择重复仅1次；109次文件读取中，同成员/同内容/同区间重复2次。该计数不覆盖跨成员、重叠读取或历史再呈现，不能据此说没有冗余。','',
'| 失败或成本现象 | 已观察证据 | 可支持的判断 |','|---|---|---|',
'| 预算边界 | v219为9/12条，9条最终代码均未通过 | 预算限制了后续行动，但没有证明加预算就能修好。 |',
'| 修复破坏既有行为 | SymPy-16792 KEEP目标测试通过，但8项既有验收失败 | 需要同时检查目标修复与回归，不只增加协调步骤。 |',
'| 合法提交但题目仍未修好 | sklearn-26323 C1约364.59万Token正式提交；复核明确承认没有直接覆盖题面关键组合 | 此例不是预算截止导致；“流程齐全”不等于“需求被验证”。 |',
'| 更少工作可以有益也可以有害 | Astropy-14539 C1比KEEP少约103.78万Token，两者均正确；上述sklearn C1也更快但失败 | 区分有效减少工作与过早满足于测试结果。 |',
'| 阶段等待分类 | v218两条实际role_stops均为预算耗尽，却记为quiescent；v219修正分类并发生5次有限提醒 | 0静止标签不等于已证明提醒提高成功率，须保留原记录。 |','',
'配置双成员不保证每条续跑都有同样的参与度：SymPy-16792 KEEP的第二成员只有1次摘要请求，没有新的Agent行动请求。不能仅按人数推断通信或并行收益。\n\n这些为逐轨迹证据及有限解释，不能把同题一次随机生成中的所有差值归给组织方式。详细动作、版本、测试和逐请求原件引用保存在E11及v220请求表。','',
'## 六 异常修复是否改变了实验','',
'| 修订 | 原问题和处理 | 审计边界 |','|---|---|---|',
'| v217.1评分分类 | 锁定候选留有合并冲突，补丁实际应用后语法错误；绑定原文件/行/测试退出证据，规范为候选失败 | 原raw未知保留；不是重跑模型取更高分。 |',
'| v217.3 Sphinx补评 | 候选测试辅助文件与官方新增测试同名，阻止隐藏测试补丁应用；评分容器中重置该测试文件后注入原官方测试 | gold真、empty假、候选真；代码和合法提交同树复用；3容器已清理、0模型调用。是评分侧环境修订，不能说环境毫无变化。 |',
'| v218阶段提示 | 明确前缀结束、恢复后继续；全员等待时最多两次有限提醒 | 提醒计入真实后续输入，不代操作、不复活技术故障停止者；收益未单独因果验证。 |',
'| v219候选恢复 | 完整JSON后的纯结束符、两种非操作注释、完全不变的已开工工作项造成拒绝 | 5题由原输出离线重编译；保留原文哈希和修复记录，再过全部权限/结构校验；0新增生成器调用。 |',
'| v219输入错误恢复 | 已声明工具多带保留字段，在0执行、无pending/result且身份完整时拒绝并给预算内格式反馈 | 不剥离参数后执行；未知工具、身份复用、已执行请求不降级处理；原技术中断题仅一次新身份前缀。 |',
'| v217.2性能与调度 | 评分占用生成槽、大状态处理慢 | 生成与评分分离；缓存优化只给未开始分支，旧进程不停。局部2.49倍基准不是整轮加速。 |','',
'v219的Django-11490前缀恢复成功，但最终只剩KEEP；生成器一次给出纯补设置，纠正后没有结构调整。只能称“未观察到符合本轮定义的候选”，不能断言无任何有效协作。v218正常预算内未取得准入的Django-15375没有为了凑数重跑。 [E04—E09]','',
'## 七 项目图定位已实现到哪一步','',
'原项目图由成员可见的工作事件维护要求、工作包、代码区域、产物、测试和版本关系；角色声明与静态引用不自动升级成语义事实。v221增加当前授权快照的全局检索、Python符号及导入/名称引用候选，图只做软排序，保留全局发现，不强制补入弱相关邻居。','',
'新增locate_work返回文件、符号、行号、来源版本及原read_file调用参数；支持合法固定patch_id，读取仍绑定同一候选。record_public_check把公开要求与本人真实测试及版本关联；public_check_status区分未绑定、历史版本、失败和“通过但覆盖未验证”。它们不自动接受复核、提交或认证语义覆盖。','',
'| v221证据 | 已完成 | 尚未证明 |','|---|---|---|',
'| 5项CPU控制 | 增量更新、删改、资源边界、私有权限、固定补丁导航、测试版本绑定 | 不代表真实任务解决率。 |',
'| 新57工具真实SDK控制 | 新检查点恢复，44脚本响应、4次CPU测试、1次合法交付；0供应商调用 | 旧54工具检查点不能直接恢复为57工具；未放宽兼容检查。 |',
'| 4个历史仓库快照 | 冷构建7.16–17.69秒、热更新0.05–0.13秒、返回约6754–7568字符 | 不代表端到端速度、API Token节省或图的独立增益。 |',
'| 成本与权限 | 过滤二进制挤占；新增3工具约2002个schema字符；每次先权限检查后查缓存 | 新schema、检索调用、索引CPU与内存须纳入净收益。 |','',
'本轮借鉴Agentless分层定位、RepoGraph仓库关系、Aider紧凑地图及SWE-agent工具界面设计，非完整复现；一手来源已在E17记录。原v220 B/V方案保持不变，图G需要另设同工具集和新共同检查点的L/G对照。 [E14—E17]','',
'## 八 费用和数据完整性','',
'以下Token为供应商实际usage；费用为实验账本按冻结峰值规则计算的人民币上界，不等同于供应商发票。缓存命中已包含在输入，不重复相加。旧失败费用保留，没有因恢复清零。','',
'| 批次 | 已结算请求 | 实际输入加输出Token | 账本费用上界元 |','|---|---:|---:|---:|']
 for r in f['ledger']:L.append(f"| {r['version']} | {r['requests']:,} | {r['tokens']:,} | {r['CNY_upper']:.8f} |")
 L += [f"| 最近三批合计 | 4,163 | 232,976,440 | {f['recent_CNY_upper']:.8f} |",'| v220与v221工程工作 | 0模型请求 | 0供应商Token | 0 |','',
'此前费用313.70709768元＋最近三批375.99297704元＝累计689.70007472元。累计上限1100元，余额410.29992528元；0未结请求、0近期活动slot。v219复用的P/G在逻辑预算中保留、物理账本不重付；不同条件共享前缀不作为新的独立任务。','',
'本审计只读汇总，未新建实验容器、启动模型或修改共享服务器。v221无收费评测；CPU和SDK合成控制另标，不计入模型成绩。','',
'## 九 下一步方案和待审事项','',
'**v220已冻结、未执行：** 4个已知诊断状态×KEEP/C1×B原验证/V公开需求验证，共16条新独立尝试。原5M上限、上下文、工具权限和组织候选保持，C/N不更新。新Token上限58,420,860，属于上限而非预计消费。任务因已知轨迹选择，不是独立确认集。 [E12、E13]','',
'V要求实现者从原公开题面形成可运行检查，复核者核对输入、期望和版本；不能用隐藏测试或仅凭测试名称判定覆盖。主分析保留未遵循V提示的回合，不能只统计“执行成功”的子集。运行实现与观察器需先准入。','',
'**v221另拟、未冻结付费题单：** 相同新工具集下比较L全局检索与G全局检索加图；需新共同检查点、同输出预算、同验证条件。不能直接把图工具加入原B/V组，导致两个处理混在一起。','',
'按历史平均账单计价并用满58.42M新Token约76元，但最坏8元/百万Token约467.37元，高于当前余额，不能保证最坏情况下16条全部准入。启动时需整题四条预约、保留不完整状态，已开始回合不因现金估计中断。当前没有新收费回合启动。','',
'| 审计事项 | 本报告建议 | 核验重点 |','|---|---|---|',
'| 结果能否追溯 | 限定通过 | 原结果、规范overlay、同树评分复用、账本、文件哈希对应。 |',
'| 图/CN是否已有收益 | 尚未通过 | 有效多候选任务少，结果差异少，P_CN未超过简单参照。 |',
'| 是否继续研究 | 可以，先做定向验证 | 固定处理变量，记录公开覆盖、真实操作、费用和全部失败。 |',
'| 是否立即扩样或调参 | 不建议 | 先解决验证覆盖和有区分的候选；不在既有确认成绩上调参数后复报。 |','',
'## 十 审计资料索引','',
'本报告、Word版、核对表、分阶段CSV、20份原始来源快照及其哈希在同一审计包中。机器可读source-manifest.json为每个E编号提供服务器原路径、SHA256和字节数；完整请求/工作区/评分日志继续保留在原runs目录，未复制进轻量审计包。','',
'| 证据编号 | 内容 |','|---|---|',
'| E01—E05 | v217最终分母、候选面板、概率比较及两项评分修订 |',
'| E06—E09 | v218原失败与v219独立恢复、实际面板及冻结题单 |',
'| E10—E11 | 逐轨迹Token、版本测试、错误与官方验收 |',
'| E12—E13 | 未启动的16条B/V方案及冻结哈希 |',
'| E14—E17 | 图定位工程准入、离线检查、源码及一手来源 |',
'| E18—E20 | 选择特征、效用、C/N定义与更新实现 |','',
'[审计事实表](../../artifacts/experiment-audit-20261120/audit-facts.json) · [来源及哈希索引](../../artifacts/experiment-audit-20261120/source-manifest.json) · [分阶段CSV](../../artifacts/experiment-audit-20261120/phase-results.csv)','',
'审计限制：本报告由助手基于记录复核，不冒充独立人工专家验收；没有开展新的解题试验、重复抽样或官方评分。Word做包结构、XML及文字/表格一致性校验，当前环境未提供Office分页渲染。']
 return '\n'.join(L)+'\n'

if __name__=='__main__':main()
