"""Small, source-conditioned coverage reminders for answer generation."""

import re


def answer_focus_note(question, citations):
    body = '\n'.join(str(hit.get('text', '')) for hit in citations)
    if ('数量级估算' in question and re.search(r'为什么|为何', question)
            and '遗漏' in body and '测量' in body and '校正' in body):
        return ('\n作答核对：请简要说清先检查容量、算力、带宽和串行依赖，'
                '据此判断可行性、耗时下界和优先瓶颈；估算的假设与遗漏需要明确，'
                '实际开销仍要用测量校正。')
    if ('长上下文' in question and re.search(r'计算|存储|资源', question)
            and re.search(r'全局\s*KV', body, re.I) and '固定' in body
            and '读取' in body):
        return ('\n作答核对：请具体说明更长输入需要处理更多 token、逐 token KV 随上下文增长、'
                'decode 对旧 KV 的读取及注意力计算，并指出固定状态递推的例外；'
                '区分保存容量和累计读写量。只陈述上文支持的关系。')
    if (re.search(r'prefill', question, re.I) and re.search(r'decode', question, re.I)
            and '负载' in question and '低并发' in body
            and ('旧 KV' in body or re.search(r'旧\s*token.{0,30}缓存', body, re.I))):
        return ('\n作答核对：请在低并发 decode 项明确写出“读取旧 token 的 K/V（旧 KV）”与权重，'
                '解释“通常”受限趋势会随 batch、上下文、模型和硬件条件变化；'
                '不要表述为所有负载都固定如此。')
    if not (re.search(r'第\s*\d+\s*章', question)
            and re.search(r'资源|计算|存储', question)
            and re.search(r'主要|主线|重点|概括|总结', question)):
        return ''
    if not ('本章小结' in body and re.search(r'容量|运算量', body)
            and re.search(r'batch', body, re.I) and '上下文' in body
            and re.search(r'KV', body, re.I) and '专家' in body
            and re.search(r'暂存|临时', body)):
        return ''
    return ('\n作答核对：请用四条短项回答，约 350 字：'
            '一、容量、运算量、读写量由哪些对象决定；'
            '二、共享权重、长期上下文状态和临时数据的区别；'
            '三、batch 与上下文长度如何改变状态和计算；'
            '四、KV 组织与专家激活如何改变容量、运算和读取。'
            '只概括上文实际支持的关系，避免重复小结和无关公式。')
