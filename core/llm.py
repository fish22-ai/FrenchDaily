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


def build_prompt(difficulty_mix: dict[str, int], theme: str = "") -> str:
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

    return f"""你是法语教学专家，学生是中文母语者、语法基础薄弱、已经忘了不少语法概念。
生成 {total} 句适合学习的法语句子：

{chr(10).join(parts)}
{theme_instr}

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


def call_llm(prompt: str, timeout: int = 120) -> Optional[dict]:
    api_key = _get_api_key()
    if not api_key:
        log.warning("No API key available")
        return None

    base_url = _get_base_url()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "user-agent": "claude-cli/2.0.0 (external, cli)",
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "claude-code-20250219",
    }

    try:
        log.info("Calling LLM (%s) for French content...", MODEL)
        resp = requests.post(
            f"{base_url}/v1/chat/completions",
            headers=headers,
            json={"model": MODEL, "max_tokens": 4000,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=timeout,
        )
        if resp.status_code != 200:
            log.warning("LLM HTTP %d: %s", resp.status_code, resp.text[:200])
            return None

        content = resp.json()["choices"][0]["message"]["content"]
        if not content:
            return None

        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
        if content.endswith("```"):
            content = content[:-3]
        result = json.loads(content.strip())
        log.info("LLM generated %d sentences", len(result.get("sentences", [])))
        return result

    except json.JSONDecodeError:
        log.warning("LLM returned invalid JSON")
    except requests.RequestException as exc:
        log.warning("LLM request failed: %s", exc)
    except Exception as exc:
        log.warning("LLM error: %s", exc)
    return None


def generate_sentences(difficulty_mix: dict[str, int], theme: str = "") -> Optional[dict]:
    prompt = build_prompt(difficulty_mix, theme)
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
]


def get_fallback_sentences(difficulty_mix: dict[str, int] | None = None) -> dict:
    if difficulty_mix is None:
        difficulty_mix = {"A1": 1, "A2": 2, "B1": 2}
    import random
    selected = []
    for level, count in difficulty_mix.items():
        pool = [s for s in BUILTIN_SENTENCES if s["difficulty"] == level]
        if pool:
            chosen = random.sample(pool, min(count, len(pool)))
            selected.extend(chosen)
    if len(selected) < sum(difficulty_mix.values()):
        remaining = sum(difficulty_mix.values()) - len(selected)
        pool = [s for s in BUILTIN_SENTENCES if s not in selected]
        selected.extend(random.sample(pool, min(remaining, len(pool))))
    return {
        "title_fr": "Phrases du jour",
        "title_zh": "今日法语句子",
        "sentences": selected,
    }
