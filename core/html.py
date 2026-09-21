"""HTML renderer: Day object → self-contained HTML page, one sentence per page.

Layout is modeled on dailybrief's deck (build_site.py):
  - .deck-track / .deck-slide → horizontal scroll-snap deck, ONE sentence per page
  - .deck-ctl                 → ‹ 1/N › buttons, arrow keys, touch swipe
  - crossing either end of the deck jumps to the neighbouring day's page

Each page is one sentence card holding the *complete* analysis:
  - French line (large, serif, clickable words + liaison marks)
  - Chinese translation
  - Per-sentence audio player with 0.5x / 0.75x / 1x speed
  - 语法解析: a one-line overview plus expandable teaching cards
    (Sentence.grammar_lessons) written for a reader rebuilding grammar basics
  - Click any word for a dictionary bubble: IPA, part of speech, definition,
    and an example sentence with its own IPA and Chinese translation
  - Number 1-100 lookup for any number word
  - Per-sentence collection (sentence-level bookmarking)

Word lookup is resolved at render time from dict/starter.json + dict/curated.json,
so adding a dictionary entry fixes every already-generated page at once.

Pure f-string templating, zero runtime dependencies.
"""
from __future__ import annotations

import html as html_mod
import json
import re
from pathlib import Path

from core import conjug
from core.models import Day, Sentence
from core.dict_lookup import Dictionary, segment, _CONTRACT_PREFIX_RE

ROOT = Path(__file__).resolve().parent.parent

_DICT_INSTANCE: Dictionary | None = None


def esc(s: object) -> str:
    return html_mod.escape(str(s or ""), quote=True)


SPK_SVG = (
    '<svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true">'
    '<path fill="currentColor" d="M3 9v6h4l5 4V5L7 9H3z"/>'
    '<path fill="currentColor" opacity=".5" d="M16.4 12a4.4 4.4 0 0 0-2.4-3.9v7.8A4.4 4.4 0 0 0 16.4 12z"/>'
    '<path fill="currentColor" opacity=".5" d="M14 3.6v2.1a6.4 6.4 0 0 1 0 12.6v2.1a8.5 8.5 0 0 0 0-16.8z"/>'
    "</svg>"
)


def _spk(text: str) -> str:
    """A small speaker inline after a transcription — no box, just the icon."""
    return (
        '<button class="spk" type="button" data-say="' + esc(text) + '"'
        ' title="听发音" aria-label="听发音">' + SPK_SVG + "</button>"
    )


# ═══════════════════════════════════════════════════════════════════════════
# CSS — French paper theme, one sentence per deck slide
# ═══════════════════════════════════════════════════════════════════════════

CSS = r"""*{box-sizing:border-box;margin:0;padding:0}

:root{
  color-scheme:light; /* tell the browser our form controls are light-themed */
  /* ── French paper palette: cream stock, burgundy, muted tricolore ── */
  --paper:#fbf6ee;--card:#fffdf8;--card-2:#f7f0e2;--cream:#f2e9d8;
  --ink:#2f2721;--ink-soft:#6a5c4e;--ink-faint:#a1937f;
  --rouge:#b04a3f;--rouge-soft:#c9705f;
  --bleu:#3f5f86;--bleu-soft:#7d99bd;
  --gold:#b8954a;--gold-soft:#dcc48e;
  --ok:#6f9a74;
  --line:#e8dcc7;--line-soft:#f2ead9;
  --sh-sm:0 1px 2px rgba(47,39,33,.05),0 10px 24px -14px rgba(47,39,33,.20);
  --sh-lg:0 2px 6px rgba(47,39,33,.06),0 24px 48px -22px rgba(47,39,33,.28);
  --r:16px;--r-sm:10px;
  --f-display:"Playfair Display","Noto Serif SC","Songti SC",Georgia,serif;
  --f-serif:"Cormorant Garamond","Noto Serif CJK SC","Songti SC",Georgia,serif;
  --f-zh:"Noto Serif CJK SC","Songti SC","STSong","SimSun",Georgia,serif;
  --f-ui:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;
}

html{scroll-behavior:smooth}
body{
  font:16px/1.8 var(--f-serif);
  background:var(--paper);
  background-image:
    radial-gradient(ellipse at 12% 0%,rgba(63,95,134,.055) 0%,transparent 46%),
    radial-gradient(ellipse at 88% 8%,rgba(176,74,63,.05) 0%,transparent 42%),
    radial-gradient(ellipse at 50% 100%,rgba(184,149,74,.05) 0%,transparent 55%);
  color:var(--ink);
  padding:0 0 72px;
  -webkit-font-smoothing:antialiased;
}
html.nav-away body{opacity:.4;transition:opacity .12s ease}

/* ── Header ── */
.site-header{text-align:center;padding:34px 20px 16px;position:relative}
.site-header::after{
  content:"";position:absolute;left:0;right:0;bottom:0;height:1px;
  background:linear-gradient(90deg,transparent,var(--line) 20%,var(--line) 80%,transparent);
}
.brand{
  font-family:var(--f-display);font-size:31px;font-weight:700;
  letter-spacing:.6px;line-height:1.1;
}
.brand .b-bleu{color:var(--bleu)}
.brand .b-rouge{color:var(--rouge);font-style:italic}
.brand-fr{
  font-family:var(--f-serif);font-style:italic;font-size:14px;
  color:var(--ink-faint);margin-top:5px;letter-spacing:1.4px;
}
/* Tricolore ribbon under the masthead — the one loud French gesture. */
.tricolore{
  display:flex;width:72px;height:3px;margin:13px auto 0;
  border-radius:2px;overflow:hidden;box-shadow:0 1px 2px rgba(47,39,33,.12);
}
.tricolore i{flex:1;display:block}
.tricolore i:nth-child(1){background:var(--bleu)}
.tricolore i:nth-child(2){background:var(--gold)}
.tricolore i:nth-child(3){background:var(--rouge)}

.header-meta{
  display:flex;align-items:center;justify-content:center;
  gap:10px;margin-top:14px;flex-wrap:wrap;
}
.chip{
  display:inline-flex;align-items:center;gap:6px;
  background:var(--card);border:1px solid var(--line);border-radius:999px;
  padding:5px 14px;font-family:var(--f-ui);font-size:12.5px;
  color:var(--ink-soft);letter-spacing:.4px;
}
.chip .streak-count{font-weight:700;color:var(--rouge)}
.streak-fire{font-size:14px;display:inline-block}
.streak-fire.animate{animation:flame 1.6s ease-in-out infinite}
@keyframes flame{
  0%,100%{transform:scale(1) rotate(0deg)}
  25%{transform:scale(1.16) rotate(-4deg)}
  50%{transform:scale(1.04) rotate(0deg)}
  75%{transform:scale(1.12) rotate(4deg)}
}

/* ── Layout ── */
.wrap{max-width:720px;margin:0 auto;padding:0 16px}

/* ══ Deck: one sentence per page ══
   The track is a horizontally scrollable flex row with mandatory snap points,
   so touch swipe and the ‹ › buttons share one position model. */
.deck{position:relative;margin-top:18px}
.deck-track{
  display:flex;align-items:flex-start;gap:16px;
  overflow-x:auto;overscroll-behavior-x:contain;
  scroll-snap-type:x mandatory;scrollbar-width:none;
  padding:3px 2px 14px;-webkit-overflow-scrolling:touch;
}
.deck-track::-webkit-scrollbar{display:none}
.deck-slide{flex:0 0 100%;min-width:0;scroll-snap-align:center}

/* ── Sentence card ── */
.sentence-card{
  position:relative;background:var(--card);
  border:1px solid var(--line);border-radius:var(--r);
  box-shadow:var(--sh-sm);overflow:hidden;
  padding-bottom:22px;
  transition:box-shadow .2s ease,transform .2s ease;
}
.deck-slide:not(.is-current) .sentence-card{box-shadow:none}
.sentence-card:hover{box-shadow:var(--sh-lg);transform:translateY(-2px)}
/* Tricolore hairline across the top of every card. */
.sentence-card::before{
  content:"";position:absolute;top:0;left:0;right:0;height:3px;
  background:linear-gradient(90deg,
    var(--bleu) 0 33.33%,var(--gold) 33.33% 66.66%,var(--rouge) 66.66% 100%);
  opacity:.9;
}

.card-topbar{
  display:flex;align-items:center;gap:10px;
  padding:16px 20px 0;
}
.level-badge{
  font-family:var(--f-ui);font-size:10px;font-weight:700;
  letter-spacing:1px;padding:3px 10px;border-radius:999px;
}
.level-A1{background:#e2eef7;color:#2f5d82}
.level-A2{background:#e3efe2;color:#3d6b45}
.level-B1{background:#f6ecd6;color:#8a6a24}
.level-B2{background:#f8e2de;color:#9c4436}
/* ── 行内小喇叭 ──
   Sits right after a transcription (or right after the word when there is no
   transcription), like the horn in a dictionary entry. No box, no border. */
.spk{
  appearance:none;display:inline-flex;align-items:center;justify-content:center;
  width:19px;height:19px;margin-left:3px;padding:0;
  border:0;border-radius:50%;background:none;color:var(--ink-faint);
  vertical-align:-4px;cursor:pointer;flex:none;
  transition:color .15s ease,background .15s ease,transform .15s ease;
}
.spk svg{display:block;width:13px;height:13px}
.spk:hover{color:var(--rouge);background:rgba(176,74,63,.10)}
.spk:active{transform:scale(.86)}
.card-collect{
  margin-left:auto;appearance:none;background:none;
  border:1px solid transparent;color:var(--ink-faint);
  width:30px;height:30px;border-radius:50%;cursor:pointer;
  font-size:15px;line-height:1;padding:0;
  display:inline-flex;align-items:center;justify-content:center;
  transition:all .2s ease;
}
.card-collect:hover{color:var(--gold);border-color:var(--gold-soft)}
.card-collect.collected{
  color:var(--gold);border-color:var(--gold);
  background:rgba(184,149,74,.12);
}

/* ── The French line ── */
.verse{position:relative;padding:20px 26px 4px}
.verse .guillemet{
  position:absolute;left:10px;top:6px;font-family:var(--f-display);
  font-size:54px;line-height:1;color:var(--gold-soft);
  opacity:.55;user-select:none;pointer-events:none;
}
.fr-text{
  font-family:var(--f-serif);font-size:24px;line-height:1.72;
  letter-spacing:.01em;color:var(--ink);text-align:center;
}
.fr-text .word{
  cursor:pointer;padding:0 1px;border-bottom:1px dashed transparent;
  border-radius:2px;transition:color .15s ease,background .15s ease,border-color .15s ease;
}
.fr-text .word:hover{
  color:var(--rouge);border-bottom-color:var(--rouge-soft);
  background:rgba(176,74,63,.06);
}
.fr-text .word[data-unknown="true"]{
  color:var(--ink-soft);border-bottom-color:transparent;
}
.fr-text .word[data-unknown="true"]:hover{
  color:var(--bleu);border-bottom-color:var(--bleu-soft);
  background:rgba(63,95,134,.06);
}
.fr-text .liaison{
  color:var(--bleu);font-size:.72em;vertical-align:.14em;
  opacity:.8;pointer-events:none;
}

.zh{
  font-family:var(--f-zh);font-size:15.5px;line-height:1.85;
  color:var(--ink-soft);text-align:center;padding:2px 26px 0;
}

/* ── Ornamental rule ── */
.rule{
  display:flex;align-items:center;justify-content:center;gap:12px;
  margin:18px 24px 0;color:var(--gold);font-size:13px;opacity:.85;
  user-select:none;
}
.rule::before,.rule::after{
  content:"";flex:1;height:1px;
  background:linear-gradient(90deg,transparent,var(--line),transparent);
}

/* ── Audio ── */
.audio-row{
  display:flex;align-items:center;gap:10px;flex-wrap:wrap;
  margin:16px 20px 0;padding:10px 12px;
  background:var(--card-2);border:1px solid var(--line-soft);
  border-radius:var(--r-sm);
}
.audio-row audio{flex:1;min-width:150px;height:34px}
.speed-group{display:flex;gap:5px;flex-shrink:0}
.speed-btn{
  appearance:none;background:var(--card);border:1px solid var(--line);
  color:var(--ink-soft);border-radius:999px;padding:4px 11px;
  font-family:var(--f-ui);font-size:11px;cursor:pointer;
  transition:all .18s ease;
}
.speed-btn:hover{border-color:var(--gold);color:var(--ink)}
.speed-btn.active{background:var(--rouge);color:#fff;border-color:var(--rouge)}
.audio-error{margin-top:6px;font-family:var(--f-ui);font-size:12px}
.audio-error span{color:var(--rouge);cursor:pointer}

/* ── Analysis sections ── */
.seg{margin:20px 20px 0}
.lb{
  display:flex;align-items:center;gap:9px;margin-bottom:10px;
  font-family:var(--f-ui);font-size:11px;letter-spacing:1.5px;
  text-transform:uppercase;color:var(--ink-faint);
}
.lb::after{content:"";flex:1;height:1px;background:var(--line-soft)}
.lb .lb-fr{text-transform:none;letter-spacing:.6px;font-style:italic;color:var(--gold)}

.grammar-note{
  font-family:var(--f-zh);font-size:14.5px;line-height:1.9;
  color:var(--ink-soft);padding:11px 15px;
  background:var(--card-2);border-left:3px solid var(--gold-soft);
  border-radius:0 var(--r-sm) var(--r-sm) 0;
}
/* ── 语法课程（可展开的讲解卡片） ── */
.lessons{margin-top:12px;padding-top:12px;border-top:1px dashed var(--line-soft)}
.lessons>summary{
  list-style:none;cursor:pointer;user-select:none;
  display:inline-flex;align-items:center;gap:8px;
  padding:7px 15px;border-radius:999px;
  background:var(--card-2);border:1px solid var(--line);
  font-family:var(--f-ui);font-size:12.5px;color:var(--rouge);
  transition:all .18s ease;
}
.lessons>summary::-webkit-details-marker{display:none}
.lessons>summary::marker{content:""}
.lessons>summary:hover{border-color:var(--rouge-soft)}
.lessons>summary:focus-visible{outline:2px solid var(--rouge);outline-offset:2px}
.lessons>summary::after{
  content:"\25be";font-size:10px;opacity:.75;
  transition:transform .18s ease;
}
.lessons[open]>summary::after{transform:rotate(180deg)}
.lessons[open]>summary{margin-bottom:14px}
.lessons .cnt{font-family:var(--f-ui);font-size:11.5px;color:var(--ink-faint)}
.lessons .tg-close{display:none}
.lessons[open] .tg-open{display:none}
.lessons[open] .tg-close{display:inline}
.lesson-list{list-style:none;counter-reset:lesson}
.lesson{
  counter-increment:lesson;position:relative;margin-bottom:10px;
  padding:12px 15px 13px 45px;background:var(--card-2);
  border:1px solid var(--line-soft);border-radius:var(--r-sm);
}
.lesson:last-child{margin-bottom:0}
.lesson::before{
  content:counter(lesson);position:absolute;left:13px;top:12px;
  width:22px;height:22px;border-radius:50%;
  background:var(--rouge);color:#fff;
  font:600 11px/1 var(--f-ui);
  display:flex;align-items:center;justify-content:center;
}
.lesson-t{
  font-family:var(--f-zh);font-size:14.5px;font-weight:700;
  line-height:1.6;color:var(--ink);margin-bottom:6px;
}
.lesson-b{
  font-family:var(--f-zh);font-size:13.8px;line-height:1.95;
  color:var(--ink-soft);
}
.lesson-b+.lesson-b{margin-top:4px}
.lesson-b em{font-style:normal;color:var(--rouge);font-weight:600}

/* ── 表格：变位课的主角和对照表 ── */
.lg-table{
  margin:12px 0 4px;padding:0;background:var(--card);
  border:1px solid var(--line);border-radius:var(--r-sm);overflow:hidden;
}
.lg-table figcaption{
  padding:9px 13px 8px;background:var(--cream);
  border-bottom:1px solid var(--line-soft);
  font-family:var(--f-ui);font-size:10.5px;letter-spacing:1px;
  text-transform:uppercase;color:var(--ink-faint);
}
.lg-table figcaption .tb-fr{
  text-transform:none;letter-spacing:.3px;font-style:italic;
  color:var(--gold);margin-left:7px;
}
.tb-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.lg-table table{
  width:100%;border-collapse:collapse;
  font-family:var(--f-ui);font-size:13px;
}
.lg-table th{
  text-align:left;padding:7px 13px;white-space:nowrap;
  font-size:10px;font-weight:600;letter-spacing:.8px;text-transform:uppercase;
  color:var(--ink-faint);border-bottom:1px solid var(--line);
}
.lg-table td{
  padding:7px 13px;color:var(--ink-soft);vertical-align:middle;
  border-bottom:1px solid var(--line-soft);
}
.lg-table tbody tr:last-child td{border-bottom:none}
.lg-table tbody tr:nth-child(even){background:rgba(184,149,74,.05)}
.lg-table td:first-child{
  font-family:var(--f-serif);font-size:14px;color:var(--ink-faint);
  white-space:nowrap;
}
.lg-table td.tb-ipa{
  font-family:var(--f-ui);font-size:12px;font-style:italic;
  color:var(--bleu);white-space:nowrap;
}
.lg-table td .word{
  font-family:var(--f-serif);font-size:16px;font-weight:600;color:var(--ink);
}
.lg-table td.tb-ipa .spk{vertical-align:-2px}
.lg-table .tb-note{
  margin:0;padding:9px 13px 11px;border-top:1px dashed var(--line-soft);
  font-family:var(--f-zh);font-size:12.5px;line-height:1.75;color:var(--ink-faint);
}

/* ══ Deck controls ══ */
.deck-ctl{
  display:flex;align-items:center;justify-content:center;gap:16px;
  margin-top:6px;min-height:42px;
}
.deck-btn{
  appearance:none;background:var(--card);border:1px solid var(--line);
  color:var(--ink-soft);border-radius:999px;width:42px;height:42px;
  cursor:pointer;box-shadow:var(--sh-sm);
  font:22px/1 var(--f-display);padding-bottom:4px;
  display:inline-flex;align-items:center;justify-content:center;
  transition:all .18s ease;
}
.deck-btn:hover:not([disabled]){
  color:var(--rouge);border-color:var(--rouge-soft);transform:translateY(-1px);
}
.deck-btn:focus-visible{outline:2px solid var(--rouge);outline-offset:2px}
.deck-btn[disabled]{opacity:.28;cursor:default}
.deck-pos{
  font-family:var(--f-ui);font-size:13px;letter-spacing:1.4px;
  color:var(--ink-faint);min-width:66px;text-align:center;
}
.deck-dots{display:flex;gap:8px;justify-content:center;margin-top:14px}
.deck-dot{
  appearance:none;padding:0;width:7px;height:7px;border-radius:50%;
  border:1px solid var(--line);background:transparent;cursor:pointer;
  transition:all .2s ease;
}
.deck-dot:hover{border-color:var(--rouge-soft)}
.deck-dot.active{
  background:var(--rouge);border-color:var(--rouge);transform:scale(1.3);
}
.progress-bar{
  height:3px;border-radius:2px;background:var(--line-soft);
  margin:16px 18px 0;overflow:hidden;
}
.progress-fill{
  height:100%;border-radius:2px;transition:width .4s ease;
  background:linear-gradient(90deg,var(--bleu),var(--gold),var(--rouge));
}
.deck-hint{
  text-align:center;font-family:var(--f-ui);font-size:11.5px;
  color:var(--ink-faint);margin-top:10px;letter-spacing:.3px;
}

/* ── Archive ── */
.archive-section{
  margin-top:30px;padding:16px 20px;background:var(--card);
  border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--sh-sm);
}
.archive-title{
  font-family:var(--f-ui);font-size:11px;letter-spacing:1.5px;
  text-transform:uppercase;color:var(--ink-faint);margin-bottom:11px;
}
.archive-list{display:flex;flex-wrap:wrap;gap:8px}
.archive-link{
  display:inline-block;padding:5px 12px;background:var(--cream);
  border:1px solid var(--line);border-radius:8px;
  font-family:var(--f-ui);font-size:12.5px;color:var(--ink-soft);
  text-decoration:none;transition:all .18s ease;
}
.archive-link:hover{background:var(--card-2);color:var(--ink)}
.archive-link.current{background:var(--ink);color:var(--paper);border-color:var(--ink)}

/* ── Floating collect button ── */
.fab-group{position:fixed;bottom:20px;right:20px;z-index:400}
.fab{
  position:relative;width:48px;height:48px;border-radius:50%;
  background:var(--card);border:1px solid var(--line);color:var(--ink-soft);
  font-size:19px;cursor:pointer;box-shadow:var(--sh-lg);
  display:inline-flex;align-items:center;justify-content:center;
  transition:all .22s ease;
}
.fab:hover{color:var(--rouge);transform:translateY(-2px)}
.fab-badge{
  position:absolute;top:-4px;right:-4px;display:none;
  min-width:18px;height:18px;padding:0 5px;border-radius:9px;
  background:var(--rouge);color:#fff;
  font-family:var(--f-ui);font-size:10px;font-weight:600;
  align-items:center;justify-content:center;
}
.fab-badge.has-items{display:inline-flex}

/* ── Collection panel ── */
.collect-overlay{
  position:fixed;inset:0;z-index:499;background:rgba(47,39,33,.18);
  opacity:0;pointer-events:none;transition:opacity .3s ease;
}
.collect-overlay.open{opacity:1;pointer-events:auto}
.collect-panel{
  position:fixed;left:0;right:0;bottom:0;z-index:500;max-height:56vh;
  display:flex;flex-direction:column;
  transform:translateY(100%);
  transition:transform .35s cubic-bezier(.4,0,.2,1);
}
.collect-panel.open{transform:translateY(0)}
.collect-panel-header{
  display:flex;align-items:center;justify-content:space-between;
  padding:14px 24px;background:var(--card);
  border:1px solid var(--line);border-bottom:none;
  border-radius:var(--r) var(--r) 0 0;box-shadow:var(--sh-sm);
}
.collect-panel-title{
  font-family:var(--f-display);font-size:18px;font-weight:700;color:var(--ink);
}
.collect-panel-count{
  font-family:var(--f-ui);font-size:12px;color:var(--ink-faint);margin-left:8px;
}
.collect-panel-close{
  appearance:none;background:none;border:none;color:var(--ink-faint);
  font-size:22px;line-height:1;cursor:pointer;padding:0 4px;
  transition:color .2s ease;
}
.collect-panel-close:hover{color:var(--ink)}
.collect-panel-body{
  flex:1;overflow-y:auto;padding:6px 0;background:var(--card);
  border:1px solid var(--line);border-top:none;
  border-radius:0 0 var(--r) var(--r);box-shadow:var(--sh-sm);
}
.collect-item{
  position:relative;padding:14px 44px 14px 24px;
  border-bottom:1px solid var(--line-soft);transition:background .15s ease;
}
.collect-item:last-child{border-bottom:none}
.collect-item:hover{background:var(--card-2)}
.collect-item-fr{
  font-family:var(--f-serif);font-size:17px;line-height:1.7;color:var(--ink);
}
.collect-item-zh{
  font-family:var(--f-zh);font-size:13.5px;line-height:1.7;
  color:var(--ink-soft);margin-top:4px;
}
.collect-item-date{
  font-family:var(--f-ui);font-size:11px;color:var(--ink-faint);margin-top:4px;
}
.collect-item-remove{
  position:absolute;top:12px;right:16px;appearance:none;background:none;
  border:none;color:var(--ink-faint);font-size:14px;cursor:pointer;
  padding:2px 6px;transition:color .2s ease;
}
.collect-item-remove:hover{color:var(--rouge)}
.collect-empty{
  text-align:center;padding:42px 20px;color:var(--ink-faint);
  font-family:var(--f-zh);font-style:italic;font-size:14.5px;
}

/* ── Tooltip / number popup ── */
.dict-tooltip{
  position:fixed;z-index:1000;display:none;width:min(336px,92vw);
  max-height:min(80vh,660px);overflow-y:auto;overscroll-behavior:contain;
  padding:14px 17px;background:rgba(255,253,248,.98);
  -webkit-backdrop-filter:blur(12px);backdrop-filter:blur(12px);
  border:1px solid var(--line);border-radius:var(--r-sm);
  box-shadow:var(--sh-lg);
}
.dict-tooltip.visible{display:block}
.dict-tooltip .dt-word{
  font-family:var(--f-serif);font-size:19px;font-weight:700;color:var(--ink);
}
.dict-tooltip .dt-ipa{
  font-family:var(--f-ui);font-size:12px;font-style:italic;
  color:var(--bleu);margin-bottom:3px;
}
.dict-tooltip .dt-pos{
  font-family:var(--f-ui);font-size:10px;letter-spacing:1px;
  text-transform:uppercase;color:var(--rouge);margin-bottom:6px;
}
.dict-tooltip .dt-def{
  font-family:var(--f-zh);font-size:14.5px;line-height:1.7;color:var(--ink-soft);
}
.dict-tooltip .dt-dim{font-style:italic;color:var(--ink-faint);font-size:13.5px}
/* 例句：加粗放大 + 音标 + 中文翻译 */
.dict-tooltip .dt-example{
  margin-top:10px;padding-top:10px;
  border-top:1px dashed var(--line-soft);
}
.dict-tooltip .dt-ex-label{
  display:block;margin-bottom:3px;
  font-family:var(--f-ui);font-size:9.5px;letter-spacing:1.3px;
  text-transform:uppercase;color:var(--ink-faint);
}
.dict-tooltip .dt-ex-fr{
  display:block;font-family:var(--f-serif);
  font-size:18px;font-weight:700;line-height:1.5;color:var(--ink);
  letter-spacing:.01em;
}
.dict-tooltip .dt-ex-ipa{
  display:block;margin-top:2px;
  font-family:var(--f-ui);font-size:12px;font-style:italic;color:var(--bleu);
}
.dict-tooltip .dt-ex-zh{
  display:block;margin-top:4px;
  font-family:var(--f-zh);font-size:13.5px;line-height:1.7;color:var(--ink-soft);
}
.dict-tooltip .dt-note{
  font-family:var(--f-zh);font-size:12.5px;line-height:1.7;
  color:var(--gold);margin-top:7px;padding-top:7px;
  border-top:1px dashed var(--line-soft);
}
.dict-tooltip .dt-more{
  appearance:none;margin:8px 0 0;background:none;border:none;
  padding:0;font-family:var(--f-ui);font-size:12px;color:var(--rouge);
  cursor:pointer;text-decoration:underline;
}

/* ── 变位面板（查词气泡里的动词部分） ── */
.dt-conj{
  margin-top:10px;padding-top:9px;border-top:1px dashed var(--line-soft);
}
.dt-cj-head{display:flex;align-items:baseline;gap:7px;flex-wrap:wrap}
.dt-cj-inf{font-family:var(--f-serif);font-size:17px;font-weight:700;color:var(--rouge)}
.dt-cj-ipa{font-family:var(--f-ui);font-size:12px;font-style:italic;color:var(--bleu)}
.dt-cj-tag{
  font-family:var(--f-ui);font-size:9.5px;letter-spacing:.6px;
  color:var(--ink-faint);background:var(--cream);border-radius:4px;padding:2px 6px;
}
.dt-cj-mean{
  font-family:var(--f-zh);font-size:12.5px;line-height:1.6;
  color:var(--ink-soft);margin-top:3px;
}
.dt-cj-now{
  font-family:var(--f-ui);font-size:11.5px;color:var(--gold);
  margin-top:5px;letter-spacing:.2px;
}
.dt-cj-tabs{display:flex;flex-wrap:wrap;gap:4px;margin-top:8px}
.dt-cj-tab{
  appearance:none;padding:3px 9px;border-radius:999px;
  background:var(--card-2);border:1px solid var(--line);color:var(--ink-faint);
  font-family:var(--f-ui);font-size:11px;cursor:pointer;transition:all .15s ease;
}
.dt-cj-tab:hover{border-color:var(--rouge-soft);color:var(--ink)}
.dt-cj-tab.on{background:var(--rouge);border-color:var(--rouge);color:#fff}
table.cj-table{
  width:100%;border-collapse:collapse;margin-top:7px;
  font-family:var(--f-ui);font-size:12.5px;
}
.cj-table th{
  text-align:left;padding:4px 6px;border-bottom:1px solid var(--line);
  font-size:9.5px;font-weight:600;letter-spacing:.7px;
  text-transform:uppercase;color:var(--ink-faint);
}
.cj-table td{padding:4px 6px;border-bottom:1px solid var(--line-soft);color:var(--ink-soft)}
.cj-table tr:last-child td{border-bottom:none}
.cj-table tbody tr{cursor:pointer}
.cj-table tbody tr:hover{background:var(--card-2)}
.cj-table tr.hit{background:rgba(176,74,63,.09)}
.cj-table tr.hit td{color:var(--ink)}
.cj-table .cj-pron{
  font-family:var(--f-serif);font-size:13px;color:var(--ink-faint);white-space:nowrap;
}
.cj-table .cj-form{
  font-family:var(--f-serif);font-size:15px;font-weight:600;color:var(--ink);white-space:nowrap;
}
.cj-table .cj-ipa{font-size:11.5px;font-style:italic;color:var(--bleu)}
.cj-table .cj-ipa .spk{margin-left:2px}
.cj-note{
  margin-top:6px;font-family:var(--f-zh);font-size:12px;
  line-height:1.65;color:var(--ink-faint);
}

.number-popup{
  position:fixed;z-index:1000;display:none;max-width:330px;
  padding:14px 17px;background:rgba(255,253,248,.98);
  -webkit-backdrop-filter:blur(12px);backdrop-filter:blur(12px);
  border:1px solid var(--line);border-radius:var(--r-sm);
  box-shadow:var(--sh-lg);
}
.number-popup.visible{display:block}
.number-popup .num-header{
  font-family:var(--f-display);font-size:17px;font-weight:700;
  color:var(--ink);margin-bottom:8px;
}
.num-search{
  width:100%;padding:7px 11px;margin-bottom:9px;
  background:var(--paper);border:1px solid var(--line);border-radius:7px;
  font-family:var(--f-ui);font-size:13px;color:var(--ink);
}
.num-search:focus{outline:none;border-color:var(--gold)}
.num-grid{display:grid;grid-template-columns:repeat(10,1fr);gap:4px}
.num-cell{
  text-align:center;padding:4px 2px;border-radius:5px;
  font-family:var(--f-ui);font-size:11.5px;color:var(--ink-soft);
  cursor:pointer;transition:all .15s ease;
}
.num-cell:hover{background:var(--cream);color:var(--rouge)}

/* ── Toast / empty ── */
.toast{
  position:fixed;top:20px;left:50%;z-index:2000;
  transform:translateX(-50%) translateY(-140%);
  padding:14px 26px;background:var(--card);
  border:1px solid var(--ok);border-radius:var(--r);
  box-shadow:var(--sh-lg);font-family:var(--f-ui);font-size:13.5px;
  color:var(--ok);white-space:nowrap;transition:transform .4s cubic-bezier(.4,0,.2,1);
}
.toast.show{transform:translateX(-50%) translateY(0)}
.empty-day{
  padding:56px 24px;text-align:center;background:var(--card);
  border:1px solid var(--line);border-radius:var(--r);
  font-family:var(--f-zh);color:var(--ink-faint);
}

/* ── Responsive ── */
@media(max-width:760px){
  body{padding:0 0 56px}
  .wrap{padding:0 12px;max-width:100%}
  .site-header{padding:24px 16px 14px}
  .brand{font-size:25px}
  .deck-track{gap:12px;padding:3px 0 12px}
  .sentence-card{padding-bottom:18px}
  .card-topbar{padding:14px 16px 0}
  .verse{padding:18px 18px 4px}
  .verse .guillemet{font-size:42px;left:4px;top:4px}
  .fr-text{font-size:20.5px;line-height:1.78}
  .zh{font-size:14.5px;padding:2px 18px 0}
  .rule{margin:16px 16px 0}
  .audio-row{margin:14px 16px 0;flex-direction:column;align-items:stretch}
  /* In a column, the base rule's `flex:1` sets flex-basis to 0% on the main
     axis, which is height here — the player would collapse out of sight. */
  .audio-row audio{width:100%;flex:none;height:34px}
  .seg{margin:18px 16px 0}
  .lesson{padding:12px 13px 13px 42px}
  .lesson::before{left:11px;width:21px;height:21px}
  .lesson-t{font-size:14px}
  .lesson-b{font-size:13.5px;line-height:1.92}
  .lg-table th,.lg-table td{padding:6px 9px}
  .lg-table td .word{font-size:15px}
  .deck-btn{width:46px;height:46px;font-size:24px}
  .collect-panel{max-height:66vh}
  .dict-tooltip{width:min(320px,94vw)}
  .header-meta{gap:7px}
  .skin-switch{margin-top:10px}
}

@media(prefers-reduced-motion:reduce){
  *{animation-duration:0s!important;transition-duration:0s!important}
  html{scroll-behavior:auto}
  .sentence-card:hover{transform:none}
}

@media(prefers-color-scheme:dark){
  :root{
    color-scheme:dark; /* native audio player / scrollbars go dark too */
    --paper:#17130f;--card:#241e17;--card-2:#2c251b;--cream:#312919;
    --ink:#eee4d4;--ink-soft:#c8b8a0;--ink-faint:#9c8d77;
    --rouge:#d98a7e;--rouge-soft:#b3665a;
    --bleu:#9db4d4;--bleu-soft:#5d7799;
    --gold:#cbaa63;--gold-soft:#8a7645;
    --ok:#8ab88e;
    --line:#40372c;--line-soft:#322a20;
    --sh-sm:0 1px 2px rgba(0,0,0,.35),0 12px 26px -14px rgba(0,0,0,.6);
    --sh-lg:0 2px 6px rgba(0,0,0,.45),0 26px 50px -22px rgba(0,0,0,.75);
  }
  .level-A1{background:#1c2a36;color:#8fb8d6}
  .level-A2{background:#1c2a1e;color:#8ab87a}
  .level-B1{background:#332a17;color:#d9b96a}
  .level-B2{background:#33201c;color:#d98a7e}
  .dict-tooltip,.number-popup{background:rgba(36,30,23,.98)}
  .collect-item:hover{background:var(--card-2)}
  .archive-link.current{color:var(--paper)}
  /* Pastel rouge under white text fails contrast on a dark card. */
  .speed-btn.active{color:#241511}
}

/* ── 外观切换（两种皮肤都显示） ── */
.skin-switch{
  display:flex;align-items:center;justify-content:center;gap:6px;
  margin-top:13px;font-family:var(--f-ui);font-size:11px;
}
.skin-switch-label{
  color:var(--ink-faint);letter-spacing:1.4px;margin-right:2px;opacity:.8;
}
.skin-switch button{
  appearance:none;background:transparent;border:1px solid var(--line);
  border-radius:999px;padding:3px 12px;cursor:pointer;
  font-family:var(--f-ui);font-size:11px;color:var(--ink-faint);
  transition:all .18s ease;
}
.skin-switch button:hover{border-color:var(--gold);color:var(--ink)}
html[data-skin="francais"] .skin-switch button[data-skin-pick="francais"],
html[data-skin="classique"] .skin-switch button[data-skin-pick="classique"]{
  background:var(--ink);border-color:var(--ink);color:var(--paper);
}
"""


# ═══════════════════════════════════════════════════════════════════════════
# Skin «français» — layer two, opt-in
#
# The CSS above *is* the `classique` skin, byte for byte what the page looked
# like before. Everything in this block lives under html[data-skin="francais"]
# so the two never fight, and flipping the attribute (plus one localStorage
# entry) switches the whole page. That is the "开口": nothing here touches
# classique, so if the new look is not wanted it is one attribute away.
#
# The intent is a French book page: laid paper, a double rule under the
# masthead, a gold hairline frame inset inside the card, small-caps section
# labels opening with a fleuron, and the tricolore reduced to a ribbon in the
# top-centre of each card and a fixed progress ribbon across the viewport.
# ═══════════════════════════════════════════════════════════════════════════

CSS_SKIN_FR = r"""
html[data-skin="francais"]{
  --paper:#f2e9d7;--card:#fffdf6;--card-2:#f6eedd;--cream:#e9dcc2;
  --ink:#2a2118;--ink-soft:#5f5140;--ink-faint:#9a886c;
  --rouge:#a1372b;--rouge-soft:#c06a58;
  --bleu:#2c4c78;--bleu-soft:#7d99bd;
  --gold:#a5853a;--gold-soft:#d8c08a;
  --ok:#5f8a63;
  --line:#d5c4a4;--line-soft:#eaddc4;
  --sh-sm:0 1px 0 rgba(42,33,24,.05),0 8px 18px -14px rgba(42,33,24,.30);
  --sh-lg:0 1px 0 rgba(42,33,24,.06),0 20px 40px -26px rgba(42,33,24,.42);
  --r:3px;--r-sm:2px;
}

html[data-skin="francais"] body{
  background-color:var(--paper);
  background-image:
    radial-gradient(ellipse at 18% -8%,rgba(44,76,120,.055),transparent 52%),
    radial-gradient(ellipse at 86% 4%,rgba(161,55,43,.05),transparent 48%),
    radial-gradient(ellipse at 50% 104%,rgba(165,133,58,.06),transparent 58%),
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='150' height='150'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='4'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='150' height='150' filter='url(%23n)' opacity='0.07'/%3E%3C/svg%3E");
  background-size:auto,auto,auto,150px 150px;
  background-blend-mode:normal,normal,normal,multiply;
}

/* ── Masthead: French book title page ── */
html[data-skin="francais"] .site-header{padding:40px 20px 24px}
html[data-skin="francais"] .site-header::after{
  background:var(--line);height:3px;opacity:.55;bottom:0;
}
html[data-skin="francais"] .site-header::before{
  content:"";position:absolute;left:0;right:0;bottom:5px;height:1px;
  background:var(--line);
}
html[data-skin="francais"] .brand{
  font-size:35px;letter-spacing:3px;font-weight:600;
}
html[data-skin="francais"] .brand-fr{
  font-family:var(--f-ui);font-style:normal;font-size:10px;
  letter-spacing:3.4px;text-transform:uppercase;color:var(--gold);
  margin-top:9px;
}
html[data-skin="francais"] .tricolore{
  width:104px;height:2px;border-radius:0;margin-top:15px;box-shadow:none;
}
html[data-skin="francais"] .header-meta{gap:14px;margin-top:17px}
html[data-skin="francais"] .chip{
  background:transparent;border:none;border-bottom:1px solid var(--line);
  border-radius:0;padding:0 1px 2px;
  font-family:var(--f-serif);font-size:13px;letter-spacing:1.2px;
  color:var(--ink-soft);
}
html[data-skin="francais"] .skin-switch{margin-top:17px}

/* ── Card = a leaf of paper with a gold rule inset ── */
html[data-skin="francais"] .sentence-card{
  border:1px solid var(--line);border-radius:0;
  box-shadow:var(--sh-sm);padding-bottom:26px;
}
html[data-skin="francais"] .sentence-card:hover{transform:none;box-shadow:var(--sh-lg)}
html[data-skin="francais"] .sentence-card::before{
  left:50%;right:auto;width:66px;height:2px;top:12px;
  transform:translateX(-50%);opacity:1;
  background:linear-gradient(90deg,
    var(--bleu) 0 33.33%,var(--gold) 33.33% 66.66%,var(--rouge) 66.66% 100%);
}
html[data-skin="francais"] .sentence-card::after{
  content:"";position:absolute;inset:6px;pointer-events:none;
  border:1px solid rgba(165,133,58,.30);
}
html[data-skin="francais"] .card-topbar{padding:28px 26px 0}
html[data-skin="francais"] .level-badge{
  background:transparent;border:1px solid currentColor;border-radius:2px;
  letter-spacing:1.6px;padding:2px 8px;
}

/* The French line: bigger, centred, opened by a lettrine-like guillemet */
html[data-skin="francais"] .verse{padding:24px 34px 6px}
html[data-skin="francais"] .verse .guillemet{
  left:16px;top:10px;font-size:64px;color:var(--gold-soft);opacity:.7;
}
html[data-skin="francais"] .fr-text{font-size:25px;line-height:1.7}
html[data-skin="francais"] .zh{font-size:15.5px;padding:4px 34px 0}
html[data-skin="francais"] .rule{margin:20px 30px 0;font-size:14px}

/* Audio becomes an engraved plate */
html[data-skin="francais"] .audio-row{
  margin:18px 26px 0;background:var(--card-2);
  border:1px solid var(--line);border-radius:0;
}
html[data-skin="francais"] .speed-btn{border-radius:2px}
html[data-skin="francais"] .speed-btn.active{
  background:var(--ink);border-color:var(--ink);color:var(--paper);
}

/* ── Section labels: small caps, opened by a fleuron ── */
html[data-skin="francais"] .seg{margin:22px 26px 0}
html[data-skin="francais"] .lb{
  font-family:var(--f-serif);font-variant:small-caps;
  font-size:13.5px;letter-spacing:2.4px;color:var(--ink-soft);
}
html[data-skin="francais"] .lb::before{
  content:"\2767";color:var(--gold);font-size:14px;letter-spacing:0;
  font-variant:normal;line-height:1;
}
html[data-skin="francais"] .lb .lb-fr{
  font-size:11px;letter-spacing:.6px;color:var(--gold);
}
html[data-skin="francais"] .grammar-note{
  background:transparent;border-left:2px solid var(--gold-soft);
  border-radius:0;padding:2px 0 2px 14px;
}

/* Numbered lessons get gold seals */
html[data-skin="francais"] .lessons{margin-top:14px;padding-top:14px}
html[data-skin="francais"] .lessons>summary{
  border-radius:2px;background:transparent;border-color:var(--line);
  font-family:var(--f-serif);font-size:13px;letter-spacing:1.1px;
  color:var(--rouge);
}
html[data-skin="francais"] .lesson{
  background:var(--card);border:1px solid var(--line-soft);
  border-radius:0;box-shadow:1px 1px 0 rgba(42,33,24,.04);
}
html[data-skin="francais"] .lesson::before{
  background:var(--gold);color:#fff;font-family:var(--f-display);
  font-weight:700;border-radius:50%;
}
html[data-skin="francais"] .lesson-t{font-weight:700}
html[data-skin="francais"] .lesson-b{color:var(--ink-soft)}

/* Tables: a leaf inside a leaf */
html[data-skin="francais"] .lg-table{border-radius:0;background:var(--card)}
html[data-skin="francais"] .lg-table figcaption{
  background:transparent;border-bottom:1px solid var(--line);
  font-family:var(--f-serif);font-variant:small-caps;
  font-size:12.5px;letter-spacing:1.6px;color:var(--ink-soft);
  text-transform:none;
}
html[data-skin="francais"] .lg-table th{
  font-family:var(--f-serif);font-variant:small-caps;
  font-size:12px;letter-spacing:1.2px;text-transform:none;color:var(--ink-faint);
}
html[data-skin="francais"] .lg-table tbody tr:nth-child(even){
  background:rgba(165,133,58,.055);
}
html[data-skin="francais"] .lg-table td:first-child{font-style:italic}

/* ── Deck controls as ringed medallions ── */
html[data-skin="francais"] .deck-btn{
  border:1px solid var(--gold-soft);background:var(--card);box-shadow:none;
  font-size:20px;
}
html[data-skin="francais"] .deck-btn:hover:not([disabled]){
  background:var(--cream);color:var(--rouge);transform:none;
}
html[data-skin="francais"] .deck-pos{
  font-family:var(--f-serif);font-style:italic;font-size:15px;
  letter-spacing:.8px;color:var(--ink-faint);
}
html[data-skin="francais"] .deck-dot{border-radius:1px;width:8px;height:4px}
html[data-skin="francais"] .deck-dot.active{
  background:var(--gold);border-color:var(--gold);transform:none;width:18px;
}
html[data-skin="francais"] .deck-hint{letter-spacing:.6px}
/* The progress bar becomes the tricolore ribbon across the top of the viewport */
html[data-skin="francais"] .progress-bar{
  position:fixed;top:0;left:0;right:0;height:3px;
  margin:0;border-radius:0;background:rgba(42,33,24,.07);z-index:600;
}
html[data-skin="francais"] .progress-fill{border-radius:0}

/* ── Archive as index cards, panels as endpapers ── */
html[data-skin="francais"] .archive-section{
  border-radius:0;border-color:var(--line);box-shadow:var(--sh-sm);
}
html[data-skin="francais"] .archive-title{
  font-family:var(--f-serif);font-variant:small-caps;
  font-size:12.5px;letter-spacing:2px;text-transform:none;color:var(--ink-faint);
}
html[data-skin="francais"] .archive-link{
  border-radius:1px;background:var(--card);border-color:var(--line);
  font-family:var(--f-serif);font-size:13.5px;letter-spacing:.6px;
}
html[data-skin="francais"] .archive-link.current{
  background:var(--ink);border-color:var(--ink);
}
html[data-skin="francais"] .collect-panel-header,
html[data-skin="francais"] .collect-panel-body{border-radius:0}
html[data-skin="francais"] .collect-panel-title{
  font-size:19px;letter-spacing:1.4px;
}
html[data-skin="francais"] .collect-item-fr{font-size:18px}

/* Skin-specific table/tooltip touches */
html[data-skin="francais"] .dict-tooltip,
html[data-skin="francais"] .number-popup{border-radius:0}
html[data-skin="francais"] .dt-cj-tab,
html[data-skin="francais"] .spk:hover{border-radius:2px}

/* ── classique: the pre-existing look, kept exactly ── */
html[data-skin="classique"] .chip-date-fr{display:none}

@media(max-width:760px){
  html[data-skin="francais"] .site-header{padding:28px 16px 18px}
  html[data-skin="francais"] .brand{font-size:27px;letter-spacing:2px}
  html[data-skin="francais"] .card-topbar{padding:24px 18px 0}
  html[data-skin="francais"] .verse{padding:20px 22px 4px}
  html[data-skin="francais"] .verse .guillemet{font-size:48px;left:8px;top:6px}
  html[data-skin="francais"] .fr-text{font-size:21px}
  html[data-skin="francais"] .zh{padding:4px 22px 0}
  html[data-skin="francais"] .seg{margin:20px 18px 0}
  html[data-skin="francais"] .rule{margin:18px 20px 0}
  html[data-skin="francais"] .audio-row{margin:16px 18px 0}
  html[data-skin="francais"] .header-meta{gap:11px}
}

@media(prefers-color-scheme:dark){
  html[data-skin="francais"]{
    color-scheme:dark;
    --paper:#15110c;--card:#231d15;--card-2:#2b2418;--cream:#312919;
    --ink:#f0e5cf;--ink-soft:#cab99e;--ink-faint:#9d8e77;
    --rouge:#d98a7e;--rouge-soft:#a8655a;
    --bleu:#9db4d4;--bleu-soft:#5d7799;
    --gold:#c9a961;--gold-soft:#7d6a3e;
    --ok:#8ab88e;
    --line:#40372a;--line-soft:#2f2819;
    --sh-sm:0 1px 0 rgba(0,0,0,.4),0 10px 22px -14px rgba(0,0,0,.7);
    --sh-lg:0 2px 6px rgba(0,0,0,.5),0 22px 44px -24px rgba(0,0,0,.85);
  }
  /* Laid paper does not survive a dark background — drop the grain. */
  html[data-skin="francais"] body{
    background-image:
      radial-gradient(ellipse at 18% -8%,rgba(44,76,120,.10),transparent 52%),
      radial-gradient(ellipse at 86% 4%,rgba(161,55,43,.08),transparent 48%);
    background-size:auto,auto;
    background-blend-mode:normal;
  }
  html[data-skin="francais"] .sentence-card::after{
    border-color:rgba(201,169,97,.22);
  }
  html[data-skin="francais"] .dict-tooltip,
  html[data-skin="francais"] .number-popup{background:rgba(35,29,21,.98)}
  /* The tricolore ribbon reads as a smear on a dark viewport — mute it. */
  html[data-skin="francais"] .progress-fill{opacity:.55;filter:saturate(.8)}
  html[data-skin="francais"] .progress-bar{background:rgba(240,229,207,.06)}
  html[data-skin="francais"] .speed-btn.active{color:#241511}
}
"""


# ═══════════════════════════════════════════════════════════════════════════
# JavaScript
# ═══════════════════════════════════════════════════════════════════════════

JS_LOOKUP = r"""<script>
/* Word lookup tooltip + conjugation panel + number table + speech synthesis.
   The conjugation data is generated from core/conjug.py at render time, so a
   verb form tapped inside a lesson and the same form tapped inside the sentence
   always read from one table. */
(function(){
"use strict";
/* All page data lives in the window.__X__ block above; read it there rather
   than interpolating the JSON a second time — the payload is large enough that
   a duplicate copy was doubling the page weight. */
var DICT = window.__DICT__ || {};
var NUMBERS = window.__NUMBERS__ || {};

/* Pre-generated audio (edge_tts, synthesized at build time). Devices without
   a French TTS voice — Chinese Android ROMs, Windows sans French voice pack —
   would read French with an English voice, so the page prefers these mp3s
   and only falls back to on-device speechSynthesis. */
var FRAUDIOS = null;
if(window.fetch){
  fetch("audio/w/index.json").then(function(r){ return r.ok ? r.json() : null; })
    .then(function(j){ if(j && typeof j === "object") FRAUDIOS = j; })
    .catch(function(){});
}

function numWord(v, k){
  /* NUMBER_TABLE values look like "vingt /vɛ̃t/" — speak only the word. */
  var i = (v || "").indexOf(" /");
  return i > 0 ? v.slice(0, i) : (v || k);
}
var GRAMMAR = window.__GRAMMAR_NOTES__ || {};
var CONJ = window.__CONJ__ || {};
var VBOOK = window.__VBOOK__ || {};
var CMETA = window.__CMETA__ || { tabs: {}, labels: {}, persons: [] };

function esc(s){var d=document.createElement("div");d.textContent=(s==null?"":String(s));return d.innerHTML;}

/* The horn that sits after a transcription. Server-rendered lesson tables use
   the exact same markup, so one delegated handler covers both. */
var SPK_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true">' +
  '<path fill="currentColor" d="M3 9v6h4l5 4V5L7 9H3z"/>' +
  '<path fill="currentColor" opacity=".5" d="M16.4 12a4.4 4.4 0 0 0-2.4-3.9v7.8A4.4 4.4 0 0 0 16.4 12z"/>' +
  '<path fill="currentColor" opacity=".5" d="M14 3.6v2.1a6.4 6.4 0 0 1 0 12.6v2.1a8.5 8.5 0 0 0 0-16.8z"/></svg>';
function spkBtn(text){
  return '<button class="spk" type="button" data-say="' + esc(text) +
         '" title="听发音" aria-label="听发音">' + SPK_SVG + '</button>';
}

var tip = document.createElement("div");
tip.className = "dict-tooltip";
document.body.appendChild(tip);

var numPopup = document.createElement("div");
numPopup.className = "number-popup";
numPopup.innerHTML = '<div class="num-header">数字表 · Nombres</div>' +
  '<input type="text" class="num-search" placeholder="搜索数字或法语..." autocomplete="off">' +
  '<div class="num-grid" id="num-grid"></div>';
document.body.appendChild(numPopup);

var numGrid = numPopup.querySelector("#num-grid");
var numSearch = numPopup.querySelector(".num-search");

/* Everything the currently open bubble needs to redraw itself. */
var tipState = null;

function renderNumbers(filter){
  var out = "";
  var keys = Object.keys(NUMBERS).sort(function(a,b){ return parseInt(a,10) - parseInt(b,10); });
  for(var k=0;k<keys.length;k++){
    var key = keys[k], val = NUMBERS[key] || "";
    if(filter && val.toLowerCase().indexOf(filter.toLowerCase()) === -1 && key !== filter) continue;
    out += '<div class="num-cell" data-num="' + esc(key) + '">' + esc(key) + '</div>';
  }
  numGrid.innerHTML = out;
  var cells = numGrid.querySelectorAll(".num-cell");
  for(var c=0;c<cells.length;c++){
    (function(cell){
      cell.addEventListener("click", function(){
        var nk = cell.getAttribute("data-num");
        tip.innerHTML = '<div class="dt-word">' + esc(nk) + '</div>' +
          '<div class="dt-ipa">' + esc(NUMBERS[nk] || "") + spkBtn(numWord(NUMBERS[nk], nk)) + '</div>';
        tip.classList.add("visible");
        placeTooltip(cell, tip);
        numPopup.classList.remove("visible");
      });
    })(cells[c]);
  }
}
renderNumbers("");
numSearch.addEventListener("input", function(){ renderNumbers(this.value.trim()); });

/* Voices load asynchronously; u.lang alone is only a hint and Windows/Android
   frequently ignores it, reading French words with the default (often English)
   voice. Pick a real French voice explicitly and refresh it when the list
   arrives. */
var FR_VOICE = null;
function pickVoice(){
  var vs = window.speechSynthesis.getVoices() || [];
  FR_VOICE = null;
  for(var i = 0; i < vs.length; i++){
    var l = (vs[i].lang || "").toLowerCase().replace("_", "-");
    if(l === "fr-fr"){ FR_VOICE = vs[i]; return; }
  }
  for(var j = 0; j < vs.length; j++){
    if((vs[j].lang || "").toLowerCase().indexOf("fr") === 0){ FR_VOICE = vs[j]; return; }
  }
}
if("speechSynthesis" in window){
  pickVoice();
  window.speechSynthesis.onvoiceschanged = pickVoice;
}

function speak(word){
  if(!word) return;
  var m = FRAUDIOS ? FRAUDIOS[word] : null;
  if(m){
    try{
      var a = new Audio(m);
      var fell = false;
      var fb = function(){ if(fell) return; fell = true; ttsSpeak(word); };
      a.onerror = fb;
      var p = a.play();
      if(p && p.catch) p.catch(fb);
      return;
    }catch(e){}
  }
  ttsSpeak(word);
}

function ttsSpeak(word){
  if(!("speechSynthesis" in window)) return;
  try{
    if(!FR_VOICE) pickVoice();
    var u = new SpeechSynthesisUtterance(word);
    u.lang = "fr-FR";
    if(FR_VOICE) u.voice = FR_VOICE;
    u.rate = 0.82;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  }catch(e){}
}

/* ── Conjugation panel ─────────────────────────────────────────────────────
   Shown whenever the tapped form is a known conjugation. Tapping "fais" in a
   lesson body used to be impossible; now it gives the person, the tense, the
   whole table and a 🔊 for every line. */
function tenseLabel(key){
  var l = CMETA.labels[key];
  return l ? l[0] : key;
}
function tabLabel(key){
  return CMETA.tabs[key] || tenseLabel(key);
}
function describe(entries){
  var e = entries[0];
  if(e.t === "infinitif") return "动词原形 · Infinitif";
  if(e.t === "participe") return "过去分词 · Participe passé";
  var persons = [];
  for(var i=0;i<entries.length;i++){
    if(entries[i].t === e.t && entries[i].i >= 0){
      var p = CMETA.persons[entries[i].i] || "";
      if(persons.indexOf(p) === -1) persons.push(p);
    }
  }
  var out = tenseLabel(e.t);
  if(persons.length) out += " · " + persons.join(" / ") + "同形";
  return out;
}
function conjPanelHTML(key, forceTense){
  var entries = CONJ[key];
  if(!entries || !entries.length) return "";
  var e = entries[0];
  var v = VBOOK[e.v];
  if(!v) return "";
  // A participle or an infinitive has no table of its own — show the present.
  var tense = forceTense && v.tenses[forceTense] ? forceTense
            : (v.tenses[e.t] ? e.t : "present");
  var block = v.tenses[tense];

  var h = '<div class="dt-conj">';
  h += '<div class="dt-cj-head"><span class="dt-cj-inf" lang="fr">' + esc(e.v) + '</span>';
  if(v.inf_ipa) h += '<span class="dt-cj-ipa">' + esc(v.inf_ipa) + spkBtn(e.v) + '</span>';
  h += '<span class="dt-cj-tag">第 ' + esc(v.group) + ' 组</span></div>';
  if(v.mean) h += '<div class="dt-cj-mean">' + esc(v.mean) + '</div>';
  h += '<div class="dt-cj-now">' + esc(describe(entries)) + '</div>';

  var keys = [];
  for(var k in v.tenses){ if(Object.prototype.hasOwnProperty.call(v.tenses, k)) keys.push(k); }
  if(keys.length > 1){
    h += '<div class="dt-cj-tabs">';
    for(var t=0;t<keys.length;t++){
      h += '<button class="dt-cj-tab' + (keys[t] === tense ? " on" : "") +
           '" type="button" data-tense="' + esc(keys[t]) + '">' +
           esc(tabLabel(keys[t])) + '</button>';
    }
    h += '</div>';
  }

  if(block){
    h += '<table class="cj-table"><thead><tr><th>人称</th><th>变位</th><th>读音</th></tr></thead><tbody>';
    for(var r=0;r<block.rows.length;r++){
      var row = block.rows[r];
      var hit = (tense === e.t && row[1].toLowerCase() === key) ? ' class="hit"' : '';
      var line = row[0] + " " + row[1];
      h += '<tr' + hit + ' data-speak="' + esc(line) + '">' +
           '<td class="cj-pron">' + esc(row[0]) + '</td>' +
           '<td class="cj-form" lang="fr">' + esc(row[1]) + '</td>' +
           '<td class="cj-ipa">' + esc(row[2] || "") + spkBtn(line) + '</td></tr>';
    }
    h += '</tbody></table>';
  }

  if(v.note) h += '<div class="cj-note">' + esc(v.note) + '</div>';
  h += '</div>';
  return h;
}

function placeTooltip(anchor, box){
  var r = anchor.getBoundingClientRect();
  var w = box.offsetWidth;
  var left = r.left + r.width / 2 - w / 2;
  if(left < 8) left = 8;
  if(left + w > window.innerWidth - 8) left = window.innerWidth - w - 8;
  box.style.left = left + "px";
  var top = r.bottom + 8;
  var h = box.offsetHeight;
  if(top + h > window.innerHeight - 8) top = Math.max(8, r.top - h - 8);
  box.style.top = top + "px";
}

function showWordTip(el){
  var key = el.getAttribute("data-word");
  var orig = el.getAttribute("data-orig") || key;
  var card = el.closest(".sentence-card");

  // A form may be indexed under the stripped root ("apprends") or verbatim.
  var cjKey = null;
  if(CONJ[key]) cjKey = key;
  else if(CONJ[orig.toLowerCase()]) cjKey = orig.toLowerCase();

  tipState = {
    el: el,
    anchor: el,
    key: key,
    orig: orig,
    sid: card ? card.getAttribute("data-sid") : null,
    isNum: el.getAttribute("data-is-num") === "true",
    hasDict: el.getAttribute("data-has-dict") === "true",
    cjKey: cjKey,
    tense: null
  };
  renderTip();
}

/* Build the bubble body from tipState. Kept separate so the tense tabs can
   rebuild it in place without re-deriving anything. */
function renderTip(){
  var st = tipState;
  if(!st) return;
  var key = st.key, orig = st.orig, html = "";

  /* The horn always rides on the line it pronounces: right after the headword's
     transcription, right after the example's. Nothing to press at the bottom. */
  var horn = spkBtn(orig);

  if(st.isNum && NUMBERS[key]){
    html = '<div class="dt-word">' + esc(orig) + '</div>' +
           '<div class="dt-ipa">' + esc(NUMBERS[key]) + spkBtn(numWord(NUMBERS[key], key)) + '</div>' +
           '<button class="dt-more" type="button">查看 1-100 数字表</button>';
  } else if(st.hasDict && DICT[key]){
    var d = DICT[key];
    html = '<div class="dt-word">' + esc(orig) + (d.ipa ? '' : horn) + '</div>' +
           (d.ipa ? '<div class="dt-ipa">' + esc(d.ipa) + horn + '</div>' : '') +
           (d.pos ? '<div class="dt-pos">' + esc(d.pos) + '</div>' : '') +
           (d.def ? '<div class="dt-def">' + esc(d.def) + '</div>' : '');
    // The conjugation sits directly under the meaning: if you tapped a verb
    // form, the table is what you came for — the example goes below it.
    if(st.cjKey) html += conjPanelHTML(st.cjKey, st.tense);
    if(d.example){
      html += '<div class="dt-example">' +
        '<span class="dt-ex-label">例句</span>' +
        '<span class="dt-ex-fr" lang="fr">' + esc(d.example) + '</span>' +
        (d.example_ipa ? '<span class="dt-ex-ipa">' + esc(d.example_ipa) + spkBtn(d.example) + '</span>'
                       : '<span class="dt-ex-ipa">' + spkBtn(d.example) + '</span>') +
        (d.example_zh ? '<span class="dt-ex-zh">' + esc(d.example_zh) + '</span>' : '') +
        '</div>';
    }
    var note = null;
    if(st.sid && GRAMMAR[st.sid]) note = GRAMMAR[st.sid][key] || GRAMMAR[st.sid][orig] || null;
    if(note) html += '<div class="dt-note">' + esc(note) + '</div>';
  } else if(st.cjKey){
    // No dictionary entry, but we still know exactly what this form is.
    html = '<div class="dt-word">' + esc(orig) + horn + '</div>' +
           conjPanelHTML(st.cjKey, st.tense);
  } else {
    html = '<div class="dt-word">' + esc(orig) + horn + '</div>' +
           '<div class="dt-def dt-dim">这个词暂未收录释义</div>';
  }
  tip.innerHTML = html;
  tip.classList.add("visible");
  placeTooltip(st.anchor, tip);

  var more = tip.querySelector(".dt-more");
  if(more) more.addEventListener("click", function(e){
    e.stopPropagation();
    openNumberPopup(st.anchor);
  });
  bindConjPanel();
}

/* Wire the pieces inside a freshly rendered conjugation panel. */
function bindConjPanel(){
  var panel = tip.querySelector(".dt-conj");
  if(!panel) return;

  var tabs = panel.querySelectorAll(".dt-cj-tab");
  for(var t=0;t<tabs.length;t++){
    tabs[t].addEventListener("click", function(e){
      e.stopPropagation();
      tipState.tense = this.getAttribute("data-tense");
      renderTip();
    });
  }

  var rows = panel.querySelectorAll("tbody tr");
  for(var r=0;r<rows.length;r++){
    rows[r].addEventListener("click", function(e){
      e.stopPropagation();
      var txt = this.getAttribute("data-speak");
      if(txt) speak(txt);
    });
  }
}

function openNumberPopup(anchor){
  var r = anchor.getBoundingClientRect();
  var w = numPopup.offsetWidth || 330;
  var left = Math.min(r.left, window.innerWidth - w - 10);
  numPopup.style.left = Math.max(8, left) + "px";
  numPopup.style.top = (r.bottom + 10) + "px";
  numSearch.value = "";
  renderNumbers("");
  numPopup.classList.add("visible");
  tip.classList.remove("visible");
  try{ numSearch.focus(); }catch(e){}
}

document.addEventListener("click", function(e){
  var t = e.target;
  // The horn — after a transcription in a lesson table, in the bubble, anywhere.
  var horn = t.closest ? t.closest(".spk") : null;
  if(horn){
    e.preventDefault();
    e.stopPropagation();
    speak(horn.getAttribute("data-say") || "");
    return;
  }
  var word = t.closest ? t.closest(".word") : null;
  if(word){
    e.preventDefault();
    e.stopPropagation();
    showWordTip(word);
    return;
  }
  if(t.closest && t.closest(".dict-tooltip")) return;
  tip.classList.remove("visible");
  tipState = null;
  if(!(t.closest && t.closest(".number-popup"))) numPopup.classList.remove("visible");
});

document.addEventListener("keydown", function(e){
  if(e.key === "Escape"){
    tip.classList.remove("visible");
    tipState = null;
    numPopup.classList.remove("visible");
  }
});
})();
</script>"""


JS_COLLECTION = r"""<script>
/* Sentence collection ("句本") — localStorage-backed */
(function(){
"use strict";
var SENTENCES = window.__SENTENCES__ || {};
var STORAGE_KEY = "frenchdaily_collections";
var panel, overlay, badge;

function esc(s){var d=document.createElement("div");d.textContent=(s==null?"":String(s));return d.innerHTML;}
function getCols(){ try{ return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}"); }catch(e){ return {}; } }
function saveCols(d){ try{ localStorage.setItem(STORAGE_KEY, JSON.stringify(d)); }catch(e){} }

function init(){
  panel = document.getElementById("collect-panel");
  overlay = document.getElementById("collect-overlay");
  badge = document.getElementById("collect-badge");
  var btns = document.querySelectorAll(".card-collect");
  for(var i=0;i<btns.length;i++){
    btns[i].addEventListener("click", function(){ toggleCollect(this.getAttribute("data-sid"), this); });
  }
  var fab = document.getElementById("collect-fab");
  if(fab) fab.addEventListener("click", openPanel);
  if(panel) panel.querySelector(".collect-panel-close").addEventListener("click", closePanel);
  if(overlay) overlay.addEventListener("click", closePanel);
  updateAllButtons();
  updateBadge();
}

function toggleCollect(sid, btn){
  if(!sid) return;
  var cols = getCols(), entry = SENTENCES[sid];
  if(!entry) return;
  if(cols[sid]){
    delete cols[sid];
    if(btn) btn.classList.remove("collected");
  } else {
    cols[sid] = entry;
    if(btn) btn.classList.add("collected");
  }
  saveCols(cols);
  updateBadge();
  renderPanel();
}

function updateAllButtons(){
  var cols = getCols();
  var btns = document.querySelectorAll(".card-collect");
  for(var i=0;i<btns.length;i++){
    var sid = btns[i].getAttribute("data-sid");
    if(cols[sid]) btns[i].classList.add("collected");
    else btns[i].classList.remove("collected");
  }
}

function updateBadge(){
  var n = Object.keys(getCols()).length;
  if(!badge) return;
  badge.textContent = n > 0 ? String(n) : "";
  badge.className = "fab-badge" + (n > 0 ? " has-items" : "");
}

function openPanel(){ renderPanel(); panel.classList.add("open"); overlay.classList.add("open"); }
function closePanel(){ panel.classList.remove("open"); overlay.classList.remove("open"); }

function renderPanel(){
  var body = document.getElementById("collect-panel-body");
  if(!body) return;
  var cols = getCols();
  var sids = Object.keys(cols);
  var countEl = document.getElementById("collect-count");
  if(countEl) countEl.textContent = sids.length ? "· " + sids.length + " 句" : "";
  if(!sids.length){ body.innerHTML = '<div class="collect-empty">还没有收藏的句子</div>'; return; }
  var html = "";
  for(var i=0;i<sids.length;i++){
    var sid = sids[i], s = cols[sid];
    html += '<div class="collect-item">' +
      '<button class="collect-item-remove" data-remove="' + esc(sid) + '" title="移除">×</button>' +
      '<div class="collect-item-fr">' + esc(s.text) + '</div>' +
      '<div class="collect-item-zh">' + esc(s.translation) + '</div>' +
      '<div class="collect-item-date">' + esc(s.date) + '</div></div>';
  }
  body.innerHTML = html;
  var rms = body.querySelectorAll(".collect-item-remove");
  for(var r=0;r<rms.length;r++){
    rms[r].addEventListener("click", function(){
      var sid = this.getAttribute("data-remove");
      var cols = getCols();
      delete cols[sid];
      saveCols(cols);
      updateAllButtons();
      updateBadge();
      renderPanel();
    });
  }
}

if(document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
else init();
})();
</script>"""


JS_DECK = r"""<script>
/* Deck navigation — one sentence per page.
   Buttons, arrow keys and touch swipe all funnel into go(); the scroll-snap
   track owns the position, so there is only ever one source of truth. */
(function(){
"use strict";
var track = document.querySelector(".deck-track");
if(!track || !track.children.length) return;

var slides = track.children;
var N = slides.length;
var prev = document.getElementById("deck-prev");
var next = document.getElementById("deck-next");
var posEl = document.getElementById("deck-pos");
var ctl = document.querySelector(".deck-ctl");
var bar = document.getElementById("progress");
var dots = Array.prototype.slice.call(document.querySelectorAll(".deck-dot"));
var older = track.getAttribute("data-older") || "";
var newer = track.getAttribute("data-newer") || "";
var maxH = 0, lastI = -1;

function measure(){
  maxH = 0;
  for(var k=0;k<N;k++){
    var h = slides[k].offsetHeight;
    if(h > maxH) maxH = h;
  }
}

function idx(){
  var w = track.clientWidth || 1;
  var i = Math.round(track.scrollLeft / w);
  if(i < 0) i = 0;
  if(i > N-1) i = N-1;
  return i;
}

function jump(href){
  document.documentElement.classList.add("nav-away");
  location.href = href;
}

function dayLabel(href){
  var m = /(\d{4})-(\d{2})-(\d{2})/.exec(href);
  return m ? (parseInt(m[2],10)) + "月" + (parseInt(m[3],10)) + "日" : "相邻一天";
}

function update(){
  var i = idx();
  if(posEl) posEl.textContent = (i+1) + " / " + N;
  for(var d=0;d<dots.length;d++) dots[d].classList.toggle("active", d === i);
  for(var s=0;s<N;s++) slides[s].classList.toggle("is-current", s === i);

  var head = (i <= 0), tail = (i >= N-1);
  if(prev){
    prev.disabled = head && !newer;
    prev.title = (head && newer) ? "上一天：" + dayLabel(newer) : "上一句 · Précédent";
    prev.setAttribute("aria-label", prev.title);
  }
  if(next){
    next.disabled = tail && !older;
    next.title = (tail && older) ? "下一天：" + dayLabel(older) : "下一句 · Suivant";
    next.setAttribute("aria-label", next.title);
  }
  if(bar) bar.style.width = ((i+1) / N * 100).toFixed(1) + "%";

  if(i !== lastI){
    lastI = i;
    /* Closing the page closes its course. A 解析 left open on a slide you
       swiped away from keeps the track that tall — a couple thousand pixels
       of blank air under the short card you are reading now. Reopening it is
       one tap whenever you swipe back. */
    for(var p=0;p<N;p++){
      if(p === i) continue;
      var opened = slides[p].querySelectorAll("details[open]");
      for(var q=0;q<opened.length;q++) opened[q].open = false;
    }
    measure();
    /* New page: if the card's top has scrolled out of view, bring it back
       upward only — otherwise a tall previous card leaves the new one starting
       halfway down the screen. */
    var top = slides[i].getBoundingClientRect().top + window.scrollY - 10;
    if(top > 0 && window.scrollY > top) window.scrollTo(0, top);
    try{
      document.dispatchEvent(new CustomEvent("deck:change", { detail: { index: i, total: N } }));
    }catch(e){}
  }

  /* Slides differ in height but the track is as tall as the tallest one.
     measure() above ran after any collapse, so the controls can sit right on
     the current card's bottom edge on every viewport. */
  if(ctl && slides[i]){
    ctl.style.marginTop = (6 - (maxH - slides[i].offsetHeight)) + "px";
  }
}

function go(i){
  if(i > N-1){
    if(older) return jump(older);
    i = N-1;
  } else if(i < 0){
    if(newer) return jump(newer + "#last");
    i = 0;
  }
  track.scrollTo({ left: i * track.clientWidth, behavior: "smooth" });
}

if(prev) prev.addEventListener("click", function(){ go(idx() - 1); });
if(next) next.addEventListener("click", function(){ go(idx() + 1); });
for(var d=0;d<dots.length;d++){
  (function(dot){
    dot.addEventListener("click", function(){ go(parseInt(dot.getAttribute("data-idx"), 10)); });
  })(dots[d]);
}

track.addEventListener("scroll", update, { passive: true });

/* Expanding/collapsing the grammar course changes the card's height, and the
   control row's margin is computed from those heights — so re-measure.
   `toggle` does not bubble, hence the capture phase. */
track.addEventListener("toggle", function(){ measure(); update(); }, true);

document.addEventListener("keydown", function(e){
  var t = e.target;
  if(t && t.tagName && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return;
  if(e.key === "ArrowRight"){ go(idx() + 1); e.preventDefault(); }
  else if(e.key === "ArrowLeft"){ go(idx() - 1); e.preventDefault(); }
});

/* Swiping past either end crosses into the neighbouring day. The track already
   contains overscroll, so a deliberate 70px outward drag past the edge is the
   signal; direction logic stays in go(). */
var sx = 0, sy = 0, dragging = false;
track.addEventListener("touchstart", function(e){
  if(e.touches.length !== 1) return;
  dragging = true;
  sx = e.touches[0].clientX;
  sy = e.touches[0].clientY;
}, { passive: true });
track.addEventListener("touchmove", function(e){
  if(!dragging) return;
  var dx = e.touches[0].clientX - sx, dy = e.touches[0].clientY - sy;
  if(Math.abs(dx) < 70 || Math.abs(dx) < Math.abs(dy) * 1.5) return;
  dragging = false;
  var edge = track.scrollWidth - track.clientWidth - 2;
  if(dx < 0 && track.scrollLeft >= edge) go(N);
  else if(dx > 0 && track.scrollLeft <= 2) go(-1);
}, { passive: true });
track.addEventListener("touchend", function(){ dragging = false; }, { passive: true });

measure();
if(location.hash === "#last" && N > 1){
  track.scrollLeft = (N-1) * track.clientWidth;
  try{ history.replaceState(null, "", location.pathname + location.search); }catch(e){}
}
update();
window.addEventListener("resize", function(){ measure(); update(); }, { passive: true });
/* Web fonts change every card's height after the first paint — the initial
   measure() above ran against fallback serif. */
if(document.fonts && document.fonts.ready){
  document.fonts.ready.then(function(){ measure(); update(); });
}
})();
</script>"""



JS_SKIN = """<script>
/* Appearance switch. Both skins ship inside one page — the new "francais" look
   and the previous "classique" one — and the choice sticks in localStorage, so
   a reload (or a jump to another day) keeps it. */
(function(){
"use strict";
var KEY = "frenchdaily_skin";
var root = document.documentElement;

function apply(name){
  if(name !== "francais" && name !== "classique") name = "francais";
  root.setAttribute("data-skin", name);
  try{ localStorage.setItem(KEY, name); }catch(e){}
  var btns = document.querySelectorAll("[data-skin-pick]");
  for(var i=0;i<btns.length;i++){
    var on = btns[i].getAttribute("data-skin-pick") === name;
    btns[i].setAttribute("aria-pressed", on ? "true" : "false");
    btns[i].classList.toggle("on", on);
  }
  try{
    document.dispatchEvent(new CustomEvent("skin:change", {detail:{skin:name}}));
  }catch(e){}
}

var btns = document.querySelectorAll("[data-skin-pick]");
for(var i=0;i<btns.length;i++){
  (function(btn){
    btn.addEventListener("click", function(){
      apply(btn.getAttribute("data-skin-pick"));
    });
  })(btns[i]);
}
apply(root.getAttribute("data-skin") || "francais");
})();
</script>"""


JS_SW = """<script>
/* Offline shell. updateViaCache:'none' makes the browser always revalidate
   sw.js itself, so a redeploy is picked up on the next visit instead of
   lingering in the HTTP cache for up to a day. */
if('serviceWorker' in navigator){
  window.addEventListener('load', function(){
    navigator.serviceWorker.register('./sw.js', {updateViaCache:'none'}).catch(function(){});
  });
}
</script>"""


# ═══════════════════════════════════════════════════════════════════════════
# Number Table (1-100)
# ═══════════════════════════════════════════════════════════════════════════

NUMBER_TABLE: dict[str, str] = {
    "0": "zéro /ze.ʁo/", "1": "un /œ̃/", "2": "deux /dø/", "3": "trois /tʁwa/",
    "4": "quatre /ka.tʁ/", "5": "cinq /sɛ̃k/", "6": "six /sis/", "7": "sept /sɛt/",
    "8": "huit /ɥit/", "9": "neuf /nœf/", "10": "dix /dis/",
    "11": "onze /ɔ̃z/", "12": "douze /duz/", "13": "treize /tʁɛz/",
    "14": "quatorze /ka.tɔʁz/", "15": "quinze /kɛ̃z/", "16": "seize /sɛz/",
    "17": "dix-sept /dis.sɛt/", "18": "dix-huit /di.zɥit/", "19": "dix-neuf /di.nœf/",
    "20": "vingt /vɛ̃t/", "21": "vingt-et-un /vɛ̃.t‿e.œ̃/", "22": "vingt-deux /vɛ̃t.dø/",
    "30": "trente /tʁɑ̃t/", "40": "quarante /ka.ʁɑ̃t/", "50": "cinquante /sɛ̃.kɑ̃t/",
    "60": "soixante /swa.sɑ̃t/", "70": "soixante-dix /swa.sɑ̃t.dis/",
    "80": "quatre-vingts /ka.tʁə.vɛ̃/", "90": "quatre-vingt-dix /ka.tʁə.vɛ̃.dis/",
    "100": "cent /sɑ̃/",
    "premier": "premier /pʁə.mje/ (第一)", "deuxième": "deuxième /dø.zjɛm/ (第二)",
    "demi": "demi /də.mi/ (一半)", "moitié": "moitié /mwa.tje/ (一半)",
}


# ═══════════════════════════════════════════════════════════════════════════
# HTML Page Assembly
# ═══════════════════════════════════════════════════════════════════════════


def _add_liaison_marks(html: str) -> str:
    """Insert liaison undertie (U+203F) between word spans where liaison occurs."""
    import re as _re
    liaison_endings = frozenset({"s", "x", "z", "d", "t", "n", "p", "r"})
    vowel_start = _re.compile(r"^[aeiouéèêàâîôûüyœæ]", _re.IGNORECASE)

    pattern = _re.compile(r'(<span class="word"[^>]*>)([^<]{1,30})(</span>)')
    matches = list(pattern.finditer(html))

    parts: list[str] = []
    last_end = 0
    for i, m in enumerate(matches):
        parts.append(html[last_end:m.start()])
        parts.append(m.group(1) + m.group(2) + m.group(3))

        if i + 1 < len(matches):
            nm = matches[i + 1]
            last_char = m.group(2)[-1].lower() if m.group(2) else ""
            first_char = nm.group(2)[0].lower() if nm.group(2) else ""
            if last_char in liaison_endings and vowel_start.match(first_char):
                parts.append('<span class="liaison">‿</span>')
        last_end = m.end()
    parts.append(html[last_end:])
    return "".join(parts)


def _render_card(s: Sentence, lexicon: dict[str, dict]) -> str:
    sid = esc(s.id)
    diff = esc(s.difficulty or "A2")

    # Audio — audio_file already holds a site-relative path ("audio/<date>/<id>.mp3")
    audio_html = ""
    if s.audio_file:
        audio_html = (
            '<div class="audio-row">'
            '<audio controls preload="none" src="' + esc(s.audio_file) + '"'
            ' onerror="onAudioError(event)"></audio>'
            '<div class="speed-group">'
            '<button class="speed-btn" type="button" data-rate="0.5" onclick="setSpeed(0.5,this)">0.5x</button>'
            '<button class="speed-btn active" type="button" data-rate="0.75" onclick="setSpeed(0.75,this)">0.75x</button>'
            '<button class="speed-btn" type="button" data-rate="1" onclick="setSpeed(1,this)">1x</button>'
            "</div></div>"
        )

    displayed = _add_liaison_marks(_wrap_words(s.text, segment(s.text), lexicon))

    zh = (
        '<p class="zh" lang="zh-CN">' + esc(s.translation) + "</p>"
        if s.translation else ""
    )

    return (
        '<div class="deck-slide">'
        '<article class="sentence-card" data-sid="' + sid + '">'
        '<div class="card-topbar">'
        '<span class="level-badge level-' + diff + '">' + diff + "</span>"
        '<button class="card-collect" data-sid="' + sid + '" type="button"'
        ' title="收藏此句" aria-label="收藏此句">☆</button>'
        "</div>"
        '<div class="verse">'
        '<span class="guillemet" aria-hidden="true">«</span>'
        '<p class="fr-text" lang="fr">' + displayed + "</p>"
        "</div>"
        + zh +
        '<div class="rule" aria-hidden="true">⚜</div>'
        + audio_html
        + _render_grammar(s, lexicon) +
        "</article>"
        "</div>"
    )


def _get_dictionary() -> Dictionary:
    """Dictionary singleton (starter.json + curated.json + gloss.json)."""
    global _DICT_INSTANCE
    if _DICT_INSTANCE is None:
        _DICT_INSTANCE = Dictionary(ROOT / "dict" / "starter.json")
    return _DICT_INSTANCE


def _explanation_text(s: Sentence) -> list[str]:
    """Every string an explanation may print — prose, notes, table cells.

    The lexicon is built from these too, so a word that only ever appears in
    the grammar course is still clickable there.
    """
    out: list[str] = [s.grammar_note or ""]
    out.extend(v for v in (s.grammar_notes or {}).values() if v)
    for lesson in s.grammar_lessons or []:
        out.append(lesson.get("t") or "")
        out.append(lesson.get("b") or "")
        spec = lesson.get("table") or {}
        out.append(str(spec.get("caption") or ""))
        out.append(str(spec.get("note") or ""))
        out.extend(str(h) for h in (spec.get("head") or []))
        for row in spec.get("rows") or []:
            out.extend(str(c) for c in row)
    return out


def _page_tokens(sentences: list[Sentence]) -> set[str]:
    """Every French token the page will print, sentence and explanation alike."""
    tokens: set[str] = set()
    for s in sentences:
        tokens.update(segment(s.text))
        for text in _explanation_text(s):
            tokens.update(_FR_WORD_RE.findall(_IPA_SPAN_RE.sub(" ", text)))
    return tokens


def _build_lexicon(sentences: list[Sentence], tokens: set[str]) -> dict[str, dict]:
    """Today's tokens → their dictionary entries.

    Resolution happens at render time rather than being read back from the
    stored ``words`` array, so topping up the dictionary makes *existing* days
    clickable-to-defined immediately — no regeneration needed. Keyed by both the
    contraction-stripped root ("apprends") and the raw token ("j'apprends"),
    because lookups arrive in both shapes.
    """
    dictionary = _get_dictionary()
    lexicon: dict[str, dict] = {}
    for token in tokens:
        key = token.lower()
        root = _CONTRACT_PREFIX_RE.sub("", key)
        entry = dictionary.lookup_local(root) or dictionary.lookup_local(key)
        if not entry:
            continue
        lexicon.setdefault(root, entry)
        lexicon.setdefault(key, entry)
    return lexicon


def _conj_payload(sentences: list[Sentence], tokens: set[str]) -> tuple[dict, dict]:
    """Conjugation data for the page: (form index, verb book).

    Only the verbs this page actually touches ship with it — a learner reading
    about faire does not need aller's futur in the page weight.
    """
    involved: set[str] = set()
    for token in tokens:
        for entry in conjug.find_form(token):
            involved.add(entry["v"])
    for s in sentences:
        for lesson in s.grammar_lessons or []:
            inf = (lesson.get("conj") or {}).get("v")
            if inf and conjug.has_verb(inf):
                involved.add(inf)
    if not involved:
        return {}, {}

    form_index: dict[str, list[dict]] = {}
    for form, entries in conjug.INDEX.items():
        hits = [e for e in entries if e["v"] in involved]
        if hits:
            form_index[form] = hits

    book = {
        inf: {
            "inf": inf,
            "group": v["group"],
            "mean": v["mean"],
            "inf_ipa": v["inf_ipa"],
            "pp": v["pp"],
            "pp_ipa": v["pp_ipa"],
            "aux": v["aux"],
            "note": v["note"],
            "tenses": {
                t: {"label": list(conjug.TENSE_LABEL.get(t, (t, ""))), "rows": rows}
                for t, rows in v["tables"].items()
            },
        }
        for inf, v in conjug.BOOK.items() if inf in involved
    }
    return form_index, book


def render_page(day: Day, streak_info: dict, archive_dates: list[str]) -> str:
    site_name = "FrenchDaily"

    sentences = [s for p in day.passages for s in p.sentences]
    total = len(sentences)

    # ── JS data ──
    tokens = _page_tokens(sentences)
    lexicon = _build_lexicon(sentences, tokens)
    conj_index, verb_book = _conj_payload(sentences, tokens)

    all_sentences: dict[str, dict] = {}
    for s in sentences:
        all_sentences[s.id] = {
            "text": s.text,
            "translation": s.translation,
            "difficulty": s.difficulty,
            "date": day.date,
        }

    dict_json = json.dumps(lexicon, ensure_ascii=False)
    conj_json = json.dumps(conj_index, ensure_ascii=False)
    vbook_json = json.dumps(verb_book, ensure_ascii=False)
    conj_meta_json = json.dumps({
        "tabs": conjug.TENSE_TAB,
        "labels": {k: list(v) for k, v in conjug.TENSE_LABEL.items()},
        "persons": conjug.PERSON_LABEL,
    }, ensure_ascii=False)
    sentences_json = json.dumps(all_sentences, ensure_ascii=False)
    numbers_json = json.dumps(NUMBER_TABLE, ensure_ascii=False)
    grammar_notes_json = json.dumps(
        {s.id: s.grammar_notes for s in sentences}, ensure_ascii=False
    )

    streak_current = streak_info.get("current_streak", 0)
    streak_total = streak_info.get("total_days", 0)

    # ── Cards / deck ──
    if total:
        cards_html = "".join(
            _render_card(s, lexicon) for s in sentences
        )
        dots_html = "".join(
            '<button class="deck-dot' + (" active" if i == 0 else "") + '"'
            ' type="button" data-idx="' + str(i) + '"'
            ' aria-label="第 ' + str(i + 1) + ' 句"></button>'
            for i in range(total)
        )
        deck_html = (
            '<div class="deck"><div class="deck-track" tabindex="0"'
            ' data-older="' + esc(_neighbour(archive_dates, day.date, 1)) + '"'
            ' data-newer="' + esc(_neighbour(archive_dates, day.date, -1)) + '">'
            + cards_html +
            "</div></div>"
            '<div class="deck-ctl">'
            '<button class="deck-btn" id="deck-prev" type="button" aria-label="上一句">‹</button>'
            '<span class="deck-pos" id="deck-pos">1 / ' + str(total) + "</span>"
            '<button class="deck-btn" id="deck-next" type="button" aria-label="下一句">›</button>'
            "</div>"
            '<div class="deck-dots" id="deck-dots">' + dots_html + "</div>"
            '<div class="progress-bar"><div class="progress-fill" id="progress"'
            ' style="width:' + f"{100 / total:.1f}" + '%"></div></div>'
            '<p class="deck-hint">← → 翻句 · 手机左右滑动 · 点单词可查词与变位</p>'
        )
    else:
        deck_html = (
            '<div class="empty-day">今天还没有内容 · Pas de contenu aujourd\'hui</div>'
        )

    # ── Archive ──
    archive_html = ""
    if archive_dates:
        links = "".join(
            '<a class="archive-link' + (" current" if d == day.date else "") + '"'
            ' href="' + esc(d) + '.html">' + esc(d) + "</a>"
            for d in archive_dates[:30]
        )
        archive_html = (
            '<div class="archive-section">'
            '<div class="archive-title">历史归档 · Archives</div>'
            '<div class="archive-list">' + links + "</div>"
            "</div>"
        )

    date_fr = _french_date(day.date)

    page = f"""<!DOCTYPE html>
<html lang="fr" data-skin="francais"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{esc(site_name)} · {esc(day.date)}</title>
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#fbf6ee" media="(prefers-color-scheme:light)">
<meta name="theme-color" content="#17130f" media="(prefers-color-scheme:dark)">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="{esc(site_name)}">
<meta name="format-detection" content="telephone=no">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;0,700;1,400;1,600&family=Playfair+Display:wght@400;600;700&display=swap" rel="stylesheet">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" type="image/png" sizes="192x192" href="icons/icon-192.png">
<link rel="apple-touch-icon" href="icons/icon-192.png">
<style>{CSS}{CSS_SKIN_FR}</style>
<script>
/* Restore the chosen skin before first paint — otherwise the page flashes the
   default look and then snaps to the saved one. */
(function(){{try{{
  var s = localStorage.getItem("frenchdaily_skin");
  if(s === "classique" || s === "francais") document.documentElement.setAttribute("data-skin", s);
}}catch(e){{}}}})();
</script>
</head><body>

<header class="site-header">
  <div class="brand">French<span class="b-rouge">Daily</span></div>
  <div class="brand-fr">Lecture du jour · 每日法语阅读</div>
  <div class="tricolore" aria-hidden="true"><i></i><i></i><i></i></div>
  <div class="header-meta">
    <span class="chip">{esc(day.date)}</span>
    <span class="chip chip-date-fr" lang="fr">{esc(date_fr)}</span>
    <span class="chip">
      <span class="streak-fire{' animate' if streak_current >= 3 else ''}">🔥</span>
      <span>连续</span><span class="streak-count">{streak_current}</span><span>天</span>
    </span>
  </div>
  <div class="skin-switch" role="group" aria-label="外观风格">
    <span class="skin-switch-label">外观</span>
    <button type="button" data-skin-pick="francais">Français</button>
    <button type="button" data-skin-pick="classique">Classique</button>
  </div>
</header>

<div class="wrap">
  {deck_html}
  {archive_html}
</div>

<div class="fab-group">
  <button class="fab" id="collect-fab" type="button" title="句本" aria-label="句本">📖<span class="fab-badge" id="collect-badge"></span></button>
</div>
<div class="collect-overlay" id="collect-overlay"></div>
<div class="collect-panel" id="collect-panel">
  <div class="collect-panel-header">
    <div><span class="collect-panel-title">句本</span><span class="collect-panel-count" id="collect-count"></span></div>
    <button class="collect-panel-close" type="button" aria-label="关闭">×</button>
  </div>
  <div class="collect-panel-body" id="collect-panel-body"><div class="collect-empty">还没有收藏的句子</div></div>
</div>

<div class="toast" id="toast"></div>

<script>
function setSpeed(rate, btn){{
  var row = btn.closest(".audio-row");
  var audio = row ? row.querySelector("audio") : null;
  if(audio) audio.playbackRate = rate;
  var btns = btn.parentElement.querySelectorAll(".speed-btn");
  for(var i=0;i<btns.length;i++) btns[i].classList.remove("active");
  btn.classList.add("active");
}}
function onAudioError(e){{
  var audio = e.target;
  var row = audio.parentElement;
  if(row.querySelector(".audio-error")) return;
  var err = document.createElement("div");
  err.className = "audio-error";
  err.innerHTML = '<span>音频暂时不可用，点击重试</span>';
  err.querySelector("span").addEventListener("click", function(){{ audio.load(); }});
  row.appendChild(err);
}}
</script>
<script>
window.__DICT__ = {dict_json};
window.__SENTENCES__ = {sentences_json};
window.__NUMBERS__ = {numbers_json};
window.__GRAMMAR_NOTES__ = {grammar_notes_json};
window.__CONJ__ = {conj_json};
window.__VBOOK__ = {vbook_json};
window.__CMETA__ = {conj_meta_json};
</script>
{JS_LOOKUP}
{JS_COLLECTION}
{JS_DECK}
{JS_SKIN}
{JS_SW}
</body></html>"""
    return page


_MONTHS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]
_DAYS_FR = [
    "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche",
]


def _french_date(date: str) -> str:
    """'2026-09-21' → 'lundi 21 septembre 2026' (no leading zero on the day)."""
    try:
        from datetime import date as _date
        y, m, d = (int(x) for x in date.split("-"))
        return f"{_DAYS_FR[_date(y, m, d).weekday()]} {d} {_MONTHS_FR[m - 1]} {y}"
    except (ValueError, IndexError):
        return ""


def _neighbour(archive_dates: list[str], date: str, offset: int) -> str:
    """Neighbouring day file for deck edge-crossing.

    archive_dates is newest-first, so +1 walks to an older day and -1 to a
    newer one. Returns "" when there is no neighbour.
    """
    try:
        i = archive_dates.index(date)
    except ValueError:
        return ""
    j = i + offset
    if 0 <= j < len(archive_dates):
        return f"{archive_dates[j]}.html"
    return ""


# ═══════════════════════════════════════════════════════════════════════════
# Word annotation — anything French, anywhere on the page, is tappable
# ═══════════════════════════════════════════════════════════════════════════

# Letters only, and only the ones French actually uses — À-ÖØ-öø-ÿ keeps × and
# ÷ out of the class, which a naive À-ÿ range would swallow.
_FR_WORD_RE = re.compile(
    r"[A-Za-zÀ-ÖØ-öø-ÿŒœÆæ]+(?:['’][A-Za-zÀ-ÖØ-öø-ÿŒœÆæ]+)*"
)
# IPA between slashes. Excluding CJK and fullwidth punctuation matters: prose
# uses "/" as a plain separator in places ("-ais / -ait / -ions"), and a naive
# [`[^/]+`] class would happily swallow a sentence fragment as if it were
# phonetic and hand the leftover letters back as words.
_IPA_SPAN_RE = re.compile(
    r"/[^/\n\u3000-\u303f\u4e00-\u9fff\uff01-\uff60]{1,40}/"
)
_AFFIX_DASH = "-–—"

# Number words that should trigger the 1-100 table popup
_NUM_KEYS = frozenset({
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
    "vingt", "trente", "quarante", "cinquante", "soixante",
    "cent", "premier", "deuxième", "demi", "moitié",
})


def _resolve(token: str, lexicon: dict[str, dict]) -> tuple[str, bool, list[dict], bool]:
    """Resolve one token → (lookup key, has dictionary entry, conjugations, is number)."""
    lower = token.lower().strip("'")
    root = _CONTRACT_PREFIX_RE.sub("", lower)
    entry = lexicon.get(root) or lexicon.get(lower)
    conj = conjug.find_form(root) or conjug.find_form(lower)
    is_num = root in _NUM_KEYS or lower in _NUM_KEYS
    return root, bool(entry), conj, is_num


def _span(token: str, root: str, has_dict: bool, conj: list[dict], is_num: bool) -> str:
    """Build the clickable span for one already-resolved token.

    A form with no dictionary entry but a known conjugation ("faisons") is a
    real word the reader can be told something about — it must not carry the
    unknown styling, which is reserved for tokens nothing in the project knows.
    """
    if has_dict:
        attrs = f'data-word="{esc(root)}" data-has-dict="true"'
    elif conj:
        attrs = f'data-word="{esc(root)}" data-conj="true"'
    elif is_num:
        attrs = f'data-word="{esc(root)}" data-is-num="true"'
    else:
        attrs = f'data-word="{esc(root)}" data-unknown="true"'
    attrs += f' data-orig="{esc(token)}"'
    return f'<span class="word" {attrs}>{esc(token)}</span>'


def _annotate(text: str, lexicon: dict[str, dict], *, strict: bool) -> str:
    """Wrap the French words of a plain-text run as clickable spans.

    ``strict=True`` (explanations, tables) only wraps a token when tapping it
    would actually tell you something — a dictionary entry or a conjugation.
    Everything else stays plain text, so the prose never sprouts dead links.

    ``strict=False`` (the sentence itself) wraps every token, because that line
    is the thing being read aloud; an unresolved word still gets a 🔊 button.

    IPA between slashes is left alone, and so is anything glued to a hyphen —
    "去掉 -er 再加词尾" is talking about a suffix, not a word.
    """
    out: list[str] = []
    pos = 0
    for m in _IPA_SPAN_RE.finditer(text):
        out.append(_annotate_plain(text[pos:m.start()], lexicon, strict))
        out.append(esc(m.group(0)))
        pos = m.end()
    out.append(_annotate_plain(text[pos:], lexicon, strict))
    return "".join(out)


def _annotate_plain(seg: str, lexicon: dict[str, dict], strict: bool) -> str:
    pieces: list[str] = []
    last = 0
    for m in _FR_WORD_RE.finditer(seg):
        s, e = m.span()
        if (s > 0 and seg[s - 1] in _AFFIX_DASH) or (e < len(seg) and seg[e] in _AFFIX_DASH):
            continue
        token = m.group(0)
        root, has_dict, conj, is_num = _resolve(token, lexicon)
        if strict and not (has_dict or conj or is_num):
            continue
        pieces.append(esc(seg[last:s]))
        pieces.append(_span(token, root, has_dict, conj, is_num))
        last = e
    pieces.append(esc(seg[last:]))
    return "".join(pieces)


def _wrap_words(text: str, all_segments: list[str], lexicon: dict[str, dict]) -> str:
    """The sentence line: every token is tappable, resolved or not."""
    # Sanity: only tokens that really occur get wrapped, and only at their own
    # boundaries — "si" must not match inside "visiter".
    replacements: list[tuple[int, int, str]] = []
    for token in all_segments:
        start = 0
        while True:
            pos = text.lower().find(token.lower(), start)
            if pos == -1:
                break
            end_pos = pos + len(token)
            before = pos > 0 and text[pos - 1].isalpha()
            after = end_pos < len(text) and text[end_pos].isalpha()
            if not before and not after:
                replacements.append((pos, end_pos, text[pos:end_pos]))
            start = pos + 1

    replacements.sort(key=lambda r: (r[0], -(r[1] - r[0])))
    filtered: list[tuple[int, int, str]] = []
    last_end = 0
    for start, end, orig in replacements:
        if start >= last_end:
            filtered.append((start, end, orig))
            last_end = end

    result: list[str] = []
    last = 0
    for start, end, orig in filtered:
        result.append(esc(text[last:start]))
        root, has_dict, conj, is_num = _resolve(orig, lexicon)
        result.append(_span(orig, root, has_dict, conj, is_num))
        last = end
    result.append(esc(text[last:]))
    return "".join(result)


# ═══════════════════════════════════════════════════════════════════════════
# Conjugation tables — real <table> markup, not a wall of text
# ═══════════════════════════════════════════════════════════════════════════


_IPA_CELL_RE = re.compile(r"^/[^/]{1,60}/$")
_FR_LETTER_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")


def _speak_src(row: list, i: int) -> str:
    """Which word the transcription in column *i* actually transcribes.

    Lesson tables are not laid out uniformly: most put the reading right after
    the word ("词 · 读音 · 意思") but the participle table puts it last
    ("原形 · 过去分词 · 读音"). So walk left for the nearest cell that holds
    French letters, skipping other transcriptions and bare Chinese notes.
    """
    for j in range(i - 1, -1, -1):
        t = str(row[j]).strip()
        if not t or _IPA_CELL_RE.match(t) or t[0] in "（(":
            continue
        if _FR_LETTER_RE.search(t):
            return t
    return ""


def _render_rows(rows: list[list[str]], lexicon: dict[str, dict], *,
                 annotate_cols: set[int] | None = None) -> str:
    """One <tr> per row. ``annotate_cols`` limits clickable cells to the given
    column indexes — a conjugation table's 人称 column is a grammatical label
    ("qu'ils/elles"), not a word of the sentence, so it stays plain text."""
    out = ""
    for row in rows:
        cells = ""
        for i, cell in enumerate(row):
            text = str(cell)
            do = annotate_cols is None or i in annotate_cols
            body = _annotate(text, lexicon, strict=True) if do else esc(text)
            # A transcription carries the horn, and the horn says the *word* —
            # speaking "/vi.zi.te/" out of an IPA string would be gibberish.
            if _IPA_CELL_RE.match(text.strip()):
                src = _speak_src(row, i)
                if src:
                    body = esc(text) + _spk(src)
                cells += f'<td class="tb-ipa">{body}</td>'
            else:
                cells += f"<td>{body}</td>"
        out += "<tr>" + cells + "</tr>"
    return out


def _table_html(head: list[str], rows: list[list[str]], lexicon: dict[str, dict],
                caption: str = "", fr_caption: str = "", note: str = "",
                annotate_cols: set[int] | None = None) -> str:
    """A scrollable leaf of paper holding a table.

    Every French cell is annotated, so tapping "fais" inside a table gives the
    same dictionary bubble + conjugation panel as tapping it in the sentence.
    """
    head_html = ""
    if head:
        head_html = "<thead><tr>" + "".join(
            f"<th>{esc(h)}</th>" for h in head
        ) + "</tr></thead>"

    cap = ""
    if caption or fr_caption:
        cap = "<figcaption>" + esc(caption)
        if fr_caption:
            cap += f'<span class="tb-fr" lang="fr">{esc(fr_caption)}</span>'
        cap += "</figcaption>"

    note_html = f'<p class="tb-note">{_annotate(note, lexicon, strict=True)}</p>' if note else ""

    return (
        '<figure class="lg-table">'
        + cap
        + '<div class="tb-scroll"><table>' + head_html
        + "<tbody>" + _render_rows(rows, lexicon, annotate_cols=annotate_cols) + "</tbody>"
        + "</table></div>"
        + note_html
        + "</figure>"
    )


def _conj_table(inf: str, tense: str, lexicon: dict[str, dict]) -> str:
    """A conjugation table pulled straight from core/conjug.py."""
    verb = conjug.tables(inf)
    if not verb:
        return ""
    rows = verb["tables"].get(tense)
    if not rows:
        return ""

    zh, fr = conjug.TENSE_LABEL.get(tense, (tense, ""))
    # Impersonal verbs only have an il row — label the column accordingly.
    person_head = "主语" if len(rows) < 3 else "人称"

    note_bits = []
    if verb.get("mean"):
        note_bits.append(verb["mean"])
    if verb.get("inf_ipa"):
        note_bits.append(verb["inf_ipa"])
    if verb.get("pp"):
        note_bits.append(f'过去分词 {verb["pp"]}' + (
            f' {verb["pp_ipa"]}' if verb.get("pp_ipa") else ""
        ))
    if verb.get("aux") == "être":
        note_bits.append("助动词用 être")
    note = " · ".join(note_bits)
    if verb.get("note"):
        note = (note + "。 " if note else "") + verb["note"]

    return _table_html(
        [person_head, "变位", "读音"], rows, lexicon,
        caption=f"{inf} · {zh}", fr_caption=fr, note=note,
        annotate_cols={1},  # only the conjugated form is a word, not the pronoun
    )


def _table_spec(spec: dict, lexicon: dict[str, dict]) -> str:
    """Render a hand-authored lesson table ({caption, head, rows})."""
    rows = [[str(c) for c in r] for r in (spec.get("rows") or [])]
    if not rows:
        return ""
    head = [str(h) for h in (spec.get("head") or [])]
    return _table_html(
        head, rows, lexicon,
        caption=str(spec.get("caption") or ""),
        fr_caption=str(spec.get("fr_caption") or ""),
        note=str(spec.get("note") or ""),
    )


def _render_grammar(s: Sentence, lexicon: dict[str, dict]) -> str:
    """Server-rendered 语法解析 section.

    Layout: a one-line overview (grammar_note) that is always visible, then the
    teaching cards (grammar_lessons) behind a native <details> toggle — zero JS,
    keyboard accessible, and it keeps a card short enough to read on one screen.

    A lesson may carry a ``table`` (hand-authored) and/or a ``conj`` reference
    ({"v": "faire", "t": "present"}) — the latter is generated from
    core/conjug.py so the conjugation in the lesson and the conjugation behind
    a tapped word can never drift apart.
    """
    note = (s.grammar_note or "").strip()
    lessons = [l for l in (s.grammar_lessons or []) if l.get("t") or l.get("b")]
    if not note and not lessons:
        return ""

    # Graceful degradation: a day generated without grammar_lessons still gets
    # something to open, built from the per-word notes.
    if not lessons:
        per_word = [
            f"{k} — {v}" for k, v in (s.grammar_notes or {}).items() if v
        ]
        if per_word:
            lessons = [{"t": "本句要点", "b": "\n".join(per_word)}]

    inner = ""
    if note:
        inner += '<p class="grammar-note">' + _annotate(note, lexicon, strict=True) + "</p>"

    if lessons:
        items = ""
        for lesson in lessons:
            title = (lesson.get("t") or "").strip()
            body = (lesson.get("b") or "").strip()
            block = ""
            if title:
                block += '<div class="lesson-t">' + esc(title) + "</div>"

            # The table is the centrepiece of a conjugation lesson, so it sits
            # directly under the title and the prose reads as the caveats.
            conj_ref = lesson.get("conj") or {}
            if conj_ref.get("v"):
                block += _conj_table(conj_ref["v"], conj_ref.get("t", "present"), lexicon)
            if lesson.get("table"):
                block += _table_spec(lesson["table"], lexicon)

            # A body may hold several "\n"-separated lines (e.g. a list of
            # example phrases) — each becomes its own paragraph so it can breathe.
            for line in body.split("\n"):
                line = line.strip()
                if line:
                    block += '<div class="lesson-b">' + _annotate(
                        line, lexicon, strict=True
                    ) + "</div>"
            if block:
                items += '<li class="lesson">' + block + "</li>"

        if items:
            inner += (
                '<details class="lessons">'
                "<summary>"
                '<span class="tg tg-open">展开讲解</span>'
                '<span class="tg tg-close">收起讲解</span>'
                '<span class="cnt">' + str(len(lessons)) + " 讲</span>"
                "</summary>"
                '<ol class="lesson-list">' + items + "</ol>"
                "</details>"
            )

    return (
        '<section class="seg">'
        '<div class="lb">语法解析<span class="lb-fr">Grammaire</span></div>'
        + inner +
        "</section>"
    )


def render_day(day: Day, streak_info: dict, archive_dates: list[str]) -> str:
    """Public entry point: one day → one self-contained HTML page."""
    return render_page(day, streak_info, archive_dates)
