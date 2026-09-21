"""French conjugation tables + a reverse index of every conjugated form.

Two jobs, one source of truth:

1. ``tables(inf)``  → the full conjugation of a verb, grouped by tense, shaped as
   ``{"label": [zh, fr], "rows": [[pronoun, form, ipa], ...]}`` so the renderer can
   drop it straight into an HTML table.
2. ``find_form(token)`` → for *any* surface form ("fais", "faites", "soient",
   "apprendrais"), what verb/tense/person it is. This is what makes the words
   inside the grammar explanations clickable: a reader who meets "font" in a
   lesson body can tap it and get "faire · 现在时 · 第3人称复数" plus the table.

Regular -er verbs are generated (spelling is 100% rule-based in French); the
irregulars French actually cares about are spelled out by hand. IPA is authored
where it is genuinely non-obvious and left blank elsewhere — the UI always offers
a 🔊 button, so a blank IPA cell never leaves the reader stuck.
"""
from __future__ import annotations

TENSE_ORDER = [
    "present", "imparfait", "futur", "conditionnel", "subjonctif", "passe_compose",
]

TENSE_LABEL: dict[str, tuple[str, str]] = {
    "present": ("现在时", "Présent"),
    "imparfait": ("未完成过去时", "Imparfait"),
    "futur": ("简单将来时", "Futur simple"),
    "conditionnel": ("条件式现在时", "Conditionnel présent"),
    "subjonctif": ("虚拟式现在时", "Subjonctif présent"),
    "passe_compose": ("复合过去时", "Passé composé"),
}

# Short tab captions for the tooltip's tense switcher.
TENSE_TAB: dict[str, str] = {
    "present": "现在",
    "imparfait": "未完成",
    "futur": "将来",
    "conditionnel": "条件",
    "subjonctif": "虚拟",
    "passe_compose": "复合过去",
}

PERSON_LABEL = [
    "第1人称单数", "第2人称单数", "第3人称单数",
    "第1人称复数", "第2人称复数", "第3人称复数",
]

_PRON = ["je", "tu", "il/elle", "nous", "vous", "ils/elles"]
_PRON_QUE = ["que je", "que tu", "qu'il/elle", "que nous", "que vous", "qu'ils/elles"]
VOWELS = set("aeiouâàéèêëîïôûùüœæh")


def _rows(spec: str) -> list[list[str]]:
    """Parse 'je|suis|/ʒə sɥi/; tu|es|/ty ɛ/' into [['je','suis','/ʒə sɥi/'], ...]."""
    out: list[list[str]] = []
    for chunk in spec.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split("|")]
        while len(parts) < 3:
            parts.append("")
        out.append(parts[:3])
    return out


# ── Irregular verbs, spelled out ──────────────────────────────────────────
# aux="être" verbs agree with the subject in gender/number — the participle is
# written with "(e)" so the table itself carries the reminder.

_IRREGULAR: dict[str, dict] = {
    "être": dict(
        group=3, mean="是（法语最不规则的动词）", inf_ipa="/ɛtʁ/",
        pp="été", pp_ipa="/e.te/", aux="avoir",
        note="虚拟式最不规则，连着 que 一起背：que je sois。",
        present=_rows("je|suis|/ʒə sɥi/; tu|es|/ty ɛ/; il|est|/i.lɛ/; nous|sommes|/nu sɔm/; vous|êtes|/vu.z‿ɛt/; ils|sont|/il sɔ̃/"),
        imparfait=_rows("je|étais|/ʒe.tɛ/; tu|étais|/ty e.tɛ/; il|était|/i.le.tɛ/; nous|étions|/nu.z‿e.tjɔ̃/; vous|étiez|/vu.z‿e.tje/; ils|étaient|/il.z‿e.tɛ/"),
        futur=_rows("je|serai|; tu|seras|; il|sera|; nous|serons|; vous|serez|; ils|seront|"),
        conditionnel=_rows("je|serais|; tu|serais|; il|serait|; nous|serions|; vous|seriez|; ils|seraient|"),
        subjonctif=_rows("que je|sois|/sjwa/; que tu|sois|/ty swa/; qu'il|soit|/il swa/; que nous|soyons|/nu swa.jɔ̃/; que vous|soyez|/vu swa.je/; qu'ils|soient|/il swa/"),
    ),
    "avoir": dict(
        group=3, mean="有（复合过去时的头号助动词）", inf_ipa="/a.vwaʁ/",
        pp="eu", pp_ipa="/y/", aux="avoir",
        note="绝大多数动词的复合过去时都用 avoir 当助动词。",
        present=_rows("je|ai|/ʒe/; tu|as|/ty a/; il|a|/il a/; nous|avons|/nu.z‿a.vɔ̃/; vous|avez|/vu.z‿a.ve/; ils|ont|/il.z‿ɔ̃/"),
        imparfait=_rows("je|avais|/ʒa.vɛ/; tu|avais|/ty a.vɛ/; il|avait|/i.la.vɛ/; nous|avions|/nu.z‿a.vjɔ̃/; vous|aviez|/vu.z‿a.vje/; ils|avaient|/il.z‿a.vɛ/"),
        futur=_rows("je|aurai|/ʒo.ʁe/; tu|auras|/ty o.ʁa/; il|aura|/i.lo.ʁa/; nous|aurons|/nu.z‿o.ʁɔ̃/; vous|aurez|/vu.z‿o.ʁe/; ils|auront|/il.z‿o.ʁɔ̃/"),
        conditionnel=_rows("je|aurais|/ʒo.ʁɛ/; tu|aurais|; il|aurait|; nous|aurions|; vous|auriez|; ils|auraient|"),
        subjonctif=_rows("que je|aie|/ʒɛ/; que tu|aies|/ty ɛ/; qu'il|ait|/il ɛ/; que nous|ayons|/nu.z‿ɛ.jɔ̃/; que vous|ayez|/vu.z‿ɛ.je/; qu'ils|aient|/il.z‿ɛ/"),
    ),
    "aller": dict(
        group=3, mean="去（以 -er 结尾却不规则）", inf_ipa="/a.le/",
        pp="allé(e)", pp_ipa="/a.le/", aux="être",
        note="aller 是极少数用 être 当助动词的常用动词，过去分词要与主语性数配合，阴性加 -e：je suis allé（阴性 je suis allée）。",
        present=_rows("je|vais|/ʒə vɛ/; tu|vas|/ty va/; il|va|/il va/; nous|allons|/nu.z‿a.lɔ̃/; vous|allez|/vu.z‿a.le/; ils|vont|/il vɔ̃/"),
        imparfait=_rows("je|allais|/ʒa.lɛ/; tu|allais|; il|allait|/i.la.lɛ/; nous|allions|/nu.z‿a.ljɔ̃/; vous|alliez|/vu.z‿a.lje/; ils|allaient|/il.z‿a.lɛ/"),
        futur=_rows("je|irai|/ʒi.ʁe/; tu|iras|/ty i.ʁa/; il|ira|/i.li.ʁa/; nous|irons|/nu.z‿i.ʁɔ̃/; vous|irez|/vu.z‿i.ʁe/; ils|iront|/il.z‿i.ʁɔ̃/"),
        conditionnel=_rows("je|irais|/ʒi.ʁɛ/; tu|irais|; il|irait|; nous|irions|; vous|iriez|; ils|iraient|"),
        subjonctif=_rows("que je|aille|/ʒaj/; que tu|ailles|/ty aj/; qu'il|aille|/il aj/; que nous|allions|/nu.z‿a.jɔ̃/; que vous|alliez|/vu.z‿a.je/; qu'ils|aillent|/il.z‿aj/"),
    ),
    "faire": dict(
        group=3, mean="做；制造（谈天气也只能用它）", inf_ipa="/fɛʁ/",
        pp="fait", pp_ipa="/fɛ/", aux="avoir",
        note="三个坑：nous faisons 读 /fə.zɔ̃/（不是 /fɛ.zɔ̃/）；vous faites 读 /fɛt/；ils font 换词根读 /fɔ̃/。",
        present=_rows("je|fais|/ʒə fɛ/; tu|fais|/ty fɛ/; il|fait|/il fɛ/; nous|faisons|/nu fə.zɔ̃/; vous|faites|/vu fɛt/; ils|font|/il fɔ̃/"),
        imparfait=_rows("je|faisais|/ʒə fə.zɛ/; tu|faisais|; il|faisait|; nous|faisions|/nu fə.zjɔ̃/; vous|faisiez|/vu fə.zje/; ils|faisaient|/il fə.zɛ/"),
        futur=_rows("je|ferai|/ʒə fə.ʁe/; tu|feras|; il|fera|; nous|ferons|; vous|ferez|; ils|feront|"),
        conditionnel=_rows("je|ferais|/ʒə fə.ʁɛ/; tu|ferais|; il|ferait|; nous|ferions|; vous|feriez|; ils|feraient|"),
        subjonctif=_rows("que je|fasse|/fas/; que tu|fasses|; qu'il|fasse|; que nous|fassions|/fa.sjɔ̃/; que vous|fassiez|/fa.sje/; qu'ils|fassent|/fas/"),
    ),
    "prendre": dict(
        group=3, mean="拿；乘坐（prendre le métro 坐地铁）", inf_ipa="/pʁɑ̃dʁ/",
        pp="pris", pp_ipa="/pʁi/", aux="avoir",
        note="单数三个人称都读 /pʁɑ̃/（-ds、-d 都不发音）；nous / vous 换成 pren- 词根；ils prennent 读 /pʁɛn/。",
        present=_rows("je|prends|/ʒə pʁɑ̃/; tu|prends|/ty pʁɑ̃/; il|prend|/il pʁɑ̃/; nous|prenons|/nu pʁə.nɔ̃/; vous|prenez|/vu pʁə.ne/; ils|prennent|/il pʁɛn/"),
        imparfait=_rows("je|prenais|/ʒə pʁə.nɛ/; tu|prenais|; il|prenait|; nous|prenions|/nu pʁə.njɔ̃/; vous|preniez|/vu pʁə.nje/; ils|prenaient|/il pʁə.nɛ/"),
        futur=_rows("je|prendrai|/ʒə pʁɑ̃.dʁe/; tu|prendras|; il|prendra|; nous|prendrons|; vous|prendrez|; ils|prendront|"),
        conditionnel=_rows("je|prendrais|/ʒə pʁɑ̃.dʁɛ/; tu|prendrais|; il|prendrait|; nous|prendrions|; vous|prendriez|; ils|prendraient|"),
        subjonctif=_rows("que je|prenne|/pʁɛn/; que tu|prennes|; qu'il|prenne|; que nous|prenions|/pʁə.njɔ̃/; que vous|preniez|/pʁə.nje/; qu'ils|prennent|/pʁɛn/"),
    ),
    "apprendre": dict(
        group=3, mean="学；学会", inf_ipa="/a.pʁɑ̃dʁ/",
        pp="appris", pp_ipa="/a.pʁi/", aux="avoir",
        note="和 prendre 同族，词根、变位套路完全一样：apprendre / comprendre / reprendre。",
        present=_rows("j'|apprends|/ʒa.pʁɑ̃/; tu|apprends|/ty a.pʁɑ̃/; il|apprend|/i.la.pʁɑ̃/; nous|apprenons|/nu.z‿a.pʁə.nɔ̃/; vous|apprenez|/vu.z‿a.pʁə.ne/; ils|apprennent|/il.z‿a.pʁɛn/"),
        imparfait=_rows("j'|apprenais|/ʒa.pʁə.nɛ/; tu|apprenais|; il|apprenait|; nous|apprenions|; vous|appreniez|; ils|apprenaient|"),
        futur=_rows("j'|apprendrai|/ʒa.pʁɑ̃.dʁe/; tu|apprendras|; il|apprendra|; nous|apprendrons|; vous|apprendrez|; ils|apprendront|"),
        conditionnel=_rows("j'|apprendrais|/ʒa.pʁɑ̃.dʁɛ/; tu|apprendrais|; il|apprendrait|; nous|apprendrions|; vous|apprendriez|; ils|apprendraient|"),
        subjonctif=_rows("que j'|apprenne|/ʒa.pʁɛn/; que tu|apprennes|; qu'il|apprenne|; que nous|apprenions|; que vous|appreniez|; qu'ils|apprennent|"),
    ),
    "comprendre": dict(
        group=3, mean="理解；明白", inf_ipa="/kɔ̃.pʁɑ̃dʁ/",
        pp="compris", pp_ipa="/kɔ̃.pʁi/", aux="avoir",
        note="和 prendre、apprendre 同族，一起记最省力。",
        present=_rows("je|comprends|/ʒə kɔ̃.pʁɑ̃/; tu|comprends|; il|comprend|; nous|comprenons|/nu kɔ̃.pʁə.nɔ̃/; vous|comprenez|; ils|comprennent|/il kɔ̃.pʁɛn/"),
        futur=_rows("je|comprendrai|/ʒə kɔ̃.pʁɑ̃.dʁe/; tu|comprendras|; il|comprendra|; nous|comprendrons|; vous|comprendrez|; ils|comprendront|"),
        conditionnel=_rows("je|comprendrais|/ʒə kɔ̃.pʁɑ̃.dʁɛ/; tu|comprendrais|; il|comprendrait|; nous|comprendrions|; vous|comprendriez|; ils|comprendraient|"),
    ),
    "vouloir": dict(
        group=3, mean="想要", inf_ipa="/vu.lwaʁ/",
        pp="voulu", pp_ipa="/vu.ly/", aux="avoir",
        note="条件式 je voudrais 是法语最常用的礼貌说法：「我想要……」。",
        present=_rows("je|veux|/ʒə vø/; tu|veux|/ty vø/; il|veut|/il vø/; nous|voulons|/nu vu.lɔ̃/; vous|voulez|/vu vu.le/; ils|veulent|/il vœl/"),
        imparfait=_rows("je|voulais|/ʒə vu.lɛ/; tu|voulais|; il|voulait|; nous|voulions|; vous|vouliez|; ils|voulaient|"),
        futur=_rows("je|voudrai|/ʒə vu.dʁe/; tu|voudras|; il|voudra|; nous|voudrons|; vous|voudrez|; ils|voudront|"),
        conditionnel=_rows("je|voudrais|/ʒə vu.dʁɛ/; tu|voudrais|; il|voudrait|; nous|voudrions|; vous|voudriez|; ils|voudraient|"),
        subjonctif=_rows("que je|veuille|/vœj/; que tu|veuilles|; qu'il|veuille|; que nous|voulions|; que vous|vouliez|; qu'ils|veuillent|"),
    ),
    "pouvoir": dict(
        group=3, mean="能；可以", inf_ipa="/pu.vwaʁ/",
        pp="pu", pp_ipa="/py/", aux="avoir",
        note="条件式 je pourrais 用于礼貌请求；现在时 ils peuvent 读 /pœv/。",
        present=_rows("je|peux|/ʒə pø/; tu|peux|/ty pø/; il|peut|/il pø/; nous|pouvons|/nu pu.vɔ̃/; vous|pouvez|/vu pu.ve/; ils|peuvent|/il pœv/"),
        imparfait=_rows("je|pouvais|/ʒə pu.vɛ/; tu|pouvais|; il|pouvait|; nous|pouvions|; vous|pouviez|; ils|pouvaient|"),
        futur=_rows("je|pourrai|/ʒə pu.ʁe/; tu|pourras|; il|pourra|; nous|pourrons|; vous|pourrez|; ils|pourront|"),
        conditionnel=_rows("je|pourrais|/ʒə pu.ʁɛ/; tu|pourrais|; il|pourrait|; nous|pourrions|; vous|pourriez|; ils|pourraient|"),
        subjonctif=_rows("que je|puisse|/pɥis/; que tu|puisses|; qu'il|puisse|; que nous|puissions|; que vous|puissiez|; qu'ils|puissent|"),
    ),
    "sortir": dict(
        group=3, mean="出去；拿出", inf_ipa="/sɔʁ.tiʁ/",
        pp="sorti(e)", pp_ipa="/sɔʁ.ti/", aux="être",
        note="表示「出去」时用 être 当助动词，阴性加 -e：je suis sorti（阴性 je suis sortie）。",
        present=_rows("je|sors|/ʒə sɔʁ/; tu|sors|; il|sort|/il sɔʁ/; nous|sortons|/nu sɔʁ.tɔ̃/; vous|sortez|/vu sɔʁ.te/; ils|sortent|/il sɔʁt/"),
        imparfait=_rows("je|sortais|/ʒə sɔʁ.tɛ/; tu|sortais|; il|sortait|; nous|sortions|; vous|sortiez|; ils|sortaient|"),
        futur=_rows("je|sortirai|/ʒə sɔʁ.ti.ʁe/; tu|sortiras|; il|sortira|; nous|sortirons|; vous|sortirez|; ils|sortiront|"),
        conditionnel=_rows("je|sortirais|/ʒə sɔʁ.ti.ʁɛ/; tu|sortirais|; il|sortirait|; nous|sortirions|; vous|sortiriez|; ils|sortiraient|"),
        subjonctif=_rows("que je|sorte|/sɔʁt/; que tu|sortes|; qu'il|sorte|; que nous|sortions|; que vous|sortiez|; qu'ils|sortent|"),
    ),
    "finir": dict(
        group=2, mean="结束；完成", inf_ipa="/fi.niʁ/",
        pp="fini", pp_ipa="/fi.ni/", aux="avoir",
        note="第二组（-ir）的样板：复数加 -iss-（nous finissons）。",
        present=_rows("je|finis|/ʒə fi.ni/; tu|finis|; il|finit|; nous|finissons|/nu fi.ni.sɔ̃/; vous|finissez|/vu fi.ni.se/; ils|finissent|/il fi.nis/"),
        imparfait=_rows("je|finissais|/ʒə fi.ni.sɛ/; tu|finissais|; il|finissait|; nous|finissions|; vous|finissiez|; ils|finissaient|"),
        futur=_rows("je|finirai|/ʒə fi.ni.ʁe/; tu|finiras|; il|finira|; nous|finirons|; vous|finirez|; ils|finiront|"),
        conditionnel=_rows("je|finirais|/ʒə fi.ni.ʁɛ/; tu|finirais|; il|finirait|; nous|finirions|; vous|finiriez|; ils|finiraient|"),
        subjonctif=_rows("que je|finisse|/fi.nis/; que tu|finisses|; qu'il|finisse|; que nous|finissions|; que vous|finissiez|; qu'ils|finissent|"),
    ),
    # Impersonal verbs: only the il form exists. One row tells the whole story.
    "pleuvoir": dict(
        group=3, mean="下雨（只有无人称的 il）", inf_ipa="/plø.vwaʁ/",
        pp="plu", pp_ipa="/ply/", aux="avoir",
        note="无人称动词，主语永远是 il，不会换成 elle。",
        present=_rows("il|pleut|/il plø/"),
        futur=_rows("il|pleuvra|/il plø.vʁa/"),
    ),
    "neiger": dict(
        group=1, mean="下雪（只有无人称的 il）", inf_ipa="/nɛ.ʒe/",
        pp="neigé", pp_ipa="/nɛ.ʒe/", aux="avoir",
        note="无人称动词，主语永远是 il。",
        present=_rows("il|neige|/il nɛʒ/"),
        futur=_rows("il|neigera|/il nɛ.ʒə.ʁa/"),
    ),
    "falloir": dict(
        group=3, mean="必须（只有无人称的 il faut）", inf_ipa="/fa.lwaʁ/",
        pp="fallu", pp_ipa="/fa.ly/", aux="avoir",
        note="il faut + 动词原形 = 必须做某事；il faut que + 虚拟式。",
        present=_rows("il|faut|/il fo/"),
        imparfait=_rows("il|fallait|/il fa.lɛ/"),
        futur=_rows("il|faudra|/il fo.dʁa/"),
        conditionnel=_rows("il|faudrait|/il fo.dʁɛ/"),
    ),
}


# ── Regular verbs, generated ──────────────────────────────────────────────
# présent is authored (spelling is where the traps live: -ger, -yer, elision);
# every other tense is generated from the infinitive, which in French is
# completely regular for -er verbs.

_REGULAR_ER: dict[str, dict] = {
    "jouer": dict(mean="玩；演奏（jouer du piano 弹钢琴）", inf_ipa="/ʒwe/", pp="joué", pp_ipa="/ʒwe/",
                  note="乐器用 jouer de，球类用 jouer à。",
                  present="je|joue|/ʒə ʒu/; tu|joues|/ty ʒu/; il|joue|/il ʒu/; nous|jouons|/nu ʒwɔ̃/; vous|jouez|/vu ʒwe/; ils|jouent|/il ʒu/"),
    "visiter": dict(mean="参观；拜访", inf_ipa="/vi.zi.te/", pp="visité", pp_ipa="/vi.zi.te/",
                    present="je|visite|/ʒə vi.zit/; tu|visites|; il|visite|; nous|visitons|/nu vi.zi.tɔ̃/; vous|visitez|/vu vi.zi.te/; ils|visitent|/il vi.zit/"),
    "trouver": dict(mean="找到；觉得（trouver ça bizarre 觉得奇怪）", inf_ipa="/tʁu.ve/", pp="trouvé", pp_ipa="/tʁu.ve/",
                    present="je|trouve|/ʒə tʁuv/; tu|trouves|; il|trouve|; nous|trouvons|/nu tʁu.vɔ̃/; vous|trouvez|/vu tʁu.ve/; ils|trouvent|/il tʁuv/"),
    "décider": dict(mean="决定（décider de + 原形）", inf_ipa="/de.si.de/", pp="décidé", pp_ipa="/de.si.de/",
                    note="décider de + 动词原形 = 决定做某事。",
                    present="je|décide|/ʒə de.sid/; tu|décides|; il|décide|; nous|décidons|/nu de.si.dɔ̃/; vous|décidez|/vu de.si.de/; ils|décident|/il de.sid/"),
    "briller": dict(mean="发光；照耀", inf_ipa="/bʁi.je/", pp="brillé", pp_ipa="/bʁi.je/",
                    note="第一组（-er）规则动词的样板，占法语动词约九成。",
                    present="je|brille|/ʒə bʁij/; tu|brilles|; il|brille|/il bʁij/; nous|brillons|/nu bʁi.jɔ̃/; vous|brillez|/vu bʁi.je/; ils|brillent|/il bʁij/"),
    "parler": dict(mean="说话；讲（parler français 讲法语）", inf_ipa="/paʁ.le/", pp="parlé", pp_ipa="/paʁ.le/",
                    present="je|parle|/ʒə paʁl/; tu|parles|; il|parle|; nous|parlons|/nu paʁ.lɔ̃/; vous|parlez|/vu paʁ.le/; ils|parlent|/il paʁl/"),
    "manger": dict(mean="吃", inf_ipa="/mɑ̃.ʒe/", pp="mangé", pp_ipa="/mɑ̃.ʒe/",
                    note="manger 属 -ger 家族：nous mangeons 要保留 e，否则 g 会读成 /ʒ/ 以外的音。",
                    ger=True,
                    present="je|mange|/ʒə mɑ̃ʒ/; tu|manges|; il|mange|; nous|mangeons|/nu mɑ̃.ʒɔ̃/; vous|mangez|/vu mɑ̃.ʒe/; ils|mangent|/il mɑ̃ʒ/"),
    "oublier": dict(mean="忘记（oublier de + 原形）", inf_ipa="/u.bli.je/", pp="oublié", pp_ipa="/u.bli.je/",
                    note="oublier de + 动词原形 = 忘记做某事。",
                    present="j'|oublie|/ʒu.bli/; tu|oublies|; il|oublie|; nous|oublions|/nu.z‿u.bli.jɔ̃/; vous|oubliez|/vu.z‿u.bli.je/; ils|oublient|/il.z‿u.bli/"),
    "refuser": dict(mean="拒绝（refuser de + 原形）", inf_ipa="/ʁə.fy.ze/", pp="refusé", pp_ipa="/ʁə.fy.ze/",
                    note="refuser de + 动词原形 = 拒绝做某事。",
                    present="je|refuse|/ʒə ʁə.fyz/; tu|refuses|; il|refuse|; nous|refusons|/nu ʁə.fy.zɔ̃/; vous|refusez|/vu ʁə.fy.ze/; ils|refusent|/il ʁə.fyz/"),
    "éviter": dict(mean="避免（éviter de + 原形）", inf_ipa="/e.vi.te/", pp="évité", pp_ipa="/e.vi.te/",
                   note="éviter de + 动词原形 = 避免做某事。",
                   present="j'|évite|/ʒe.vit/; tu|évites|; il|évite|; nous|évitons|/nu.z‿e.vi.tɔ̃/; vous|évitez|/vu.z‿e.vi.te/; ils|évitent|/il.z‿e.vit/"),
    "essayer": dict(mean="尝试（essayer de + 原形）", inf_ipa="/e.sɛ.je/", pp="essayé", pp_ipa="/e.sɛ.je/",
                    note="essayer 属 -yer 家族：je / tu / il / ils 把 y 变 i（j'essaie）。",
                    yer=True,
                    present="j'|essaie|/ʒe.sɛ/; tu|essaies|; il|essaie|; nous|essayons|/nu.z‿e.sɛ.jɔ̃/; vous|essayez|/vu.z‿e.sɛ.je/; ils|essaient|/il.z‿e.sɛ/"),
}


_AUX_PRES = {
    "avoir": ["ai", "as", "a", "avons", "avez", "ont"],
    "être": ["suis", "es", "est", "sommes", "êtes", "sont"],
}

_IMP_END = ["ais", "ais", "ait", "ions", "iez", "aient"]
_FUT_END = ["ai", "as", "a", "ons", "ez", "ont"]
_SUBJ_END = ["e", "es", "e", "ions", "iez", "ent"]


def _pron_col(idx: int, form: str, que: bool = False) -> str:
    """Pronoun cell for a row, eliding je → j' before a vowel sound."""
    if que:
        base = _PRON_QUE[idx]
        if base == "que je" and form[:1].lower() in VOWELS:
            return "que j'"
        return base
    pron = _PRON[idx]
    if pron == "je" and form[:1].lower() in VOWELS:
        return "j'"
    return pron


def _pc_rows(aux: str, pp: str) -> list[list[str]]:
    """Compound past: auxiliary in the present + past participle."""
    forms = _AUX_PRES.get(aux, _AUX_PRES["avoir"])
    return [[_pron_col(i, forms[i]), forms[i] + " " + pp, ""] for i in range(6)]


def _gen_regular_er(inf: str, meta: dict) -> dict[str, list[list[str]]]:
    """Build the non-présent tenses of an -er verb from its infinitive.

    Spelling only — French -er conjugation is completely regular here, so this
    is arithmetic rather than guesswork. IPA is left blank where it is not
    authored; the UI offers 🔊 on every form.
    """
    stem = inf[:-2]                       # parler → parl, manger → mang
    ger = bool(meta.get("ger"))
    imp_stem = inf[:-1] if ger else stem  # mange- (keeps the e) / parl-
    pp = stem + "é"

    def build(suffixes: list[str], base: str, que: bool = False) -> list[list[str]]:
        return [
            [_pron_col(i, base + suffixes[i], que), base + suffixes[i], ""]
            for i in range(6)
        ]

    return {
        "imparfait": build(_IMP_END, imp_stem),
        "futur": build(_FUT_END, inf),
        "conditionnel": build(_IMP_END, inf),
        "subjonctif": build(_SUBJ_END, stem, que=True),
        "passe_compose": _pc_rows(meta.get("aux", "avoir"), pp),
    }


# ── Public API ────────────────────────────────────────────────────────────

def _ordered(tables: dict[str, list[list[str]]]) -> dict[str, list[list[str]]]:
    """Keep tense order canonical so the tooltip's tabs never shuffle."""
    return {t: tables[t] for t in TENSE_ORDER if t in tables}


def _verb_book() -> dict[str, dict]:
    """Assemble every verb's full table, once."""
    book: dict[str, dict] = {}

    for inf, meta in _IRREGULAR.items():
        tables: dict[str, list[list[str]]] = {}
        for tense in TENSE_ORDER:
            rows = meta.get(tense)
            if rows:
                tables[tense] = rows
        if "passe_compose" not in tables:
            tables["passe_compose"] = _pc_rows(
                meta.get("aux", "avoir"), meta.get("pp", "")
            )
        book[inf] = dict(
            inf=inf, group=meta.get("group", 3), mean=meta.get("mean", ""),
            inf_ipa=meta.get("inf_ipa", ""), pp=meta.get("pp", ""),
            pp_ipa=meta.get("pp_ipa", ""), aux=meta.get("aux", "avoir"),
            note=meta.get("note", ""), tables=_ordered(tables),
        )

    for inf, meta in _REGULAR_ER.items():
        tables = _gen_regular_er(inf, meta)
        tables["present"] = _rows(meta["present"])
        book[inf] = dict(
            inf=inf, group=1, mean=meta.get("mean", ""),
            inf_ipa=meta.get("inf_ipa", ""), pp=meta.get("pp", ""),
            pp_ipa=meta.get("pp_ipa", ""), aux=meta.get("aux", "avoir"),
            note=meta.get("note", ""), tables=_ordered(tables),
        )
    return book


BOOK: dict[str, dict] = _verb_book()


def _build_index() -> dict[str, list[dict]]:
    """Reverse map: surface form → every (verb, tense, person, ipa) it can be.

    Includes the infinitive and the past participle, so tapping "fait" or
    "pris" in an explanation still tells you where it came from.

    Buckets are sorted so the *default* reading is the one a reader most likely
    wants — "brillent" is a present-tense form before it is a subjunctive one.
    """
    idx: dict[str, list[dict]] = {}
    priority = {
        "present": 0, "passe_compose": 1, "imparfait": 2, "futur": 3,
        "conditionnel": 4, "participe": 5, "infinitif": 6, "subjonctif": 7,
    }

    def add(key: str, entry: dict) -> None:
        key = key.lower().strip()
        if not key:
            return
        bucket = idx.setdefault(key, [])
        for e in bucket:
            if e["v"] == entry["v"] and e["t"] == entry["t"] and e["i"] == entry["i"]:
                return
        bucket.append(entry)

    for inf, v in BOOK.items():
        add(inf, {"v": inf, "t": "infinitif", "i": -1, "ipa": v["inf_ipa"]})
        if v["pp"]:
            # "allé(e)" is one table cell but two real surface forms — index both
            # so tapping "allée" in "je suis allée" still explains itself.
            for surface in {
                v["pp"].replace("(e)", "").replace("(s)", ""),
                v["pp"].replace("(e)", "e").replace("(s)", "s"),
            }:
                add(surface, {"v": inf, "t": "participe", "i": -1, "ipa": v["pp_ipa"]})
        for tense, rows in v["tables"].items():
            for i, row in enumerate(rows):
                add(row[1], {"v": inf, "t": tense, "i": i, "ipa": row[2]})
                # Passé composé rows carry "ai visité" — index the participle
                # half too so a lone "visité" resolves.
                if tense == "passe_compose" and " " in row[1]:
                    add(row[1].split(" ", 1)[1],
                        {"v": inf, "t": "participe", "i": -1, "ipa": ""})

    for bucket in idx.values():
        bucket.sort(key=lambda e: priority.get(e["t"], 9))
    return idx


INDEX: dict[str, list[dict]] = _build_index()


def find_form(token: str) -> list[dict]:
    """Every reading of ``token`` as a conjugated form (may be empty)."""
    return INDEX.get(token.lower().strip("'"), [])


def tables(inf: str) -> dict | None:
    return BOOK.get(inf.lower().strip())


def has_verb(inf: str) -> bool:
    return inf.lower().strip() in BOOK


def aliases() -> dict[str, str]:
    """Every indexed surface form → its verb, for the renderer's lexicon."""
    return {form: entries[0]["v"] for form, entries in INDEX.items() if entries}
