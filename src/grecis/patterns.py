from __future__ import annotations

import re
from typing import Any

PATTERN_METADATA: dict[str, dict[str, Any]] = {
    "concession": {
        "label": "让步",
        "function": "先承认限制、例外或对方观点，再推进作者真正要强调的结论。",
        "reading_tip": "让步成分通常不是作者落点，重点看主句或转折后的判断。",
        "priority": 10,
    },
    "contrast": {
        "label": "转折与对比",
        "function": "并置不同事实、观点或预期，突出差异以及作者的论证重心。",
        "reading_tip": "重点标记转折词前后的评价方向变化。",
        "priority": 10,
    },
    "causality": {
        "label": "因果与结果",
        "function": "连接原因、机制、结果或解释，是定位论证链条的核心结构。",
        "reading_tip": "区分事实上的原因、作者给出的解释和仅仅相关的现象。",
        "priority": 10,
    },
    "condition": {
        "label": "条件与限定",
        "function": "限定结论成立的前提、范围或例外。",
        "reading_tip": "不要脱离条件词概括作者结论，尤其注意 unless 和 only if。",
        "priority": 9,
    },
    "stance": {
        "label": "作者态度与观点",
        "function": "标示作者、研究者或被引述者对命题的判断和立场。",
        "reading_tip": "先确认观点归属，再判断作者是赞同、保留还是反驳。",
        "priority": 9,
    },
    "hedging": {
        "label": "模糊限制与审慎表达",
        "function": "降低断言强度，表达概率、趋势、证据边界或不确定性。",
        "reading_tip": "may、could、appear 等词会显著改变命题强度，不能漏译。",
        "priority": 9,
    },
    "emphasis": {
        "label": "强调与焦点",
        "function": "通过强调句、否定转移或焦点结构突出真正的信息中心。",
        "reading_tip": "先还原普通语序，再确认被强调的成分。",
        "priority": 8,
    },
    "comparison": {
        "label": "比较与取舍",
        "function": "通过比较、排除或程度变化建立评价标准。",
        "reading_tip": "注意比较对象是否对称，以及 rather than 等结构的取舍方向。",
        "priority": 8,
    },
    "inversion": {
        "label": "倒装结构",
        "function": "因否定前置、条件省略或修辞强调改变正常语序。",
        "reading_tip": "先恢复主语和谓语的正常位置，再处理否定或条件关系。",
        "priority": 8,
    },
    "cleft": {
        "label": "强调句与分裂句",
        "function": "使用 it is/was ... that 或 what ... is ... 突出句子焦点。",
        "reading_tip": "去掉强调框架后检查剩余成分是否仍构成完整命题。",
        "priority": 8,
    },
    "relative_clause": {
        "label": "定语从句与补充说明",
        "function": "用从句限定名词或补充背景、原因和评价。",
        "reading_tip": "先找关系词指代对象，再判断从句是必要限定还是补充信息。",
        "priority": 7,
    },
    "participial_clause": {
        "label": "分词与非谓语结构",
        "function": "压缩时间、原因、条件、伴随或结果信息。",
        "reading_tip": "补出分词结构的逻辑主语，并判断它与主句的语义关系。",
        "priority": 7,
    },
    "nominal_clause": {
        "label": "名词性从句",
        "function": "用 what、whether、that 等从句充当主语、宾语或同位语。",
        "reading_tip": "把整个从句视作一个名词成分，再确定它在主句中的位置。",
        "priority": 7,
    },
    "argument_development": {
        "label": "论证推进",
        "function": "通过举例、证据、反方观点、问题—方案或由个别到一般推进论证。",
        "reading_tip": "判断当前句是在提出观点、提供证据、回应反方还是得出结论。",
        "priority": 8,
    },
    "other": {
        "label": "其他修辞结构",
        "function": "尚未归入稳定分类的修辞或句法结构。",
        "reading_tip": "结合上下文判断该结构对作者论证方向的作用。",
        "priority": 1,
    },
}


def normalize_sentence_pattern_type(value: str, function: str = "") -> str:
    raw = _normalize_type_text(value)
    context = f"{raw} {_normalize_type_text(function)}"

    direct_aliases = {
        "author attitude": "stance",
        "author attitude expression": "stance",
        "stance marker": "stance",
        "stance markers": "stance",
        "hedging expression": "hedging",
        "hedging expressions": "hedging",
        "argument development pattern": "argument_development",
        "argument development patterns": "argument_development",
        "concession structure": "concession",
        "contrast structure": "contrast",
        "causality structure": "causality",
    }
    if raw in PATTERN_METADATA:
        return raw
    if raw in direct_aliases:
        return direct_aliases[raw]

    keyword_groups = (
        ("inversion", ("inversion", "inverted")),
        ("cleft", ("cleft", "it is that", "it was that")),
        ("relative_clause", ("relative clause", "attributive clause")),
        ("participial_clause", ("participial", "participle", "non finite")),
        ("nominal_clause", ("nominal clause", "noun clause", "subject clause")),
        ("condition", ("condition", "conditional", "unless", "provided that")),
        ("concession", ("concession", "concessive")),
        ("contrast", ("contrast", "comparison and contrast")),
        ("causality", ("causality", "causal", "cause effect", "cause and effect")),
        ("hedging", ("hedg", "qualification", "tentative")),
        ("stance", ("stance", "author attitude", "attitude expression")),
        ("emphasis", ("emphasis", "emphatic", "focus structure")),
        ("comparison", ("comparison", "comparative", "preference")),
        (
            "argument_development",
            (
                "argument development",
                "problem solution",
                "claim evidence",
                "counterargument",
                "counter argument",
                "example evidence",
                "rhetorical question",
                "analogy",
            ),
        ),
    )
    for canonical, keywords in keyword_groups:
        if any(keyword in context for keyword in keywords):
            return canonical
    return "other"


def pattern_metadata(pattern_type: str) -> dict[str, Any]:
    canonical = normalize_sentence_pattern_type(pattern_type)
    return PATTERN_METADATA.get(canonical, PATTERN_METADATA["other"])


def infer_sentence_pattern_template(
    sentence: str,
    pattern_type: str,
    *,
    provided_template: str = "",
) -> str:
    if provided_template.strip():
        return _clean_template(provided_template)

    canonical = normalize_sentence_pattern_type(pattern_type)
    lowered = " ".join(sentence.lower().split())
    candidates = TEMPLATE_CUES.get(canonical, ())
    for label, pattern in candidates:
        if re.search(pattern, lowered, re.IGNORECASE):
            return label
    return pattern_metadata(canonical)["label"]


def sentence_example_quality(sentence: str, template: str = "", source: str = "") -> float:
    text = " ".join(str(sentence).split())
    if not text:
        return -100.0

    length = len(text)
    word_count = len(re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)?", text))
    score = 0.0
    if 70 <= length <= 240:
        score += 4.0
    elif 45 <= length <= 320:
        score += 2.0
    else:
        score -= min(abs(length - 150) / 80, 4.0)

    if 14 <= word_count <= 42:
        score += 3.0
    elif 9 <= word_count <= 55:
        score += 1.0
    else:
        score -= 1.5

    if text[-1:] in {".", "!", "?", '"', "”", "’"}:
        score += 0.5
    if template and template.lower() in text.lower():
        score += 0.8
    if source.lower() in {"pastpapers.cn", "kaoyan_exam"}:
        score += 1.5
    if re.search(r"subscribe|sign up|newsletter|all rights reserved", text, re.IGNORECASE):
        score -= 6.0
    if length > 420:
        score -= 5.0
    return round(score, 3)


def pattern_priority(pattern_type: str) -> int:
    return int(pattern_metadata(pattern_type)["priority"])


def _normalize_type_text(value: str) -> str:
    text = str(value or "").strip().lower().replace("_", " ").replace("-", " ")
    text = re.sub(r"[^a-z0-9/ +]+", " ", text)
    return " ".join(text.split())


def _clean_template(value: str) -> str:
    text = " ".join(str(value).split())
    text = re.sub(r"^[Tt]emplate\s*:\s*", "", text)
    return text[:120] or "未命名结构"


TEMPLATE_CUES: dict[str, tuple[tuple[str, str], ...]] = {
    "concession": (
        ("even though ...", r"\beven though\b"),
        ("although / though ...", r"\b(?:although|though)\b"),
        ("despite / in spite of ...", r"\b(?:despite|in spite of)\b"),
        ("admittedly / granted ...", r"\b(?:admittedly|granted)\b"),
    ),
    "contrast": (
        ("however / nevertheless ...", r"\b(?:however|nevertheless|nonetheless)\b"),
        ("while / whereas ...", r"\b(?:while|whereas)\b"),
        ("rather than ...", r"\brather than\b"),
        ("instead / instead of ...", r"\binstead(?: of)?\b"),
        ("by contrast / on the other hand ...", r"\b(?:by contrast|on the other hand)\b"),
        ("..., but ...", r"\bbut\b"),
    ),
    "causality": (
        ("because / since ...", r"\b(?:because|since)\b"),
        ("because of / due to ...", r"\b(?:because of|due to|owing to)\b"),
        ("therefore / thus / hence ...", r"\b(?:therefore|thus|hence|consequently)\b"),
        ("lead to / result in ...", r"\b(?:lead(?:s|ing)? to|led to|result(?:s|ed|ing)? in)\b"),
        ("account for ...", r"\baccount(?:s|ed|ing)? for\b"),
        ("so ... that ...", r"\bso\b.+\bthat\b"),
    ),
    "condition": (
        ("if ...", r"\bif\b"),
        ("unless ...", r"\bunless\b"),
        ("provided / providing that ...", r"\bprovid(?:ed|ing) that\b"),
        ("only if / as long as ...", r"\b(?:only if|as long as)\b"),
        ("whether ... or ...", r"\bwhether\b.+\bor\b"),
    ),
    "stance": (
        ("argue / claim that ...", r"\b(?:argue|argues|argued|claim|claims|claimed) that\b"),
        (
            "suggest / indicate that ...",
            r"\b(?:suggest|suggests|suggested|indicate|indicates|indicated) that\b",
        ),
        ("according to ...", r"\baccording to\b"),
        (
            "the author/researchers believe ...",
            r"\b(?:believe|believes|believed|maintain|maintains) that\b",
        ),
    ),
    "hedging": (
        ("may / might / could ...", r"\b(?:may|might|could)\b"),
        ("appear / seem to ...", r"\b(?:appear|appears|appeared|seem|seems|seemed) to\b"),
        ("be likely / unlikely to ...", r"\b(?:likely|unlikely) to\b"),
        ("tend to / in general ...", r"\b(?:tend(?:s|ed)? to|in general|typically|often)\b"),
    ),
    "emphasis": (
        ("not only ... but also ...", r"\bnot only\b.+\bbut also\b"),
        ("not so much A as B", r"\bnot so much\b.+\bas\b"),
        ("what matters/is important is ...", r"\bwhat (?:matters|is important) is\b"),
        ("the point/fact is that ...", r"\bthe (?:point|fact) is that\b"),
    ),
    "comparison": (
        ("more/less ... than ...", r"\b(?:more|less)\b.+\bthan\b"),
        ("as ... as ...", r"\bas\b.+\bas\b"),
        ("the more ... the more ...", r"\bthe (?:more|less)\b.+\bthe (?:more|less)\b"),
        ("rather than ...", r"\brather than\b"),
    ),
    "inversion": (
        (
            "not only + auxiliary + subject ...",
            r"^\s*not only\s+"
            r"(?:do|does|did|is|are|was|were|has|have|had|can|could|will|would)",
        ),
        (
            "never/rarely/little + auxiliary + subject ...",
            r"^\s*(?:never|rarely|seldom|little|hardly)\s+"
            r"(?:do|does|did|is|are|was|were|has|have|had|can|could|will|would)",
        ),
        ("had/were/should + subject ...", r"^\s*(?:had|were|should)\s+\w+"),
    ),
    "cleft": (
        (
            "it is/was ... that/who ...",
            r"\bit (?:is|was)\s+(?:only |not |precisely |exactly )?"
            r"(?:the |a |an |in |on |at |by |because |when |after |before |through |from )"
            r".{1,100}\b(?:that|who)\b",
        ),
        (
            "what ... is/was ...",
            r"^\s*what\s+(?:[a-z'-]+\s+){0,5}(?:is|was)\b",
        ),
    ),
    "relative_clause": (
        ("noun, which/who/whose ...", r",\s*(?:which|who|whose)\b"),
        ("noun that/which/who ...", r"\b(?:that|which|who|whose)\b"),
    ),
    "participial_clause": (
        (
            "V-ing/V-ed ..., main clause",
            r"^\s*(?:having|being|given|considering|compared|based|faced|assuming)\b.+,",
        ),
        (
            "..., V-ing/V-ed ...",
            r",\s*(?:using|making|leading|reflecting|resulting|allowing|requiring|"
            r"creating|providing|leaving|suggesting|indicating|raising|reducing|"
            r"increasing|including|based|compared|given|faced|driven|combined|"
            r"viewed|considered|known)\b",
        ),
    ),
    "nominal_clause": (
        (
            "what ... + predicate",
            r"^\s*what\s+(?:[a-z'-]+\s+){0,5}"
            r"(?:is|was|matters|counts|causes|drives|makes|remains|seems)\b",
        ),
        ("the fact/idea/claim that ...", r"\bthe (?:fact|idea|claim|assumption|evidence) that\b"),
    ),
    "argument_development": (
        ("for example / for instance ...", r"\b(?:for example|for instance)\b"),
        (
            "evidence/data show ...",
            r"\b(?:evidence|data|findings|research) "
            r"(?:show|shows|suggest|suggests|indicate|indicates)\b",
        ),
        ("problem → solution", r"\b(?:solution|address|solve|remedy)\b"),
        (
            "counterargument → response",
            r"\b(?:critics|opponents|supporters) (?:argue|claim|say)\b",
        ),
        ("rhetorical question", r"\?$"),
    ),
}
