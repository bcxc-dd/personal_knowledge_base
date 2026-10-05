"""Prepare source-grounded TEST candidates for human review; never run matchers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INTAKE = ROOT / 'test-results/test-frozen-intake-2026-10-03'
OUT = INTAKE / 'test-candidate-review-v5'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def slot(fact_id: str, fact_type: str, target: dict, **answer: object) -> tuple[dict, dict]:
    return ({'fact_id': fact_id, 'fact_type': fact_type, 'target': target},
            {'fact_id': fact_id, 'fact_type': fact_type, **answer})


# Every proposed value below was checked against the rendered PDF page and the
# saved production-parser 400/60 chunk. Human review is still required.
SPECS = [
    dict(id='P01', doc='policy', page=[3], type='COMPOUND',
         query='一般推免生的前三年总GPA和专业排名要同时达到什么要求？', pos=['policy:4'],
         slots=[slot('gpa', 'numeric_requirement', {'scope':'一般推免生','metric':'前三年总GPA'}, metric='前三年总GPA', operator='>=', value=3.0, scope='一般推免生'),
                slot('rank', 'numeric_requirement', {'scope':'一般推免生','metric':'本专业总GPA排名'}, metric='本专业总GPA排名', operator='前', value='50%', scope='一般推免生')],
         answer='一般推免生前三年总GPA不低于3.0，且总GPA排名须列本专业前50%。',
         notes='两个条件均为必答；不能用其他类型推免生的3.0替代专业排名。'),
    dict(id='P02', doc='policy', page=[3], type='CONDITION',
         query='一般推免生不用大学英语四级成绩时，雅思达到多少分可以满足外语条件？', pos=['policy:4'],
         slots=[slot('ielts_alternative', 'numeric_requirement', {'scope':'一般推免生','condition':'未使用CET4路径','metric':'雅思成绩'}, metric='雅思成绩', operator='>=', value=6.0, scope='一般推免生', condition='作为CET4替代路径')],
         answer='一般推免生可用雅思6.0分（含）以上满足该外语条件。',
         notes='“或”“含”明确支持替代与含6.0边界；不推断CET4未达标的其他后果。'),
    dict(id='P03', doc='policy', page=[3], type='YES_NO',
         query='本科学业指导教师与学生合作的成果，是否受“与学历、职称明显高于本人者合作”限制？', pos=['policy:5'],
         slots=[slot('exception', 'boolean_claim', {'proposition':'本科学业指导教师合作受该限制'}, answer='NO', exception='本科学业指导教师与学生合作不受该限制')],
         answer='不受该限制。细则明确将本科学业指导教师与学生合作列为例外。',
         relation='CONTRADICTS_QUERY_PROPOSITION', notes='否定极性和教师例外必须同时保留。'),
    dict(id='P04', doc='policy', page=[5], type='COMPOUND',
         query='候补名额一般按什么比例确定，名单公示后有人放弃时如何递补？', pos=['policy:8'],
         slots=[slot('reserve_ratio', 'numeric_requirement', {'metric':'候补名额比例'}, metric='候补名额比例', operator='一般为', value='10%', scope='学校发布的名额'),
                slot('replacement', 'policy_rule', {'condition':'公示后推荐名单学生放弃或被取消资格'}, scope='公示后的候补名单', condition='推荐名单学生放弃或被取消资格', consequence='一般按排名顺序从已公示候补名单依次递补')],
         answer='候补名额按学校发布的比例确定，一般为10%；公示后有人放弃或被取消资格，一般从公示的候补名单中按排名顺序依次递补。',
         notes='用户已指定 policy:8 单独为 FULL、policy:9 为 PARTIAL；普通 COMPOUND，非严格跨 chunk 样本。'),
    dict(id='P05', doc='policy', page=[7], type='WH',
         original='GPA 相同的一般推免生，先按什么规则排定先后？',
         query='一般推免生总GPA相同时，依次按哪些规则决定排名？', pos=['policy:12'],
         slots=[slot('tie_break', 'ordered_rule', {'scope':'一般推免生','condition':'总GPA相同'}, scope='一般推免生', condition='总GPA相同', order=['无不及格重修记录优先','已获学分多优先','已获学分相同时已获成绩绩点多优先','仍无法排序时经工作组认定的奖励、成果或突出表现者优先'])],
         answer='依次比较：无不及格重修记录、已获学分数量、已获成绩绩点；仍无法排序时，经工作组认定的奖励、成果或其他突出表现者优先。',
         notes='原问“先按什么”只需第一项，与完整多级排序 gold 不符，故明确改问“依次”。'),
    dict(id='P06', doc='policy', page=[7], type='YES_NO',
         query='2024年9月6日当天补录的成绩会计入本细则的GPA排名吗？', pos=['policy:13'],
         slots=[slot('date_boundary', 'boolean_claim', {'proposition':'2024-09-06当天补录成绩计入GPA排名'}, answer='NO', cutoff='2024-09-06（不含）之前录入')],
         answer='不会。细则以2024年9月6日（不含）之前录入的成绩为准，9月6日（含）之后不再接受补录或新变化。',
         relation='CONTRADICTS_QUERY_PROPOSITION', notes='PDF 明确同时写“不含”与“含”，边界无歧义。'),
    dict(id='T01', doc='technical', page=[11], type='DEFINITION',
         query='白皮书如何定义云密码服务？', pos=['technical:30'],
         slots=[slot('definition', 'definition', {'subject':'云密码服务'}, subject='云密码服务', value='云计算技术与身份认证、授权访问、传输加密、存储加密等密码技术融合的密码功能交付模式；提供商整合产品、策略、接口与流程为服务')],
         answer='白皮书将云密码服务定义为一种密码功能交付模式：云计算技术与认证、授权和加密等密码技术融合，由提供商整合产品、策略、接口和流程，以服务形式交付。',
         notes='问题只问定义，不把后列所有商业优势都升为必答。'),
    dict(id='T02', doc='technical', page=[16], type='WH',
         original='云密码资源池服务为何倾向把硬件密码模块单独部署？',
         query='为什么通常单独部署云密码资源池，而不在云服务器内部署硬件密码模块？', pos=['technical:43'],
         slots=[slot('reason', 'causal_reason', {'subject':'单独部署云密码资源池'}, reason='在云服务器中部署硬件密码模块比较困难', context='重要应用的密码运算和密钥管理要求使用硬件密码模块')],
         answer='重要应用需要硬件密码模块保障密码运算和密钥管理，但在云服务器内部署这类模块较困难，因此通常单独部署云密码资源池并通过网络调用。',
         notes='原问“倾向”易混淆原因与做法，改问明确的因果。'),
    dict(id='T03', doc='technical', page=[13], type='WH',
         original='云密钥管理服务要解决云中哪些密钥管理需求？',
         query='云中密钥的生成、存储、销毁和获取、使用分别需要满足什么要求？', pos=['technical:35','technical:36'],
         slots=[slot('lifecycle', 'set_requirement', {'subject':'云中密钥生命周期'}, items=['生成安全','存储安全','销毁安全']),
                slot('usability', 'set_requirement', {'subject':'云中密钥使用'}, items=['方便获取','方便使用'])],
         answer='云中密钥的生成、存储和销毁必须安全，同时还应便于获取和使用。',
         notes='原问范围过宽；改为原文明确列出的两组要求。technical:35 已覆盖核心，36 为连续上下文。'),
    dict(id='T04', doc='technical', page=[71], type='COMPARISON',
         original='白皮书所述CASB代理模式与API模式有何区别？',
         query='白皮书中CASB代理模式与API模式在技术本质上有何区别？', pos=['technical:164'],
         slots=[slot('proxy_mode', 'comparison_relation', {'mode':'CASB代理模式','aspect':'技术本质'}, subject='CASB代理模式', relation='技术本质', object='网关侧分析和代理应用请求，以适配方式增强数据安全与业务安全'),
                slot('api_mode', 'comparison_relation', {'mode':'CASB API模式','aspect':'技术本质'}, subject='CASB API模式', relation='技术本质', object='应用内识别用户数据操作，以配置方式增强数据安全')],
         answer='代理模式在网关侧分析并代理应用请求，以适配增强安全；API模式在应用内识别用户数据操作，以配置增强安全。',
         notes='原问可涉及优缺点和部署，跨 technical:164/165；收窄到表格“技术本质”行，核对两列绑定。'),
    dict(id='T05', doc='technical', page=[17], type='WH',
         query='白皮书称NIST将云计算服务分为哪三种模式？', pos=['technical:46'],
         slots=[slot('iaas', 'category', {'code':'IaaS'}, code='IaaS', name='基础设施即服务'),
                slot('paas', 'category', {'code':'PaaS'}, code='PaaS', name='平台即服务'),
                slot('saas', 'category', {'code':'SaaS'}, code='SaaS', name='软件即服务')],
         answer='基础设施即服务（IaaS）、平台即服务（PaaS）和软件即服务（SaaS）。',
         notes='三种模式及中文全称全部必答。'),
    dict(id='A01', doc='paper', page=[1], type='WH',
         query='论文假设不同领域的用户物品交互之间存在什么关联？', pos=['paper:1'],
         slots=[slot('hypothesis', 'research_hypothesis', {'subject':'不同领域用户-物品交互行为'}, claim='存在潜在的模式关联')],
         answer='论文假设，不同领域的用户—物品交互行为之间存在潜在的模式关联。',
         notes='保持“研究假设”语气，不写成已经证明的普遍事实。'),
    dict(id='A02', doc='paper', page=[4], type='COMPARISON',
         query='PEIDR中XSimGCL和BGE分别用于什么？', pos=['paper:22'],
         slots=[slot('xsimgcl', 'component_role', {'component':'XSimGCL'}, component='XSimGCL', role='联合编码目标域和辅助域的用户-物品二分图，得到用户与物品嵌入'),
                slot('bge', 'component_role', {'component':'BGE'}, component='BGE', role='编码辅助域物品文本描述以获取语义信息')],
         answer='XSimGCL 联合编码目标域与辅助域的用户—物品二分图，生成嵌入；BGE 编码辅助域物品的文本描述，提取语义信息。',
         notes='同一 chunk 清楚区分两个模型角色；公式字形损坏与此题无关。'),
    dict(id='A03', doc='paper', page=[1], type='WH',
         query='论文方法如何利用辅助域信息增强目标域推荐？', pos=['paper:1'],
         slots=[slot('source_information', 'method_step', {'role':'来源'}, value='辅助域用户-物品交互信息与物品描述信息'),
                slot('transfer', 'method_step', {'role':'迁移'}, value='联合图编码并引入交互行为语义模式'),
                slot('target_usage', 'method_step', {'role':'目标'}, value='迁移到目标域以增强ID推荐中的交互行为语义')],
         answer='方法联合编码辅助域与目标域信息，再通过交互行为语义模式把辅助域的用户—物品交互及物品描述信息迁移到目标域，增强目标域ID推荐的交互语义。',
         notes='摘要支持来源、迁移机制与目标用途；不要求超出摘要的算法细节。'),
    dict(id='A04', doc='paper', page=[8], type='WH',
         query='论文怎样通过消融实验验证交互行为语义模式增强的作用？', pos=['paper:44','paper:45'],
         slots=[slot('setup', 'experiment_setup', {'subject':'交互行为语义模式增强'}, comparison='有/无行为语义模式增强', control='超参数与PEIDR对比试验相同'),
                slot('result', 'experiment_result', {'metric':'推荐效果'}, direction='引入行为语义模式增强后提升'),
                slot('conclusion', 'author_conclusion', {'subject':'该增强模块'}, claim='作者认为其能有效提升模型推荐结果')],
         answer='作者在相同超参数下对比有、无行为语义模式增强的PEIDR；表4结果显示引入该增强后推荐效果提升，据此认为增强有效。',
         notes='正文有实验设置和作者结论，表4给出数值；不能据表外推其他因果。'),
    dict(id='A05', doc='paper', page=[8], type='TABLE_LOOKUP',
         query='Yelp2018上有无行为语义模式增强时，Recall@20分别是多少？', pos=['paper:45'],
         slots=[slot('with_enhancement', 'table_lookup', {'dataset':'Yelp2018','metric':'Recall@20','variant':'PEIDR(Ours)'}, row='Yelp2018', column='Recall@20 / PEIDR(Ours)', value=0.0744),
                slot('without_enhancement', 'table_lookup', {'dataset':'Yelp2018','metric':'Recall@20','variant':'无行为语义模式增强'}, row='Yelp2018', column='Recall@20 / 无行为语义模式增强', value=0.0729)],
         answer='Yelp2018的Recall@20：有行为语义模式增强为0.0744，无增强为0.0729。',
         notes='逐格对照 PDF 表4；表3的PEIDR 0.0744不能替代消融表的无增强值。'),
    dict(id='F01', doc='tables', page=[3], type='TABLE_LOOKUP',
         query='全日制专业学位硕士中，食品工程的每学年学费是多少？', pos=['tables:4'],
         slots=[slot('food_fee', 'table_lookup', {'degree_type':'专业学位硕士','study_mode':'全日制','major':'食品工程','period':'每学年'}, row='全日制专业学位硕士 / 食品工程', column='收费标准', value=12000, unit='元/学年')],
         answer='全日制专业学位硕士食品工程学费为12000元/学年。',
         notes='收费项目为跨行类别标签，金额须绑定食品工程行。'),
    dict(id='F02', doc='tables', page=[3], type='COMPARISON',
         query='全日制专业学位硕士的控制工程比食品工程每学年学费高多少？', pos=['tables:4'],
         slots=[slot('control_fee', 'table_lookup', {'degree_type':'专业学位硕士','study_mode':'全日制','major':'控制工程'}, row='全日制专业学位硕士 / 控制工程', column='收费标准', value=18000, unit='元/学年'),
                slot('food_fee', 'table_lookup', {'degree_type':'专业学位硕士','study_mode':'全日制','major':'食品工程'}, row='全日制专业学位硕士 / 食品工程', column='收费标准', value=12000, unit='元/学年'),
                slot('difference', 'arithmetic_difference', {'minuend':'控制工程','subtrahend':'食品工程'}, value=6000, unit='元/学年')],
         answer='控制工程18000元/学年，食品工程12000元/学年，因此高6000元/学年。',
         notes='差额由 PDF 同一类别的正确两行计算，不能仅凭裸金额。'),
    dict(id='F03', doc='tables', page=[3], type='COMPARISON',
         query='工商管理MBA的全日制与非全日制硕士学费各是多少？', pos=['tables:5'],
         slots=[slot('full_mba', 'table_lookup', {'major':'工商管理(MBA)','study_mode':'全日制'}, row='全日制专业学位硕士 / 工商管理(MBA)', column='收费标准', value=99000, unit='元/学年'),
                slot('part_mba', 'table_lookup', {'major':'工商管理(MBA)','study_mode':'非全日制'}, row='非全日制硕士 / 工商管理(MBA)', column='收费标准', value=114000, unit='元/学年')],
         answer='工商管理（MBA）全日制硕士为99000元/学年，非全日制硕士为114000元/学年。',
         notes='同名专业相邻不同培养方式；“泛血管”MBA 214000 元为另一行，不可混用。'),
    dict(id='F04', doc='tables', page=[3], type='TABLE_LOOKUP',
         query='全日制学术型博士中，系统科学专业的每学年学费是多少？', pos=['tables:5','tables:6'],
         slots=[slot('doctoral_fee', 'table_lookup', {'degree_type':'学术型博士','study_mode':'全日制','major':'系统科学'}, row='全日制学术型博士 / 系统科学', column='收费标准', value=9000, unit='元/学年')],
         answer='全日制学术型博士系统科学专业学费为9000元/学年。',
         notes='PDF 中类别跨行；pypdf 在 tables:5 与 6 仍保留类别、专业和金额顺序，需人工再确认映射。'),
    dict(id='F05', doc='tables', page=[3], type='COMPARISON',
         query='成人高校夜大一般专业与特殊专业的每学年学费分别是多少？', pos=['tables:4'],
         slots=[slot('ordinary_fee', 'table_lookup', {'study_mode':'成人高校夜大','major_type':'一般专业'}, row='成人高校夜大 / 一般专业', column='收费标准', value=3200, unit='元/学年'),
                slot('special_fee', 'table_lookup', {'study_mode':'成人高校夜大','major_type':'特殊专业'}, row='成人高校夜大 / 特殊专业', column='收费标准', value=4800, unit='元/学年')],
         answer='成人高校夜大一般专业为3200元/学年，特殊专业为4800元/学年。',
         notes='两相邻行分别绑定金额；表格标题和收费范围不能丢。'),
]


# Six original suggestions plus fifteen new same-document chunks. Labels here are
# agent proposals; no matcher output was consulted.
NEGATIVES = {
    'P01': [('policy:7','NONE','其他类型推免生同样有3.0，但没有一般推免生专业前50%条件。','ORIGINAL')],
    'P02': [('policy:5','NONE','片段主要是特殊学术专长类的雅思6.0，缺一般推免生范围；开头有无范围的上一条尾句。','ADDED')],
    'P03': [('policy:4','NONE','同页学业条件与外语替代规则，不含导师合作例外。','ADDED')],
    'P04': [('policy:9','PARTIAL','仅含公示后递补，缺候补比例。','ORIGINAL')],
    'P05': [('policy:11','NONE','只说一般推免按GPA高低排序，没有同分的依次规则。','ADDED')],
    'P06': [('policy:12','NONE','同页其他规则与GPA有关，但没有9月6日录入边界。','ADDED')],
    'T01': [('technical:29','NONE','讨论密码技术作用与概念标题，未给云密码服务定义。','ADDED')],
    'T02': [('technical:35','NONE','同为云密码服务，但只讲密钥管理，未解释资源池单独部署原因。','ORIGINAL')],
    'T03': [('technical:34','NONE','章节引言只说云密码发展现状，没有密钥生成、存储、销毁及使用要求。','ADDED')],
    'T04': [('technical:41','NONE','介绍CASB用途，没有代理/API两种模式的技术本质。','ADDED')],
    'T05': [('technical:47','NONE','表2-1片段只出现IaaS代码，没有题目要求的三种模式及中文全称。','ADDED')],
    'A01': [('paper:21','NONE','模型概述谈迁移和编码，未陈述不同领域交互的研究假设。','ADDED')],
    'A02': [('paper:21','NONE','模型概述提及图神经网络与预训练模型，未绑定XSimGCL/BGE各自作用。','ORIGINAL')],
    'A03': [('paper:22','PARTIAL','说明双域图编码与辅助域文本编码，但未完整解释交互模式信息如何迁移并增强目标域推荐。','ADDED')],
    'A04': [('paper:40','NONE','同页表3为基线性能对比，不是有无语义模式增强的消融实验。','ADDED')],
    'A05': [('paper:40','PARTIAL','表3含Yelp2018的PEIDR Recall@20=0.0744，但没有表4无增强0.0729。','ADDED')],
    'F01': [('tables:5','NONE','相邻同页硕士收费行，没有食品工程目标行。','ORIGINAL')],
    'F02': [('tables:5','NONE','同类硕士其他专业收费，不含控制工程与食品工程两目标行。','ADDED')],
    'F03': [('tables:4','NONE','含全日制硕士类别，但该chunk截至国际商务，尚未出现MBA两行。','ORIGINAL')],
    'F04': [('tables:4','NONE','同页其他收费类别，无学术型博士系统科学目标行。','ADDED')],
    'F05': [('tables:5','NONE','同页研究生学费，未包含成人高校夜大两行。','ADDED')],
}


def cell(table: str, row: str, column: str, value: object, unit: str | None,
         scope: str) -> dict:
    return {'table': table, 'row': row, 'column': column, 'value': value,
            'unit': unit, 'scope': scope}


STRUCTURED_GOLD = {
    'A05': {
        'source_context':'CCL 2024 论文 PDF 第8页表4：消融实验结果',
        'cells':[
            cell('表4 消融实验结果','Yelp2018','Recall@20 / PEIDR(Ours)',0.0744,'无量纲','有行为语义模式增强'),
            cell('表4 消融实验结果','Yelp2018','Recall@20 / 无行为语义模式增强',0.0729,'无量纲','无行为语义模式增强'),
        ],
        'comparison':{'left_item':'PEIDR(Ours)','left_value':0.0744,
                      'right_item':'无行为语义模式增强','right_value':0.0729,
                      'derived_difference':None,'difference_requested':False},
    },
    'F01': {
        'source_context':'上海理工大学 2025–2026 学年教育收费 PDF 第3页',
        'cells':[cell('教育收费表','全日制专业学位硕士 / 食品工程','收费标准',12000,'元/学年','全日制专业学位硕士')],
    },
    'F02': {
        'source_context':'上海理工大学 2025–2026 学年教育收费 PDF 第3页',
        'cells':[
            cell('教育收费表','全日制专业学位硕士 / 控制工程','收费标准',18000,'元/学年','全日制专业学位硕士'),
            cell('教育收费表','全日制专业学位硕士 / 食品工程','收费标准',12000,'元/学年','全日制专业学位硕士'),
        ],
        'comparison':{'left_item':'控制工程','left_value':18000,'right_item':'食品工程',
                      'right_value':12000,'derived_difference':6000,'difference_unit':'元/学年',
                      'difference_requested':True},
    },
    'F03': {
        'source_context':'上海理工大学 2025–2026 学年教育收费 PDF 第3页',
        'cells':[
            cell('教育收费表','全日制专业学位硕士 / 工商管理(MBA)','收费标准',99000,'元/学年','全日制'),
            cell('教育收费表','非全日制硕士 / 工商管理(MBA)','收费标准',114000,'元/学年','非全日制'),
        ],
        'comparison':{'left_item':'全日制MBA','left_value':99000,'right_item':'非全日制MBA',
                      'right_value':114000,'derived_difference':15000,'difference_unit':'元/学年',
                      'difference_requested':False},
    },
    'F04': {
        'source_context':'上海理工大学 2025–2026 学年教育收费 PDF 第3页',
        'cells':[cell('教育收费表','全日制学术型博士 / 系统科学','收费标准',9000,'元/学年','全日制学术型博士')],
    },
    'F05': {
        'source_context':'上海理工大学 2025–2026 学年教育收费 PDF 第3页',
        'cells':[
            cell('教育收费表','成人高校夜大 / 一般专业','收费标准',3200,'元/学年','成人高校夜大'),
            cell('教育收费表','成人高校夜大 / 特殊专业','收费标准',4800,'元/学年','成人高校夜大'),
        ],
        'comparison':{'left_item':'夜大一般专业','left_value':3200,'right_item':'夜大特殊专业',
                      'right_value':4800,'derived_difference':1600,'difference_unit':'元/学年',
                      'difference_requested':False},
    },
    'T04': {
        'source_context':'云密码服务技术白皮书（2019）PDF 第71页 A.8 CASB 模式比较表',
        'cells':[
            cell('CASB 模式比较表','技术本质','CASB代理模式（串网关）',
                 '网关侧分析和代理应用请求；以适配方式增强数据安全与业务安全',None,'CASB数据加密服务'),
            cell('CASB 模式比较表','技术本质','CASB API模式之插件版',
                 '应用内识别用户数据操作；以配置方式增强数据安全',None,'CASB数据加密服务'),
        ],
        'comparison':{'left_item':'CASB代理模式','left_value':'网关侧分析和代理应用请求；适配增强',
                      'right_item':'CASB API模式','right_value':'应用内识别用户数据操作；配置增强',
                      'derived_difference':None,'difference_requested':False},
    },
}


POLARITY_GOLD = {
    'P03': {'queried_proposition':'本科学业指导教师与学生合作受“学历、职称明显高于本人者合作”限制',
            'expected_polarity':'NO','evidence_relation':'明确例外：不受该限制'},
    'P06': {'queried_proposition':'2024年9月6日当天补录成绩计入本细则GPA排名',
            'expected_polarity':'NO','evidence_relation':'9月6日（不含）之前录入；9月6日（含）之后不接受补录'},
}


def build_review() -> tuple[dict, dict]:
    manifest = json.loads((INTAKE/'source-manifest.json').read_text(encoding='utf-8'))
    source_by_slug = {s['slug']:s for s in manifest['sources']}
    chunks = {c['chunk_id']:c for c in json.loads((INTAKE/'candidate-chunks.json').read_text(encoding='utf-8'))['chunks']}
    rows = []
    negative_pairs = []
    for s in SPECS:
        source = source_by_slug[s['doc']]
        positives = s['pos']
        negatives = NEGATIVES.get(s['id'], [])
        if any(chunks[i]['document_id'] != source['sha256'] for i in positives):
            raise ValueError(f"Wrong positive document: {s['id']}")
        for chunk_id, label, reason, origin in negatives:
            if chunks[chunk_id]['document_id'] != source['sha256']:
                raise ValueError(f"Wrong negative document: {s['id']}/{chunk_id}")
            negative_pairs.append({'case_id':s['id'],'chunk_id':chunk_id,'answerability':label,
                                   'reason':reason,'candidate_origin':origin,'human_review_state':'PENDING'})
        rows.append({
            'case_id':s['id'], 'document_slug':s['doc'], 'document_id':source['sha256'],
            'document_sha256':source['sha256'], 'source_title':source['title'],
            'pdf_page':s['page'], 'page_preview_paths':[f'test-review-previews/{s["doc"]}-p{p}.png' for p in s['page']],
            'query':s['query'], 'query_rewrite_from':s.get('original'), 'query_type':s['type'],
            'parser_status':'PASS', 'parser_status_provisional':True,
            'required_facts':[required for required,_ in s['slots']],
            'positive_evidence_ids':positives,
            'hard_negative_evidence_ids':[n[0] for n in negatives],
            'answerability':'FULL', 'expected_facts':[expected for _,expected in s['slots']],
            'expected_answer':s['answer'], 'relation_status':s.get('relation','ENTAILS'),
            'risk_flags':[], 'review_notes':s['notes'],
            'structured_gold':STRUCTURED_GOLD.get(s['id']),
            'polarity_gold':POLARITY_GOLD.get(s['id']),
            'aggregation_category':'COMPOUND_SINGLE_CHUNK' if s['id']=='P04' else None,
            'parser_validation':{
                'checked_pdf_pages':s['page'], 'checked_chunks':positives,
                'proposed_result':'PASS',
                'basis':('PDF表格左侧跨行类别“全日制学术型博士研究生学费”与9000元/学年、系统科学同一行；'
                         'tables:5和tables:6均按此顺序保留，未靠已知答案反向补关系。'
                         if s['id']=='F04' else
                         'PDF目标事实与生产pypdf文本、400/60候选chunk逐项对照，关键事实暂可读。'),
                'human_confirmation_required':True,
            },
            'human_instruction':('用户附件 4c283b31：P04保留为普通COMPOUND，policy:8 FULL，policy:9 PARTIAL。'
                                 if s['id']=='P04' else None),
            'human_review_state':'PENDING', 'split':'TEST_CANDIDATE',
        })
    return ({'schema':'evidence-test-candidate-v1','state':'AGENT_PROPOSED_PENDING_HUMAN_REVIEW',
             'case_count':len(rows),'document_count':len({r['document_id'] for r in rows}),
             'test_frozen_count':0,'cases':rows},
            {'schema':'evidence-test-candidate-pairs-v1','chunks':chunks,
             'hard_negative_pairs':negative_pairs})


def review_markdown(review: dict, evidence: dict) -> str:
    lines = ['# 独立中文 Evidence TEST 候选逐题复核', '',
             '> 以下 query、答案、parser 状态和 evidence pair 是 agent 依据 PDF 页图及生产 pypdf/400-60 文本提出的草案；全部待真人签核。TEST_FROZEN=0；E0/E4 未运行。', '',
             f"共 {review['case_count']} 题、{review['document_count']} 份独立中文 PDF；{len(evidence['hard_negative_pairs'])} 个同文档真实 hard-negative pair（其中 {sum(p['candidate_origin']=='ADDED' for p in evidence['hard_negative_pairs'])} 个新增）。", '',
             '| ID | 页 | 状态 | 正例 | 负例 | 重点 |', '|---|---:|---|---|---|---|']
    for c in review['cases']:
        marker = '改写' if c['query_rewrite_from'] else '保留'
        lines.append(f"| {c['case_id']} | {','.join(map(str,c['pdf_page']))} | {marker}; parser {c['parser_status']} 待核 | {', '.join(c['positive_evidence_ids'])} | {', '.join(c['hard_negative_evidence_ids']) or '待补'} | {c['review_notes'].replace('|','/')} |")
    for c in review['cases']:
        preview_links = ', '.join('[第 {} 页](../test-review-previews/{}-p{}.png)'.format(p, c['document_slug'], p)
                                  for p in c['pdf_page'])
        lines += ['', f"## {c['case_id']} · {c['source_title']}", '',
                  f"- Query：{c['query']}",
                  f"- 原候选：{c['query_rewrite_from'] or '未改写'}",
                  f"- PDF 页：{c['pdf_page']}；页图：{preview_links}",
                  f"- 生产 parser/chunk：{', '.join(c['positive_evidence_ids'])}；parser_status 暂标 `{c['parser_status']}`",
                  f"- 暂拟 answerability：`{c['answerability']}`；关系：`{c['relation_status']}`",
                  f"- 暂拟回答：{c['expected_answer']}",
                  f"- 复核要点：{c['review_notes']}", '',
                  f"- parser 判据：{c['parser_validation']['basis']}",
                  f"- 能力类别：{c['aggregation_category'] or '常规证据匹配'}", '',
                  '**required_facts / expected_facts**', '', '```json',
                  json.dumps({'required_facts':c['required_facts'],'expected_facts':c['expected_facts']},ensure_ascii=False,indent=2),
                  '```', '']
        if c['structured_gold']:
            lines += ['**结构化表格 gold（待人审）**', '', '```json',
                      json.dumps(c['structured_gold'],ensure_ascii=False,indent=2), '```', '']
        if c['polarity_gold']:
            lines += ['**YES/NO 极性 gold（待人审）**', '', '```json',
                      json.dumps(c['polarity_gold'],ensure_ascii=False,indent=2), '```', '']
        lines += ['**正例原 chunk**', '']
        for id in c['positive_evidence_ids']:
            chunk=evidence['chunks'][id]
            lines += [f"### {id} · PDF 第 {chunk['page']} 页", '', '<pre>', chunk['text'].replace('&','&amp;').replace('<','&lt;'), '</pre>', '']
        if c['hard_negative_evidence_ids']:
            lines += ['**同文档 hard negative 候选**', '']
            for pair in evidence['hard_negative_pairs']:
                if pair['case_id'] != c['case_id']:
                    continue
                lines += [f"- `{pair['chunk_id']}`：暂标 `{pair['answerability']}`；{pair['reason']}",
                          f"  - 原文摘录：{evidence['chunks'][pair['chunk_id']]['text'][:180].replace(chr(10),' ')}"]
        lines += ['', '**人工复核：** `CONFIRM / CORRECT / EXCLUDE`；请核对页图、原文、query、parser、事实槽、正负例及答案。', '']
    return '\n'.join(lines)


def write_package(out: Path = OUT) -> dict:
    if out.exists():
        raise FileExistsError(f'Review package already exists: {out}')
    review,evidence=build_review()
    out.mkdir(parents=True)
    files={
        'test-candidate-review.json':json.dumps(review,ensure_ascii=False,indent=2),
        'case-evidence.json':json.dumps(evidence,ensure_ascii=False,indent=2),
        'review-sheet.md':review_markdown(review,evidence),
    }
    for name,content in files.items():
        (out/name).write_text(content,encoding='utf-8')
    # The original PDF text layer is preserved alongside the 400/60 chunks.
    from pypdf import PdfReader
    manifest=json.loads((INTAKE/'source-manifest.json').read_text(encoding='utf-8'))
    src={s['slug']:s for s in manifest['sources']}
    pages=[]
    for slug,page in sorted({(c['document_slug'],p) for c in review['cases'] for p in c['pdf_page']}):
        path=INTAKE/'sources'/src[slug]['file']
        text=(PdfReader(path).pages[page-1].extract_text() or '')
        pages.append({'document_slug':slug,'document_sha256':src[slug]['sha256'],
                      'pdf_page':page,'parser':'pypdf text layer via production parser dependency',
                      'raw_page_text':text,'raw_page_text_sha256':hashlib.sha256(text.encode()).hexdigest(),
                      'preview_path':f'../test-review-previews/{slug}-p{page}.png'})
    (out/'page-audit.json').write_text(json.dumps({'pages':pages},ensure_ascii=False,indent=2),encoding='utf-8')
    result={'state':'TEST_CANDIDATE_PENDING_HUMAN_REVIEW','test_frozen_count':0,
            'case_count':len(review['cases']),'document_count':review['document_count'],
            'hard_negative_pairs':len(evidence['hard_negative_pairs']),
            'files':{name:{'sha256':sha(out/name),'bytes':(out/name).stat().st_size}
                     for name in [*files,'page-audit.json']},
            'source_manifest_sha256':sha(INTAKE/'source-manifest.json'),
            'chunk_corpus_sha256':sha(INTAKE/'candidate-chunks.json'),
            'document_sha256':{s['slug']:sha(INTAKE/'sources'/s['file']) for s in manifest['sources']}}
    (out/'review-manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    print(json.dumps(write_package(),ensure_ascii=False,indent=2))
