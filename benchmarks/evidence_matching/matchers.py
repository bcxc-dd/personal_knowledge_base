"""Isolated E1-E4 evidence assessors. Never reads gold labels or facts.

These deliberately small, auditable Chinese-domain rules are a benchmark probe,
not a drop-in production replacement or a general natural-language entailment model.
"""
from __future__ import annotations

import re
import unicodedata

from app.evidence import assess_evidence
from app.query_plan import build_query_plan

LABEL = {"supported": "SUPPORTED", "partial": "PARTIAL", "insufficient": "NOT_SUPPORTED"}


def citation(case):
    source = case["evidence_metadata"]
    return {"chunk_id": case["case_id"],
            "document_id": source[0]["chunk_id"].split(":")[0] if source else "controlled",
            "name": "2027届本科毕业生推免工作细则.pdf" if source and source[0]["document_key"] == "promotion"
                    else "AI-Infra-Book.pdf" if source else "受控对照片段",
            "text": case["evidence_text"]}


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).replace("\r", "\n")
    value = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def compact(value: str) -> str:
    return re.sub(r"\s+", "", normalize(value)).lower()


def result(label: str, reason: str, matched=(), missing=(), constraints=()):
    return {"predicted_label": label, "reason": reason,
            "matched": list(matched), "missing": list(missing),
            "constraints": list(constraints)}


def _base(case, normalized=False):
    question = normalize(case["query"]) if normalized else case["query"]
    source = citation(case)
    if normalized:
        source["text"] = normalize(source["text"])
    plan = build_query_plan(question) if normalized else build_query_plan(case["query"])
    assessment = assess_evidence(question, [source], plan)
    return result(LABEL[assessment.status], "PRODUCTION_ASSESSMENT" if not normalized else "NORMALIZED_PRODUCTION_ASSESSMENT",
                  assessment.supported_subquestions, assessment.unsupported_subquestions)


def _metric_relation(question, text, aliases=False, strict=False):
    """Require the course GPA metric, threshold direction and scope in one clause."""
    if not ("绩点" in question and ("门槛" in question or "至少" in question or "豁免" in question)):
        return None
    body = compact(text)
    # NFKC has already converted the PDF's visual typography; only verified
    # course/课程 variants are accepted, never an unrelated numeric metric.
    metric = re.search(r"必修课(?:程)?(?:的)?平均学分绩点", body)
    if not metric or re.search(r"(?:绩点排名|绩点名次).{0,12}要求", body):
        return result("NOT_SUPPORTED", "METRIC_SCOPE_MISSING", missing=("必修课平均学分绩点",))
    tail = body[metric.end():metric.end() + 35]
    relation = re.search(r"(大于等于|不低于|不少于|至少|达到|≥|>=|低于|小于|<)\s*(\d+(?:\.\d+)?)", tail)
    if not relation:
        return result("NOT_SUPPORTED", "METRIC_NUMERIC_RELATION_MISSING", missing=("门槛方向和数值",))
    op, value = relation.groups()
    if strict and op in {"低于", "小于", "<"} and re.search(r"至少|不低于|≥", question):
        return result("NOT_SUPPORTED", "CONTRADICTORY_OPERATOR", constraints=(f"{op}{value}",))
    if strict and (re.search(r"创新班专项.{0,24}平均学分绩点", body)
                   and re.search(r"普通推免.{0,12}另行规定", body)):
        return result("NOT_SUPPORTED", "SCOPE_EXCEPTION", constraints=("创新班专项≠普通推免",))
    if strict and re.search(r"(?:是否|能否)豁免", question) and "豁免" not in body:
        return result("PARTIAL", "THRESHOLD_ONLY_EXEMPTION_MISSING", matched=(f"平均学分绩点{op}{value}",), missing=("豁免事实",))
    aliases_used = ("必修课→必修课程",) if "必修课平均" in question and "必修课程" in body else ()
    return result("SUPPORTED", "METRIC_OPERATOR_VALUE_SCOPE", matched=("必修课平均学分绩点", *aliases_used), constraints=(f"{op}{value}",))


def _team(question, text, aliases=False, strict=False):
    if "团队" not in question or not re.search(r"扣减|扣除|计分|分值", question):
        return None
    body = compact(text)
    if re.search(r"所有团队成员.*完整分值", question):
        if re.search(r"除.*外|其余.*扣减", body):
            return result("NOT_SUPPORTED", "UNIVERSAL_CLAIM_CONTRADICTED", constraints=("除…外",))
    if not re.search(r"团队成员|以团队参赛", body):
        return result("NOT_SUPPORTED", "TEAM_SCOPE_MISSING")
    decrement = bool(re.search(r"扣减|扣除|扣分", body) or aliases and "减去" in body)
    if not decrement:
        return result("NOT_SUPPORTED", "DECREMENT_ACTION_MISSING", missing=("扣减/减去",))
    explicit = re.search(r"(0\.\d+)\s*[\*×]?\s*[（(]?团队排名\s*-\s*1", body)
    if strict and re.search(r"0\.\d+", question):
        wanted = re.search(r"0\.\d+", question).group()
        if not explicit or explicit.group(1) != wanted:
            return result("NOT_SUPPORTED", "TEAM_FACTOR_MISMATCH", constraints=(f"question={wanted}", f"evidence={explicit.group(1) if explicit else 'missing'}"))
    if strict and not explicit:
        return result("NOT_SUPPORTED", "TEAM_FORMULA_MISSING", missing=("扣减系数及排名式",))
    floor = bool(re.search(r"最低(?:为)?0分", body))
    if strict and not floor:
        return result("PARTIAL", "TEAM_FLOOR_MISSING", matched=("团队扣减式",), missing=("最低0分",))
    alias_used = ("扣减/扣除→减去",) if aliases and "减去" in body and not re.search(r"扣减|扣除|扣分", body) else ()
    return result("SUPPORTED", "TEAM_DECREMENT_RULE", matched=("团队成员", "扣减动作", *alias_used),
                  constraints=(explicit.group(0), "最低0分") if explicit and floor else ())


def _numeric_condition(question, text):
    if "CSP" not in question.upper() or not re.search(r"g[_ ]?i|计分", question, re.I):
        return None
    body = compact(text)
    asked = re.search(r"(\d{2,4})\s*分", question)
    threshold = asked.group(1) if asked else None
    if not threshold:
        return None
    # Allow either prose or a PDF formula branch; conditions must match the asked number.
    condition = bool(re.search(rf"(?:x_i>=|达到){threshold}(?:分)?", body))
    wrong_condition = re.search(r"(?:x_i>=|达到)(\d{2,4})(?:分)?", body)
    if not condition:
        return result("NOT_SUPPORTED", "NUMERIC_CONDITION_MISMATCH", missing=(f"成绩≥{threshold}",),
                      constraints=(f"source={wrong_condition.group(1)}" if wrong_condition else "source=missing",))
    output = bool(re.search(r"g_i\s*(?:=|计分为)\s*0\.\d+", body)
                  or re.search(r"g_i\s*=\s*0\.\d+[,，].{0,20}x_i>=", body))
    return result("SUPPORTED" if output else "PARTIAL", "CONDITION_AND_OUTPUT" if output else "OUTPUT_MISSING",
                  matched=(f"成绩≥{threshold}",), missing=() if output else ("g_i分值",))


def _comparison(question, text):
    body = compact(text)
    if "GQA" in question.upper() and "MQA" in question.upper():
        # Bound relation to the entity's local clause, avoiding swapped attribution.
        mqa = bool(re.search(r"mqa.{0,15}(?:所有|全部).{0,8}q.{0,15}(?:共用|共享).{0,8}(?:一组|1组)", body))
        gqa = bool(re.search(r"gqa.{0,25}(?:分组|每组).{0,15}(?:共享|共用).{0,8}(?:一组|1组)", body))
        swapped = bool(re.search(r"gqa.{0,10}所有.{0,8}q.{0,10}共用", body)
                       or re.search(r"mqa.{0,15}按组共享", body))
        if swapped:
            return result("NOT_SUPPORTED", "RELATION_SWAPPED", constraints=("GQA/MQA共享范围颠倒",))
        return result("SUPPORTED" if mqa and gqa else "PARTIAL" if mqa or gqa else "NOT_SUPPORTED",
                      "BOTH_SHARING_RELATIONS" if mqa and gqa else "ONE_SHARING_RELATION" if mqa or gqa else "SHARING_RELATIONS_MISSING",
                      matched=tuple(k for k, v in (("MQA所有Q共享一组KV", mqa), ("GQA分组共享KV", gqa)) if v),
                      missing=tuple(k for k, v in (("MQA共享范围", mqa), ("GQA共享范围", gqa)) if not v))
    if "预填充" in question and "解码" in question:
        prefill = bool(re.search(r"处理输入.{0,15}预填充|预填充.{0,15}处理输入", body))
        decode = bool(re.search(r"逐步生成.{0,15}解码|解码.{0,15}逐步生成", body))
        return result("SUPPORTED" if prefill and decode else "PARTIAL" if prefill or decode else "NOT_SUPPORTED",
                      "BOTH_PHASES" if prefill and decode else "ONE_PHASE" if prefill or decode else "PHASES_MISSING",
                      matched=tuple(k for k, v in (("预填充处理输入", prefill), ("解码逐步生成", decode)) if v))
    return None


def _definition(question, text):
    if "AI Infra" not in question:
        return None
    body = compact(text)
    definition = bool(re.search(r"aiinfra是.{0,15}支撑ai训练和推理的基础设施", body))
    parts = bool(re.search(r"计算设备.{0,8}存储.{0,8}互联", body)
                 and re.search(r"(?:组织.{0,12}资源的软件|软件)", body))
    return result("SUPPORTED" if definition and parts else "PARTIAL" if definition or parts else "NOT_SUPPORTED",
                  "DEFINITION_AND_COMPONENTS" if definition and parts else "ONE_DEFINITION_FACT" if definition or parts else "TOPIC_ONLY",
                  matched=tuple(k for k, v in (("定义", definition), ("组成", parts)) if v))


def _table(question, text):
    if "竞赛等级" not in question or "第二等次" not in question:
        return None
    body = normalize(text)
    # A same-row capture is essential. NFKC maps Ⅱ to II; allow both.
    row = re.search(r"(?:Ⅱ|II)\s*级甲等\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)", body, re.I)
    if not row:
        return result("NOT_SUPPORTED", "TARGET_TABLE_ROW_MISSING", missing=("Ⅱ级甲等行",))
    return result("SUPPORTED", "TARGET_ROW_SECOND_COLUMN", matched=("Ⅱ级甲等", "第二等次"), constraints=(f"value={row.group(2)}",))


def _award(question, text):
    if "竞赛获奖成绩" not in question or "累加" not in question:
        return None
    body = compact(text)
    highest = "最高一项" in body
    no_sum = "不累加" in body
    if re.search(r"可以累加|均计分", body):
        return result("NOT_SUPPORTED", "CONTRADICTORY_ACCUMULATION")
    return result("SUPPORTED" if highest and no_sum else "PARTIAL" if highest or no_sum else "NOT_SUPPORTED",
                  "HIGHEST_AND_NO_ACCUMULATION" if highest and no_sum else "AWARD_CONSTRAINT_INCOMPLETE")


def evaluate(case, variant: str):
    if variant == "E0":
        return _base(case)
    if variant not in {"E1", "E2", "E3", "E4"}:
        raise ValueError(variant)
    basic = _base(case, normalized=True)
    if variant == "E1":
        return basic
    question, source = normalize(case["query"]), normalize(case["evidence_text"])
    metric = _metric_relation(question, source, aliases=variant in {"E3", "E4"}, strict=variant == "E4")
    if metric is not None:
        return metric
    if variant == "E2":
        # E2 tightens broad single-keyword support and adds core metric-subphrase coverage.
        if basic["predicted_label"] == "SUPPORTED" and not re.search(r"(?:是|包括|对应|计分|分值|共享|共用|处理|生成|扣|减去|不累加)", source):
            return result("NOT_SUPPORTED", "RELATION_WORD_MISSING")
        return basic
    team = _team(question, source, aliases=True, strict=variant == "E4")
    if team is not None:
        return team
    if variant == "E3":
        return basic
    for assessor in (_numeric_condition, _comparison, _definition, _table, _award):
        found = assessor(question, source)
        if found is not None:
            return found
    return basic
