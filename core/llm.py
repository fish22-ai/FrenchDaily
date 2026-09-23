"""LLM-powered French sentence generator.

Uses the same API endpoint as dailybrief (agentrouter via CC Switch proxy).
Generates French sentences at specified difficulty levels (A1/A2/B1/B2)
with Chinese translations, IPA, and grammar notes.

Falls back to built-in corpus if the API is unavailable.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Optional

import requests

from core.models import Sentence, Word

log = logging.getLogger(__name__)

MODEL = "deepseek-v4-flash"
API_URL = "https://agentrouter.org/v1/chat/completions"

# deepseek-v4-flash is a *reasoning* model: it spends output tokens on a hidden
# think phase before writing a single character of `content`. At 4000 tokens the
# budget was consumed entirely by reasoning, `content` came back as "" and every
# day silently fell through to the built-in corpus. 16000 leaves room for both;
# the retry budget covers a day where the answer runs long.
MAX_TOKENS = 16000
MAX_TOKENS_RETRY = 32000

LEVEL_DESCRIPTIONS = {
    "A1": {
        "name_cn": "入门",
        "desc": (
            "最基础的词汇和语法。句子简短（5-12词），"
            "只使用高频名词、动词、形容词。"
            "时态只限现在时和最近将来时。"
            "避免从句、复合句和虚拟式。"
        ),
    },
    "A2": {
        "name_cn": "基础",
        "desc": (
            "A1词汇加常见日常词汇。句子中等长度（8-15词），"
            "可包含简单复合句（用et/mais/ou/donc/car连接）。"
            "时态扩展至未完成过去时和复合过去时。"
            "引入直接宾语代词。"
        ),
    },
    "B1": {
        "name_cn": "进阶",
        "desc": (
            "A1-A2词汇加更丰富的表达。句子较长（12-20词），"
            "可使用关系代词（qui/que/où）、虚拟式简单时态。"
            "时态涵盖条件式现在时和愈复合过去时。"
        ),
    },
    "B2": {
        "name_cn": "中高级",
        "desc": (
            "广泛词汇包括一些书面语和习语。句子复杂多变（15-25词），"
            "自如使用所有时态包括虚拟式过去时。"
            "引入抽象概念和观点表达。"
        ),
    },
}


def _get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key and key != "PROXY_MANAGED":
        return key
    db_path = Path.home() / ".cc-switch" / "cc-switch.db"
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute("SELECT settings_config FROM providers WHERE is_current=1")
            row = cur.fetchone()
            if row:
                cfg = json.loads(row[0])
                key = cfg.get("env", {}).get("ANTHROPIC_AUTH_TOKEN", "")
                if key:
                    return key
        except Exception:
            pass
    return ""


def _get_base_url() -> str:
    return os.environ.get("ANTHROPIC_BASE_URL", "https://agentrouter.org")


def build_prompt(difficulty_mix: dict[str, int], theme: str = "",
                 avoid: list[str] | None = None) -> str:
    parts = []
    total = sum(difficulty_mix.values())
    for level in ["A1", "A2", "B1", "B2"]:
        count = difficulty_mix.get(level, 0)
        if count == 0:
            continue
        info = LEVEL_DESCRIPTIONS[level]
        parts.append(
            f"  - {level} ({info['name_cn']}) x {count}句\n"
            f"    要求：{info['desc']}"
        )
    theme_instr = f"\n主题方向：{theme}。所有句子围绕这个主题展开。" if theme else ""
    # Naming the recent sentences costs nothing and kills the "yesterday's page
    # again" complaint at the source.
    avoid_instr = ""
    if avoid:
        listed = "\n".join(f"  - {s}" for s in avoid[:25])
        avoid_instr = (
            "\n最近已经用过的句子（**绝对不要重复或改写其中任何一句**，"
            "内容、场景、句型都要换开）：\n" + listed + "\n"
        )

    return f"""你是法语教学专家，学生是中文母语者、语法基础薄弱、已经忘了不少语法概念。
生成 {total} 句适合学习的法语句子：

{chr(10).join(parts)}
{theme_instr}{avoid_instr}
要求：
1. 每句完整、语法正确
2. 内容贴近日常生活（问候/购物/餐饮/交通/天气/爱好/旅行）
3. 每句附带准确中文翻译
4. 每句给一个 grammar_note：用中文一句话点出这句最值得注意的语法点
5. 每句给 grammar_notes：为句中 2-3 个重点词添加逐词语法讲解，key 用该词的原形（去掉 m'/j'/d' 等前缀，如 "apprends"、"fait"），value 是中文
6. **每句给 grammar_lessons：3-6 讲语法课**，这是重点。学生语法基础差，要当他是第一次学：
   - 每讲是一个对象 {{"t": "标题", "b": "正文"}}
   - t 用提问或直白的说法，例如「复合过去时是什么」「faire 到底是什么意思」「为什么天气句的主语是 il」
   - b 用中文口语化地讲清楚，从零讲起，不要用「如前所述」这类省略
   - 需要时把动词变位整套列出，用换行分隔，例如：
     "je fais /ʒə fɛ/　·　tu fais /ty fɛ/　·　il fait /il fɛ/\\nnous faisons /nu fə.zɔ̃/　·　vous faites /vu fɛt/　·　ils font /il fɔ̃/"
   - 要指出中国人容易错的点、易混形式（如 j'apprendrai vs j'apprendrais）
   - 语法术语第一次出现时要用中文解释它是什么，再给例子
   - 不要只复述句子翻译，要讲可复用的规律
7. 同一天不同句子尽量用不同词汇
8. 句子独立成篇，不要有逻辑依赖

严格 JSON 输出（不要其他内容）：
{{
  "title_fr": "今日标题（法文5-10词）",
  "title_zh": "今日标题（中文）",
  "sentences": [
    {{
      "id": "s1",
      "difficulty": "A2",
      "text": "La phrase.",
      "translation": "中文翻译。",
      "grammar_note": "这句的核心语法点，一句话。",
      "grammar_notes": {{
        "apprends": "apprendre 的现在时 je 形式（同 prendre 一族）",
        "fait": "faire 的现在时 il 形式"
      }},
      "grammar_lessons": [
        {{
          "t": "复合过去时是什么",
          "b": "讲已经做完的事用复合过去时，公式是助动词 avoir 的现在时加过去分词。j'ai visité 就是 j'ai（我有）加 visité（参观过）。"
        }},
        {{
          "t": "avoir 的现在时变位",
          "b": "j'ai /ʒe/　·　tu as /ty a/　·　il a /il a/\\nnous avons /nu.z‿a.vɔ̃/　·　vous avez /vu.z‿a.ve/　·　ils ont /il.z‿ɔ̃/"
        }}
      ]
    }}
  ]
}}

注意：
- id 从 s1 连续编号
- difficulty 必须是 A1/A2/B1/B2
- grammar_note 是中文，不要留空；grammar_lessons 至少 3 讲，不要留空
- grammar_notes / grammar_lessons 里出现的法语词请附音标（斜杠包裹）
- pos: nm/nf/v/adj/adv/prep/conj/pron/interj/np
- b 字段里需要换行时用 \\n
- JSON 必须合法"""


def _extract_json(text: str) -> dict:
    """Pull the JSON object out of a model reply (fences, stray prose, …)."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise json.JSONDecodeError("no JSON object in reply", text, 0)
    return json.loads(text[start:end + 1])


def _post(prompt: str, max_tokens: int, timeout: int) -> Optional[dict]:
    """One completion round-trip. Returns the parsed reply, or None."""
    api_key = _get_api_key()
    if not api_key:
        log.warning("No API key available")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "user-agent": "claude-cli/2.0.0 (external, cli)",
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "claude-code-20250219",
    }

    log.info("Calling LLM (%s, max_tokens=%d) for French content...", MODEL, max_tokens)
    resp = requests.post(
        f"{_get_base_url()}/v1/chat/completions",
        headers=headers,
        json={"model": MODEL, "max_tokens": max_tokens,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=timeout,
    )
    if resp.status_code != 200:
        log.warning("LLM HTTP %d: %s", resp.status_code, resp.text[:200])
        return None

    choice = (resp.json().get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content") or ""
    # Keep the think phase out of the log but note its size — an empty `content`
    # with a huge `reasoning_content` is the truncated-budget signature.
    log.info("LLM reply: finish=%s content=%d chars reasoning=%d chars",
             choice.get("finish_reason"), len(content),
             len(message.get("reasoning_content") or ""))

    if not content.strip():
        log.warning("LLM returned empty content (finish_reason=%s)",
                    choice.get("finish_reason"))
        return None
    if choice.get("finish_reason") == "length":
        log.warning("LLM reply hit the token ceiling, treating as unusable")
        return None

    result = _extract_json(content)
    log.info("LLM generated %d sentences", len(result.get("sentences", [])))
    return result


def call_llm(prompt: str, timeout: int = 240) -> Optional[dict]:
    """Two attempts: normal budget, then a doubled one.

    The retry exists for the reasoning-model failure mode above — a big think
    phase can still starve a long answer, and by then the model has already
    reasoned its way to the content, so re-asking is cheap.
    """
    for attempt, budget in enumerate((MAX_TOKENS, MAX_TOKENS_RETRY), start=1):
        try:
            result = _post(prompt, budget, timeout)
            if result and result.get("sentences"):
                return result
            log.warning("LLM attempt %d produced no usable sentences", attempt)
        except json.JSONDecodeError:
            log.warning("LLM attempt %d returned invalid JSON", attempt)
        except requests.RequestException as exc:
            log.warning("LLM attempt %d request failed: %s", attempt, exc)
        except Exception as exc:
            log.warning("LLM attempt %d error: %s", attempt, exc)
    return None


def generate_sentences(difficulty_mix: dict[str, int], theme: str = "",
                       avoid: list[str] | None = None) -> Optional[dict]:
    prompt = build_prompt(difficulty_mix, theme, avoid)
    return call_llm(prompt)


# ── Fallback Corpus ──────────────────────────────────────────────────────

BUILTIN_SENTENCES = [
    {
        "difficulty": "A1",
        "text": "Je m'appelle Marie. J'ai vingt ans.",
        "translation": "我叫玛丽。我二十岁。",
        "grammar_note": "je m'appelle 是自反动词 se appeler 的第一人称变位，意思是(我叫......)。J'ai 是 avoir 的第一人称变位，用来表达年龄。",
        "grammar_notes": {
            "m'appelle": "自反动词 se appeler 的第一人称变位，se appeler 表示称呼自己",
            "vingt": "法语数字20，注意70/80/90的特殊表达（soixante-dix, quatre-vingts）",
        },
        "words": [
            {"w": "appelle", "pos": "v", "def": "叫", "ipa": "/a.pɛl/", "example": "Comment tu t'appelles ?"},
            {"w": "ans", "pos": "nm", "def": "岁", "ipa": "/ɑ̃/", "example": "J'ai vingt ans."},
        ],
    },
    {
        "difficulty": "A1",
        "text": "Bonjour ! Je vais au café avec mon amie.",
        "translation": "你好！我和朋友去咖啡馆。",
        "grammar_note": "je vais 是 aller（去）的第一人称变位。au = à + le，意思是\"到\"。avec 是介词\"和\"。",
        "grammar_notes": {
            "vais": "aller（去）的第一人称变位，注意 aller 是不规则动词",
            "aujourd'hui": "aujourd'hui 是今天，由 au + jour + hui 构成"
        },
        "words": [
            {"w": "avec", "pos": "prep", "def": "和", "ipa": "/a.vɛk/", "example": "Avec mon ami."},
            {"w": "amie", "pos": "nf", "def": "女朋友", "ipa": "/a.mi/", "example": "C'est mon amie."},
        ],
    },
    {
        "difficulty": "A1",
        "text": "Il fait beau aujourd'hui. Le soleil brille.",
        "translation": "今天天气很好。太阳在发光。",
        "grammar_note": "il fait 是 faire 的第三人称变位。faire beau 是固定搭配\"天气好\"。aujourd'hui 是\"今天\"。",
        "grammar_notes": {
            "fait": "faire 的第三人称变位，faire 是最常用的不规则动词之一",
            "aujourd'hui": "aujourd'hui 是今天"
        },
        "words": [
            {"w": "beau", "pos": "adj", "def": "好的，晴朗的", "ipa": "/bo/", "example": "Il fait beau."},
            {"w": "soleil", "pos": "nm", "def": "太阳", "ipa": "/sɔ.lɛj/", "example": "Le soleil brille."},
        ],
    },
    {
        "difficulty": "A2",
        "text": "Hier, j'ai visité le musée du Louvre avec mes amis.",
        "translation": "昨天，我和朋友们参观了卢浮宫。",
        "grammar_note": "hier 是\"昨天\"。j'ai visité 是复合过去时：助动词 avoir + 过去分词 visité。du = de + le。",
        "grammar_notes": {
            "visite": "复合过去时（passe compose）：助动词 avoir + 过去分词 visite",
            "du": "de + le 的缩合形式，表示从/属于"
        },
        "words": [
            {"w": "visité", "pos": "v", "def": "参观了", "ipa": "/vi.zi.te/", "example": "J'ai visité Paris."},
            {"w": "amis", "pos": "nm", "def": "朋友们", "ipa": "/a.mi/", "example": "Mes amis sont gentils."},
        ],
    },
    {
        "difficulty": "A2",
        "text": "Je prends le métro pour aller au travail chaque jour.",
        "translation": "我每天坐地铁去上班。",
        "grammar_note": "je prends 是 prendre（坐/拿）的第一人称变位。pour + 动词原形 表示目的\"为了......\"。chaque 是\"每一个\"。",
        "grammar_notes": {
            "prends": "prendre（坐/拿）的第一人称变位，不规则动词",
            "chaque": "chaque 是每一个，后面直接跟名词不加冠词",
        },
        "words": [
            {"w": "métro", "pos": "nm", "def": "地铁", "ipa": "/me.tʁo/", "example": "La station de métro."},
            {"w": "chaque", "pos": "adj", "def": "每一个", "ipa": "/ʃak/", "example": "Chaque jour."},
        ],
    },
    {
        "difficulty": "B1",
        "text": "Bien que le temps soit froid, nous avons décidé de sortir.",
        "translation": "尽管天气很冷，我们还是决定出去。",
        "grammar_note": "bien que 是\"尽管\"，后面必须接虚拟式：le temps soit（être 的虚拟式现在时）。虚拟式表达不确定性或主观态度。",
        "grammar_notes": {
            "soit": "etre 的虚拟式现在时第三人称变位"
        },
        "words": [
            {"w": "bien", "pos": "conj", "def": "尽管", "ipa": "/bjɛ̃/", "example": "Bien qu'il soit tard."},
            {"w": "décidé", "pos": "v", "def": "决定了", "ipa": "/de.si.de/", "example": "J'ai décidé de partir."},
        ],
    },
    {
        "difficulty": "B1",
        "text": "Si j'avais plus de temps, j'apprendrais à jouer du piano.",
        "translation": "如果我有更多时间，我会学弹钢琴。",
        "grammar_note": "条件式虚拟式结构：si + imparfait（j'avais）→ conditionnel présent（j'apprendrais）。表示假设。",
        "grammar_notes": {
            "avais": "imparfait（未完成过去时）变位，si + imparfait 引出虚拟条件",
            "apprendrais": "conditionnel present（条件式现在时），表示假设"
        },
        "words": [
            {"w": "apprendrais", "pos": "v", "def": "会学（条件式）", "ipa": "/a.pʁɑ̃.dʁɛ/", "example": "J'apprendrais si je pouvais."},
            {"w": "piano", "pos": "nm", "def": "钢琴", "ipa": "/pja.no/", "example": "Jouer du piano."},
        ],
    },
    {
        "difficulty": "B1",
        "text": "Plus j'apprends le français, plus je trouve cette langue belle.",
        "translation": "我越学法语，越觉得这门语言优美。",
        "grammar_note": "plus...plus 是\"越......越......\"结构。cette 是阴性指示形容词\"这个\"，修饰阴性名词 langue。",
        "grammar_notes": {
            "plus": "plus...plus 结构表示越...越...",
            "cette": "cette 是指示形容词这个，修饰阴性名词 langue"
        },
        "words": [
            {"w": "trouve", "pos": "v", "def": "觉得", "ipa": "/tʁuv/", "example": "Je trouve cela intéressant."},
            {"w": "belle", "pos": "adj", "def": "美丽的（阴性）", "ipa": "/bɛl/", "example": "Une langue belle."},
        ],
    },
    # ── A1 additions ─────────────────────────────────────────────────────
    {
        "difficulty": "A1",
        "text": "J'habite à Lyon avec ma famille.",
        "translation": "我和家人住在里昂。",
        "grammar_note": "j'habite 是 habiter（住）的第一人称变位。城市名前用介词 à：à Lyon。",
        "grammar_notes": {
            "habite": "habiter（住）的第一人称，-er 动词按规则变位",
            "famille": "famille 是阴性名词，ma 是阴性单数物主形容词",
        },
    },
    {
        "difficulty": "A1",
        "text": "Le matin, je bois un café et je mange du pain.",
        "translation": "早上我喝一杯咖啡，吃面包。",
        "grammar_note": "du 是部分冠词，表示「一些」这种不确定的量，用于不可数名词。",
        "grammar_notes": {
            "bois": "boire（喝）的第一人称，不规则动词",
            "pain": "le pain 面包；du pain = 一些面包，不说 un pain",
        },
    },
    {
        "difficulty": "A1",
        "text": "C'est combien, ce livre ?",
        "translation": "这本书多少钱？",
        "grammar_note": "C'est combien 是问价最常用的说法。ce 是阳性指示形容词，修饰 livre。",
        "grammar_notes": {
            "combien": "combien 询问数量和价格",
            "livre": "livre 是阳性名词「书」（阴性时指「磅」）",
        },
    },
    {
        "difficulty": "A1",
        "text": "Nous allons au marché le samedi matin.",
        "translation": "我们每周六早上去市场。",
        "grammar_note": "au = à + le。le samedi 表示「每周六」这种习惯，不是某一个周六。",
        "grammar_notes": {
            "allons": "aller 的 nous 形式，不规则动词",
            "samedi": "le samedi 每周六；samedi 单独用只指某个周六",
        },
    },
    {
        "difficulty": "A1",
        "text": "Elle a un chat qui s'appelle Minou.",
        "translation": "她有一只叫米努的猫。",
        "grammar_note": "qui 是关系代词，代替前面的 le chat 作从句的主语。",
        "grammar_notes": {
            "a": "avoir 的第三人称形式，这里表示「拥有」",
            "qui": "qui 引导关系从句，在从句里作主语",
        },
    },
    {
        "difficulty": "A1",
        "text": "Je ne parle pas très bien français.",
        "translation": "我法语说得不太好。",
        "grammar_note": "否定用 ne ... pas 把变位动词夹在中间：je ne parle pas。",
        "grammar_notes": {
            "parle": "parler（说）的第一人称；否定要把 ne/pas 夹住它",
            "très": "très 修饰 bien；「说得好」是 parler bien",
        },
    },
    {
        "difficulty": "A1",
        "text": "Aujourd'hui, je travaille à la maison.",
        "translation": "今天我在家工作。",
        "grammar_note": "à la maison 是固定搭配「在家」，不用 chez。",
        "grammar_notes": {
            "travaille": "travailler 的第一人称，-er 动词规则变位",
            "maison": "la maison 房子；à la maison 在家",
        },
    },
    # ── A2 additions ─────────────────────────────────────────────────────
    {
        "difficulty": "A2",
        "text": "Nous avons mangé au restaurant hier soir.",
        "translation": "昨晚我们在餐馆吃了饭。",
        "grammar_note": "复合过去时 = avoir 的现在时 + 过去分词（avons mangé）。",
        "grammar_notes": {
            "mangé": "过去分词；manger 的复合过去时用 avoir 作助动词",
            "hier": "hier 昨天，通常配合复合过去时",
        },
    },
    {
        "difficulty": "A2",
        "text": "Quand j'étais petit, je jouais au football tous les jours.",
        "translation": "我小时候每天都踢足球。",
        "grammar_note": "未完成过去时（imparfait）表示过去的习惯或背景，区别于一次性动作的复合过去时。",
        "grammar_notes": {
            "étais": "être 的未完成过去时 je 形式",
            "jouais": "jouer 的未完成过去时，表示过去反复做的事",
        },
    },
    {
        "difficulty": "A2",
        "text": "Je vais partir en vacances au mois d'août.",
        "translation": "我八月要去度假。",
        "grammar_note": "aller + 动词原形 = 最近将来时，表示马上或计划将要做的事。",
        "grammar_notes": {
            "vais": "aller 的第一人称，这里作助动词，不表示「去」",
            "août": "au mois d'août 在八月",
        },
    },
    {
        "difficulty": "A2",
        "text": "Elle m'a téléphoné pendant que je dormais.",
        "translation": "我睡觉的时候她给我打了电话。",
        "grammar_note": "pendant que 引出同时发生的动作，用未完成过去时；主句动作用复合过去时。",
        "grammar_notes": {
            "téléphoné": "复合过去时；m' 是间接宾语代词（给我）",
            "dormais": "dormir 的未完成过去时，表示被打断时正在进行的动作",
        },
    },
    {
        "difficulty": "A2",
        "text": "Depuis deux ans, j'apprends le français tout seul.",
        "translation": "两年来我一直在自学法语。",
        "grammar_note": "depuis + 时间段，动词用现在时，表示从过去持续到现在——中文说「两年了」，法语不换时态。",
        "grammar_notes": {
            "depuis": "depuis 后接时间段或起点，动词用现在时",
            "seul": "tout seul 独自，强调没有别人帮忙",
        },
    },
    {
        "difficulty": "A2",
        "text": "Si tu veux, on peut aller au cinéma ce soir.",
        "translation": "如果你愿意，我们今晚可以去看电影。",
        "grammar_note": "si + 现在时，主句用现在时/最近将来时——真实条件句不涉及虚拟式。",
        "grammar_notes": {
            "veux": "vouloir 的 tu 形式，不规则动词",
            "peut": "pouvoir 的 on 形式；on 这里指「我们」",
        },
    },
    {
        "difficulty": "A2",
        "text": "Je cherche un appartement près de la gare.",
        "translation": "我在找车站附近的公寓。",
        "grammar_note": "chercher 是直接及物动词，后面直接跟宾语，不加 à 或 pour。",
        "grammar_notes": {
            "cherche": "chercher（找）的第一人称，不接介词",
            "près": "près de + 名词 = 在…附近",
        },
    },
    {
        "difficulty": "A2",
        "text": "Ce matin, je me suis levé très tôt.",
        "translation": "今天早上我很早就起床了。",
        "grammar_note": "自反动词的复合过去时用 être 作助动词，过去分词要和主语配合（levé）。",
        "grammar_notes": {
            "me": "自反代词；se lever 是「起床」，不是「举起」",
            "levé": "自反动词用 être 助动词，分词随主语变化",
        },
    },
    {
        "difficulty": "A2",
        "text": "On se retrouve devant le musée à trois heures.",
        "translation": "我们三点在博物馆前碰面。",
        "grammar_note": "se retrouver 表示「（约好）碰面」，是自反动词。",
        "grammar_notes": {
            "retrouve": "se retrouver 的第一人称式；on 代替 nous",
            "devant": "devant 在…前面（空间），区别于 avant 在…之前（时间）",
        },
    },
    # ── B1 additions ─────────────────────────────────────────────────────
    {
        "difficulty": "B1",
        "text": "Il faut que je finisse ce travail avant midi.",
        "translation": "我必须在中午前完成这项工作。",
        "grammar_note": "il faut que 后面必须用虚拟式：je finisse（不是 je finis）。",
        "grammar_notes": {
            "finisse": "il faut que 引出虚拟式：finir → je finisse",
            "avant": "avant + 时间点 = 在…之前；avant de + 动词原形",
        },
    },
    {
        "difficulty": "B1",
        "text": "Je doute qu'il vienne ce soir.",
        "translation": "我怀疑他今晚会来。",
        "grammar_note": "表示怀疑、否定、情感的动词后面接虚拟式：douter que + subjonctif。",
        "grammar_notes": {
            "vienne": "venir 的虚拟式第三人称：il vienne",
        },
    },
    {
        "difficulty": "B1",
        "text": "Ce que j'aime le plus en France, c'est la boulangerie du coin.",
        "translation": "在法国我最喜欢的是街角那家面包店。",
        "grammar_note": "ce que 引导名词性从句作主语，等于「我喜欢的（东西）」；du = de + le。",
        "grammar_notes": {
            "ce": "ce que = 关系代词，代表一个整体概念",
            "du": "du coin = de + le coin，街角的",
        },
    },
    {
        "difficulty": "B1",
        "text": "Après avoir fini mes études, je voudrais travailler à l'étranger.",
        "translation": "完成学业后，我想去国外工作。",
        "grammar_note": "après + 不定式过去时（avoir fini）表示「在…之后」，主语和主句一致时用这种写法。",
        "grammar_notes": {
            "après": "après avoir + 过去分词 = 在做完…之后",
            "voudrais": "条件式现在时，比 veux 客气，表达愿望",
        },
    },
    {
        "difficulty": "B1",
        "text": "Il m'a demandé si j'avais déjà visité la Provence.",
        "translation": "他问我是否去过普罗旺斯。",
        "grammar_note": "间接问句用 si 引导；主句是过去时，从句时态要后退——所以说 avais visité（愈过去时）。",
        "grammar_notes": {
            "si": "间接问句用 si（是否），不用 est-ce que",
            "avais": "avais visité 是愈过去时，表示比主句更早的动作",
        },
    },
    {
        "difficulty": "B1",
        "text": "Les enfants jouent dans le jardin pendant que leur mère prépare le dîner.",
        "translation": "孩子们在花园里玩，妈妈在准备晚饭。",
        "grammar_note": "pendant que 连接两个同时进行的动作。leur 在这里是单数物主形容词，修饰单数名词 mère。",
        "grammar_notes": {
            "pendant": "pendant que = 在…（发生的）同时",
            "leur": "leur + 单数名词 = 他们的；leurs + 复数名词",
        },
    },
    {
        "difficulty": "B1",
        "text": "Quand j'aurai le temps, je lirai ce roman que tu m'as conseillé.",
        "translation": "等我有时间，我就读你推荐的那本小说。",
        "grammar_note": "quand + 简单将来时，主句也用将来时——法语在时间状语从句里也用将来时，不像中文说「等我有空」。",
        "grammar_notes": {
            "aurai": "avoir 的简单将来时 je 形式：j'aurai",
            "que": "que 引导关系从句，修饰 ce roman",
        },
    },
    {
        "difficulty": "B1",
        "text": "On aurait dû réserver une table, le restaurant est complet.",
        "translation": "我们本该订个位子，餐馆坐满了。",
        "grammar_note": "aurait dû + 动词原形 = 「本该做而没做」，是一种遗憾/责备的语气。",
        "grammar_notes": {
            "aurait": "aurait dû + 不定式，过去条件式表示未实现的应该",
            "complet": "complet 满的（阳性）；阴性是 complète",
        },
    },
]


def _norm(text: str) -> str:
    return " ".join((text or "").split()).strip()


FALLBACK_TITLES = [
    ("Cinq phrases pour aujourd'hui", "今天的五句法语"),
    ("Le français, jour après jour", "每天一点法语"),
    ("Petites phrases, grands progrès", "小句子，大进步"),
    ("Un peu de français chaque jour", "每天学一点法语"),
    ("Des mots pour la journée", "今天用得上的句子"),
    ("Lire, écouter, répéter", "读一读，听一听，跟一跟"),
]


def get_fallback_sentences(difficulty_mix: dict[str, int] | None = None,
                           *, avoid: list[str] | None = None,
                           seed: str | None = None) -> dict:
    """Last-resort corpus pick — deterministic per day, blind to yesterday.

    Two rules, both learned from the "9/22 looks exactly like 9/21" bug:
      * the pick is seeded (by date), so one day always yields the same five
        sentences — but the *next* day's seed moves the window on;
      * anything in ``avoid`` (the sentences the last two weeks already showed)
        is skipped until that level's pool runs dry, and the title rotates too.
    """
    import random

    if difficulty_mix is None:
        difficulty_mix = {"A1": 1, "A2": 2, "B1": 2}
    rng = random.Random(seed or "frenchdaily")
    recent = {_norm(t) for t in (avoid or [])}
    wanted = sum(difficulty_mix.values())
    selected: list[dict] = []
    used: set[str] = set()

    def take(level: str, count: int) -> list[dict]:
        pool = [s for s in BUILTIN_SENTENCES if s["difficulty"] == level]
        fresh = [s for s in pool
                 if _norm(s["text"]) not in recent and _norm(s["text"]) not in used]
        stale = [s for s in pool if _norm(s["text"]) not in used and s not in fresh]
        rng.shuffle(fresh)
        rng.shuffle(stale)
        return (fresh + stale)[:count]  # only repeat once the fresh pool is empty

    for level, count in difficulty_mix.items():
        for s in take(level.upper(), count):
            selected.append(s)
            used.add(_norm(s["text"]))

    if len(selected) < wanted:  # config asked for more than the level pools hold
        rest = [s for s in BUILTIN_SENTENCES if _norm(s["text"]) not in used]
        rng.shuffle(rest)
        selected.extend(rest[:wanted - len(selected)])

    rng.shuffle(selected)  # interleave the levels instead of A1-block-first
    title_fr, title_zh = FALLBACK_TITLES[rng.randrange(len(FALLBACK_TITLES))]
    return {"title_fr": title_fr, "title_zh": title_zh, "sentences": selected}
