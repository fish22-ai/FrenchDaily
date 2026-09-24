"""Top up dict/auto.json: entries for every word the pages show but the
dictionary lacks.

The dictionary is three hand-maintained files; the daily generator invents new
sentences faster than they get topped up, so a reader taps a word ("pomme")
and is told 未收录 while the explanation right below it plainly glosses it.
This script closes that loop:

    python scripts/gen_dict.py            # scan data/*.json, fill what's missing
    python scripts/gen_dict.py --dry-run  # report only, no LLM call, no write

Words are collected with exactly the tokenizer the renderer uses (IPA spans
skipped, hyphen-glued fragments skipped, 1-2 letter orphans skipped), so the
list is "what the reader can actually tap". Existing entries always win —
auto.json is an overlay of last resort, never a re-writer of curated wording.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import conjug  # noqa: E402
from core import html as H  # noqa: E402
from core import llm  # noqa: E402
from core.dict_lookup import Dictionary  # noqa: E402

log = logging.getLogger("gen_dict")

AUTO_PATH = ROOT / "dict" / "auto.json"
# Small batches: a 40-word reply is long enough that one stray quote can break
# the JSON, and a broken chunk costs the whole batch. 20 keeps replays cheap.
BATCH = 20

SYSTEM_RULES = """你是法语词典编辑。为给定的法语词逐个写出词条，只输出 JSON，不要解释。

输出格式（键就是给定的词，原样小写）：
{"pomme": {"pos": "nf", "ipa": "/pɔm/", "def": "苹果"}}

字段规则：
- pos：nf 阴性名词 / nm 阳性名词 / v 动词 / adj 形容词 / adv 副词 / pron 代词 / det 限定词 /
  prep 介词 / conj 连词 / num 数词 / interj 感叹词 / propn 专有名词
- ipa：斜杠包住的国际音标，按词形本身注音（变位形式按变位后的读音）
- def：简短中文释义，最多 12 字
- 如果给的是变位形式（如 choisisse、préférerais、restions），def 以原形开头，例如
  "（choisir 的虚拟式）选择"、"（préférer 的条件式）更愿意"；能判断时态就写明
- 如果该词不是规范法语词（拼写错误、缩写、符号残留），pos 填 "?"，def 填"疑似拼写有误：…"

JSON 硬性要求：字符串内不要出现换行、不要用中文引号、不要有未转义的引号；释义与音标都保持一行。
"""


def _collect_missing() -> list[str]:
    """Words the pages print that nothing in the project can explain.

    Sentence text and explanation text are weighed differently for very short
    tokens: a model-written sentence never contains a stray fragment, so a
    two-letter word there is a real word ("ta", "me") and gets an entry; the
    same two letters inside Chinese prose are usually noise ("加 ons", "v.")
    and are skipped. Both cases are skipped when the renderer would not link
    them anyway.
    """
    dictionary = Dictionary(ROOT / "dict" / "starter.json")
    missing: dict[str, int] = {}

    for path in sorted((ROOT / "data").glob("2026-*.json")):
        if path.name == "index.json":
            continue
        day = json.loads(path.read_text(encoding="utf-8"))
        texts: list[tuple[str, bool]] = []  # (text, is_sentence)
        for passage in day.get("passages", []):
            for s in passage.get("sentences", []):
                texts.append((s.get("text", ""), True))
                texts.append((s.get("grammar_note") or "", False))
                texts.extend(
                    (str(v), False) for v in (s.get("grammar_notes") or {}).values()
                )
                for lesson in s.get("grammar_lessons") or []:
                    texts.append((lesson.get("t") or "", False))
                    texts.append((lesson.get("b") or "", False))
        for text, is_sentence in texts:
            for token in _tokens(text):
                key = token.lower()
                root = H._CONTRACT_PREFIX_RE.sub("", key)
                if dictionary.lookup_local(root) or dictionary.lookup_local(key):
                    continue
                if conjug.find_form(root) or conjug.find_form(key):
                    continue
                if root in H._NUM_KEYS or key in H._NUM_KEYS:
                    continue
                if len(token) <= 2 and not is_sentence:
                    continue
                missing[root] = missing.get(root, 0) + 1

    return sorted(missing, key=lambda w: (-missing[w], w))


def _tokens(text: str):
    """The renderer's own tokenization: IPA spans and hyphen-affixes excluded."""
    pos = 0
    pieces: list[str] = []
    for m in H._IPA_SPAN_RE.finditer(text):
        pieces.append(text[pos:m.start()])
        pos = m.end()
    pieces.append(text[pos:])
    for seg in pieces:
        for m in H._FR_WORD_RE.finditer(seg):
            s, e = m.span()
            if (s > 0 and seg[s - 1] in H._AFFIX_DASH) or (
                e < len(seg) and seg[e] in H._AFFIX_DASH
            ):
                continue
            yield m.group(0)


def _ask(words: list[str]) -> dict[str, dict]:
    prompt = (
        SYSTEM_RULES
        + "\n要处理的词（共 %d 个）：\n%s\n" % (len(words), "、".join(words))
        + "\n只输出 JSON 对象。"
    )
    for budget in (llm.MAX_TOKENS, llm.MAX_TOKENS_RETRY):
        try:
            data = llm._post(prompt, budget, 600)
        except Exception as exc:  # a malformed reply must not sink the run
            log.warning("  解析失败（%s），换更大额度重试", type(exc).__name__)
            continue
        # _post already parses the reply into the JSON object itself — it is the
        # word→entry mapping, not a wrapper carrying a "content" field.
        if not isinstance(data, dict):
            continue
        clean: dict[str, dict] = {}
        for word, entry in data.items():
            wl = str(word).lower().strip()
            if not isinstance(entry, dict) or wl not in words:
                continue
            clean[wl] = {
                "pos": str(entry.get("pos", ""))[:8],
                "ipa": str(entry.get("ipa", ""))[:40],
                "def": str(entry.get("def", ""))[:60],
            }
        if clean:
            return clean
    return {}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只报告缺失词，不调用 LLM")
    args = ap.parse_args()

    missing = _collect_missing()
    log.info("待补词 %d 个：%s", len(missing), "、".join(missing))

    if not missing:
        return 0
    if args.dry_run:
        return 0

    existing: dict[str, dict] = {}
    if AUTO_PATH.exists():
        existing = json.loads(AUTO_PATH.read_text(encoding="utf-8"))
    todo = [w for w in missing if w not in existing]
    log.info("其中 %d 个是新词（auto.json 已有 %d 条）", len(todo), len(existing))

    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        log.info("请求第 %d 批（%d 词）…", i // BATCH + 1, len(chunk))
        try:
            got = _ask(chunk)
        except Exception as exc:  # one bad batch must not sink the rest
            log.warning("  这一批失败：%r", exc)
            continue
        log.info("  返回 %d / %d 条", len(got), len(chunk))
        existing.update(got)

    kept = {k: v for k, v in sorted(existing.items()) if v.get("def")}
    AUTO_PATH.write_text(
        json.dumps(kept, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    log.info("写入 %s（%d 条）", AUTO_PATH.name, len(kept))
    still = [w for w in missing if w not in kept]
    if still:
        log.warning("仍缺 %d 个：%s", len(still), "、".join(still))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
