#!/usr/bin/env python3
"""
Build and clean the lzl-dream classical Chinese dream-divination corpus.

Fetches ONLY from verified MIT and Public Domain sources:
  1. ycc77cn/skills (MIT): 梦林玄解.txt, 梦林玄解_前段.txt
  2. Chinese Wikisource (Public Domain): 夢林玄解/夢林玄解卷之首,
     钦定古今图书集成·历象汇编·庶徵典·第144卷至第152卷 (梦部)
  3. GaoRenYouShu/XuanJiPaiPan (MIT): zhougong-duanm.js (断梦秘书),
     zhougong-data.js (周公解梦 27 类), zhougong.js (繁简归一化参照)
  4. garychowcmu/daizhigev20 (Public Domain): 周公解梦.txt, 周礼·占梦,
     潜夫论·梦列, 列子·周穆王, 灵枢·淫邪发梦, 论衡·订鬼/纪妖, 阿难七梦经
  5. kanripo (Public Domain): KR5a0295 占怪祟恶梦法第六十六,
     KR5e0028 解恶梦品, KR5e0068 附梦秘法 & 应梦占验
  6. BYVoid/OpenCC (Apache-2.0): TSCharacters.txt (for T2S normalization)

Outputs cleaned JSONL corpora + manifest.json into references/corpus/
and t2s_map.json into references/.
"""

from __future__ import annotations

import ast
import hashlib
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
REFS_DIR = SKILL_ROOT / "references"
CORPUS_DIR = REFS_DIR / "corpus"

UA = "LzlDreamCorpusBuilder/1.0 (https://github.com/solplum/lzl-skill)"


def fetch_text(url: str, delay: float = 0.0) -> str:
    """Fetch UTF-8 text from url with polite User-Agent and optional delay."""
    if delay > 0:
        time.sleep(delay)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def gh_raw(owner: str, repo: str, branch: str, path: str) -> str:
    encoded = "/".join(urllib.parse.quote(part) for part in path.split("/"))
    return fetch_text(f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{encoded}")


def wikisource_parse(page: str) -> str:
    url = "https://zh.wikisource.org/w/api.php?" + urllib.parse.urlencode(
        {
            "action": "parse",
            "page": page,
            "prop": "text",
            "variant": "zh-cn",
            "format": "json",
        }
    )
    data = json.loads(fetch_text(url, delay=0.45))
    return data.get("parse", {}).get("text", {}).get("*", "")


def build_t2s_map() -> dict[str, str]:
    """Build a reliable Traditional -> Simplified single-character map."""
    t2s: dict[str, str] = {}
    ts_raw = gh_raw("BYVoid", "OpenCC", "master", "data/dictionary/TSCharacters.txt")
    for line in ts_raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "\t" not in line:
            continue
        trad, simp_list = line.split("\t", 1)
        cands = simp_list.split()
        if len(trad) == 1 and cands and len(cands[0]) == 1 and trad != cands[0]:
            t2s[trad] = cands[0]

    # Overlay curated ZG_T2S from GaoRenYouShu/XuanJiPaiPan (MIT)
    zg_js = gh_raw("GaoRenYouShu", "XuanJiPaiPan", "main", "assets/zhougong.js")
    m = re.search(r"var\s+ZG_T2S\s*=\s*(\{.*?\});", zg_js, re.S)
    if m:
        zg_t2s = ast.literal_eval(m.group(1))
        for k, v in zg_t2s.items():
            if len(k) == 1 and len(v) == 1:
                t2s[k] = v

    # Classical divination disambiguation overrides:
    # Keep 乾 as 乾 (not 干, since 乾坤/乾卦 is core terminology), 佔 -> 占, 徵 -> 征 except phrase handled
    t2s["乾"] = "乾"
    t2s["佔"] = "占"
    t2s["夢"] = "梦"
    t2s["斷"] = "断"
    t2s["靈"] = "灵"
    t2s["龜"] = "龟"
    t2s["龍"] = "龙"
    t2s["歷"] = "历"
    t2s["曆"] = "历"
    t2s["彙"] = "汇"
    t2s["藝"] = "艺"
    t2s["紀"] = "纪"
    t2s["雜"] = "杂"
    t2s["呪"] = "咒"
    t2s["祕"] = "秘"
    t2s["竈"] = "灶"
    t2s["牀"] = "床"
    t2s["裏"] = "里"
    t2s["裡"] = "里"
    t2s["爲"] = "为"
    t2s["於"] = "于"
    t2s["後"] = "后"
    t2s["復"] = "复"
    t2s["複"] = "复"
    t2s["發"] = "发"
    t2s["惡"] = "恶"
    t2s["厭"] = "厌"
    t2s["應"] = "应"
    t2s["驗"] = "验"
    t2s["鬱"] = "郁"
    t2s["齋"] = "斋"
    t2s["臟"] = "脏"
    t2s["腑"] = "腑"
    t2s["徵"] = "征"
    # Kanripo / classical CJK variant forms
    t2s["縁"] = "缘"
    t2s["闘"] = "斗"
    t2s["宻"] = "密"
    t2s["虵"] = "蛇"
    t2s["䑕"] = "鼠"
    t2s["黒"] = "黑"
    t2s["眞"] = "真"
    t2s["髙"] = "高"
    t2s["冨"] = "富"
    t2s["徃"] = "往"
    t2s["炁"] = "气"
    t2s["衞"] = "卫"
    t2s["迴"] = "回"
    t2s["囬"] = "回"
    t2s["䖍"] = "虔"
    return t2s


def to_simp(text: str, t2s: dict[str, str]) -> str:
    # Preserve 庶徵典 / 梦徵 / 觉有八征? Actually 庶徵典 and 梦徵 are traditionally 征 or 徵.
    # Let's keep 徵 as 征 in simplified except 宫商角徵羽, or keep consistent:
    # Wait: dream_guji & modern texts write 庶徵典 / 梦徵 with 徵! Let's preserve 徵 -> 徵 so 庶徵典/梦徵 stays authentic!
    local_map = dict(t2s)
    local_map.pop("徵", None)
    return "".join(local_map.get(ch, ch) for ch in text)


def infer_polarity(text: str) -> str:
    """Infer omen polarity strictly from explicit textual markers."""
    if not text:
        return "平/待参"
    has_ji = bool(re.search(r"大吉|吉昌|大吉利|吉利|主吉|极佳|祥|吉", text))
    has_xiong = bool(re.search(r"大凶|主凶|凶兆|凶|不祥|灾|祸|丧|病|死|失|败|破|防|忌|危", text))
    has_split = bool(
        re.search(
            r"（一）|（二）|贵人梦|常人梦|君子梦|小人梦|士子|商人|孕妇|女子|男子|老人|儿童|春|夏|秋|冬|昼|夜",
            text,
        )
    )
    if re.search(r"^[^。]{0,12}大吉", text) and not has_xiong:
        return "大吉"
    if re.search(r"^[^。]{0,12}大凶", text) and not has_ji:
        return "大凶"
    if (has_ji and has_xiong) or has_split:
        return "分人/分时"
    if re.search(r"大吉|吉利|吉昌|皆吉|大贵|富贵|大富|极佳", text) and not has_xiong:
        return "大吉" if "大吉" in text or "大富贵" in text else "吉"
    if has_ji and not has_xiong:
        return "吉"
    if has_xiong and not has_ji:
        return "大凶" if "大凶" in text else "凶"
    return "平/待参"


COND_PATTERNS = [
    ("贵人/官宦", r"贵人|达官|卿|王侯|公卿|官"),
    ("常人/庶民", r"常人|凡人|庶人|俗子|庸流"),
    ("士子/文人", r"士人|士子|文人|学者|书生|举子|科举"),
    ("商人/市井", r"商人|商贾|市人|贸易|求财|商旅"),
    ("孕妇/妇人", r"孕妇|产妇|妇人|女人|女子|闺阃|寡妇|处女"),
    ("男子", r"男子|丈夫|男人"),
    ("病者", r"病人|病者|病中|患者|患病|病患"),
    ("老人/幼童", r"老人|老者|幼童|儿童|小儿|婴孩"),
    ("讼者", r"讼者|狱讼|官司|争讼"),
    ("行人/旅人", r"行人|远行|出外|旅人"),
    ("春夏", r"春|夏|春夏"),
    ("秋冬", r"秋|冬|秋冬"),
    ("方位", r"东南|西北|东北|西南|东方|西方|南方|北方"),
    ("昼夜", r"昼|夜|平旦|鸡鸣"),
]


def extract_conditions(text: str) -> list[str]:
    conds = []
    for label, pat in COND_PATTERNS:
        if re.search(pat, text):
            conds.append(label)
    return conds or ["通用"]


def extract_keywords(motif: str, reading: str, category: str) -> list[str]:
    """Extract clean 1-4 char Chinese content tokens for indexing."""
    stop = set("梦见梦者此主为之于与而在有得乃及亦则若或非不无皆大吉凶兆象人者事")
    raw = f"{motif} {category}".strip()
    raw = re.sub(r"^[子丑寅卯辰巳午未申酉戌亥][·\s]*", "", raw)
    raw = re.sub(r"[·，。、；：！？（）〈〉《》「」『』\[\]\s]+", " ", raw)
    tokens: list[str] = []
    seen = set()
    # Add cleaned motif without leading '梦' / '梦见'
    core = re.sub(r"^梦见?", "", motif).strip("，。 ")
    if core and core not in seen:
        tokens.append(core)
        seen.add(core)
    for part in raw.split():
        part_clean = re.sub(r"^梦见?", "", part)
        if 1 <= len(part_clean) <= 6 and part_clean not in stop and part_clean not in seen:
            tokens.append(part_clean)
            seen.add(part_clean)
        for i in range(len(part_clean)):
            for ln in (2, 1):
                sub = part_clean[i : i + ln]
                if len(sub) == ln and sub not in stop and sub not in seen:
                    tokens.append(sub)
                    seen.add(sub)
                    if len(tokens) >= 16:
                        return tokens
    return tokens


def clean_whitespace(s: str) -> str:
    s = html.unescape(s).replace("\u200b", "").replace("\ufeff", "").replace("\u3000", " ")
    s = re.sub(r"[ \t\r]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


# ---------------------------------------------------------------------------
# 1. 梦林玄解 (ycc77cn/skills MIT + Wikisource 卷之首 PD)
# ---------------------------------------------------------------------------
class MenglinHeadParser(HTMLParser):
    """Parse Wikisource 夢林玄解卷之首 HTML into (heading, paragraphs)."""

    def __init__(self) -> None:
        super().__init__()
        self.skip_depth = 0
        self.in_h = False
        self.in_p = False
        self.cur_buf: list[str] = []
        self.blocks: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = dict(attrs)
        cls = ad.get("class") or ""
        el_id = ad.get("id") or ""
        if self.skip_depth > 0:
            self.skip_depth += 1
            return
        if (
            "mw-editsection" in cls
            or "toc" in cls
            or el_id in ("toc", "headerContainer", "plainSister")
            or tag in ("style", "script")
        ):
            self.skip_depth = 1
            return
        if tag in ("h2", "h3"):
            self.in_h = True
            self.cur_buf = []
        elif tag == "p":
            self.in_p = True
            self.cur_buf = []

    def handle_endtag(self, tag: str) -> None:
        if self.skip_depth > 0:
            self.skip_depth -= 1
            return
        if tag in ("h2", "h3") and self.in_h:
            self.in_h = False
            txt = clean_whitespace("".join(self.cur_buf))
            if txt:
                self.blocks.append(("h", txt))
        elif tag == "p" and self.in_p:
            self.in_p = False
            txt = clean_whitespace("".join(self.cur_buf))
            if txt:
                self.blocks.append(("p", txt))

    def handle_data(self, data: str) -> None:
        if self.skip_depth == 0 and (self.in_h or self.in_p):
            self.cur_buf.append(data)


def build_menglin(t2s: dict[str, str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_texts: set[str] = set()
    idx = 1

    # 1A. 卷首序论 from ycc77cn/skills 梦林玄解_前段.txt
    pre_raw = gh_raw(
        "ycc77cn", "skills", "main", "国学占卜/综合占卜-八层卜术/原文库/梦林玄解_前段.txt"
    )
    section_map = {
        "1knwreibwn410": ("序论·何栋如《梦林玄解》叙", "梦林玄解_前段"),
        "1knwrejn2amuu": ("序论·陈士元叙与张凤翼《梦占类考》叙", "梦林玄解_前段"),
        "1knwrejrl4zyj": ("凡例与葛洪小传", "梦林玄解_前段"),
    }
    cur_sec = ""
    cur_paras: list[str] = []

    def flush_pre() -> None:
        nonlocal idx
        if cur_sec not in section_map or not cur_paras:
            return
        cat, src_tag = section_map[cur_sec]
        for p in cur_paras:
            p_clean = to_simp(clean_whitespace(p), t2s)
            if len(p_clean) < 25 or p_clean == "AI生成":
                continue
            if p_clean in seen_texts:
                continue
            seen_texts.add(p_clean)
            records.append(
                {
                    "id": f"mlxj-{idx:04d}",
                    "book": "梦林玄解",
                    "era": "明",
                    "layer": "theory",
                    "category": cat,
                    "motif": cat,
                    "reading": p_clean,
                    "text": p_clean,
                    "polarity": "平/待参",
                    "conditions": extract_conditions(p_clean),
                    "keywords": extract_keywords(cat, p_clean, "梦原 序论"),
                    "note": "含OCR极少数缺讹字，按底本原貌保留",
                    "source_id": f"ycc77cn/skills:{src_tag}.txt",
                }
            )
            idx += 1

    for line in pre_raw.splitlines():
        line_s = line.strip()
        m = re.match(r"^=+\s*\[([^\]]+)\].*=+$", line_s)
        if m:
            flush_pre()
            cur_sec = m.group(1)
            cur_paras = []
        elif line_s:
            cur_paras.append(line_s)
    flush_pre()

    # 1B. 卷之首占繇正文 from Chinese Wikisource (观天地之会 / 辨二气之乘 / 审三辰之象)
    ws_html = wikisource_parse("夢林玄解/夢林玄解卷之首")
    parser = MenglinHeadParser()
    parser.feed(ws_html)
    cur_h = "占繇"
    for btype, btxt in parser.blocks:
        btxt_s = to_simp(btxt, t2s)
        if btype == "h":
            if "占繇" in btxt_s:
                continue
            cur_h = btxt_s
        else:
            if btxt_s in seen_texts or len(btxt_s) < 15:
                continue
            seen_texts.add(btxt_s)
            records.append(
                {
                    "id": f"mlxj-{idx:04d}",
                    "book": "梦林玄解",
                    "era": "明",
                    "layer": "theory",
                    "category": f"卷之首·占繇·{cur_h}",
                    "motif": cur_h,
                    "reading": btxt_s,
                    "text": f"{cur_h}：{btxt_s}",
                    "polarity": "平/待参",
                    "conditions": extract_conditions(btxt_s),
                    "keywords": extract_keywords(cur_h, btxt_s, "占繇 占法"),
                    "note": "",
                    "source_id": "zh.wikisource.org:夢林玄解/夢林玄解卷之首",
                }
            )
            idx += 1

    # 1C. 梦林玄解 7部16类梦占词典 from ycc77cn/skills 梦林玄解.txt
    ml_raw = gh_raw(
        "ycc77cn", "skills", "main", "国学占卜/综合占卜-八层卜术/原文库/梦林玄解.txt"
    )
    cur_cat = ""
    buf: list[str] = []

    def flush_entry() -> None:
        nonlocal idx
        if not buf or not cur_cat:
            buf.clear()
            return
        entry = to_simp(clean_whitespace("".join(buf)), t2s)
        buf.clear()
        if not entry or entry in seen_texts:
            return
        seen_texts.add(entry)
        # Split motif & reading cleanly
        if "。" in entry:
            parts = entry.split("。", 1)
            motif = parts[0].strip()
            reading = parts[1].strip()
        elif "，" in entry:
            parts = entry.split("，", 1)
            motif = parts[0].strip()
            reading = parts[1].strip()
        else:
            motif = entry
            reading = ""
        records.append(
            {
                "id": f"mlxj-{idx:04d}",
                "book": "梦林玄解",
                "era": "明",
                "layer": "omen",
                "category": cur_cat,
                "motif": motif,
                "reading": reading,
                "text": entry,
                "polarity": infer_polarity(reading or entry),
                "conditions": extract_conditions(entry),
                "keywords": extract_keywords(motif, reading, cur_cat),
                "note": "",
                "source_id": "ycc77cn/skills:梦林玄解.txt",
            }
        )
        idx += 1

    for line in ml_raw.splitlines():
        s = line.strip()
        m_cat = re.match(r"^=+\s*梦林玄解\s*\|\s*(.+?)\s*(?:-\s*知乎)?\s*=+$", s)
        if m_cat:
            flush_entry()
            cur_cat = to_simp(m_cat.group(1).strip(), t2s)
            continue
        if not cur_cat:
            continue
        if not s:
            flush_entry()
        else:
            # Some paragraphs may contain multiple lines; keep joining
            buf.append(s)
    flush_entry()
    return records


# ---------------------------------------------------------------------------
# 2. 断梦秘书 (GaoRenYouShu/XuanJiPaiPan MIT)
# ---------------------------------------------------------------------------
def extract_js_array(js_text: str, var_name: str) -> Any:
    """Safely extract a JS array literal using ast.literal_eval (no JS execution)."""
    m = re.search(rf"var\s+{re.escape(var_name)}\s*=\s*(\[[\s\S]*?\]);", js_text)
    if not m:
        raise ValueError(f"Could not find JS array {var_name}")
    body = m.group(1)
    # Remove trailing commas before ] which Python literal_eval forbids? Actually Python allows trailing commas in lists!
    # Strip any inline /* ... */ comments if present inside array
    body = re.sub(r"/\*[\s\S]*?\*/", "", body)
    return ast.literal_eval(body)


def build_duanmeng(t2s: dict[str, str]) -> list[dict[str, Any]]:
    js_raw = gh_raw("GaoRenYouShu", "XuanJiPaiPan", "main", "assets/zhougong-duanm.js")
    cats_flat = extract_js_array(js_raw, "ZG_DM_CATS")
    sets = extract_js_array(js_raw, "ZG_DM_SETS")

    cat_map: dict[int, str] = {}
    for i in range(0, len(cats_flat), 2):
        cat_idx = (i // 2) + 1
        cat_map[cat_idx] = f"{cats_flat[i]}·{cats_flat[i + 1]}"

    records: list[dict[str, Any]] = []
    for idx, row in enumerate(sets, 1):
        cat_idx, subcat, motif, reading = row
        cat_label = f"{cat_map[cat_idx]}·{subcat}"
        motif_s = to_simp(clean_whitespace(motif), t2s)
        # Normalize ASCII comma inside Chinese clauses to fullwidth comma
        reading_s = to_simp(clean_whitespace(reading), t2s).replace(",", "，")
        full = f"{motif_s}：{reading_s}" if reading_s else motif_s
        records.append(
            {
                "id": f"dmms-{idx:04d}",
                "book": "断梦秘书",
                "era": "明清",
                "layer": "omen",
                "category": cat_label,
                "motif": motif_s,
                "reading": reading_s,
                "text": full,
                "polarity": infer_polarity(reading_s),
                "conditions": extract_conditions(full),
                "keywords": extract_keywords(motif_s, reading_s, cat_label),
                "note": "",
                "source_id": "GaoRenYouShu/XuanJiPaiPan:assets/zhougong-duanm.js",
            }
        )
    return records


# ---------------------------------------------------------------------------
# 3. 古本周公解梦二十七类 (GaoRenYouShu/XuanJiPaiPan MIT + daizhigev20 PD)
# ---------------------------------------------------------------------------
def build_zhougong(t2s: dict[str, str]) -> list[dict[str, Any]]:
    js_raw = gh_raw("GaoRenYouShu", "XuanJiPaiPan", "main", "assets/zhougong-data.js")
    cats = extract_js_array(js_raw, "ZG_CATS")
    sets = extract_js_array(js_raw, "ZG_SETS")
    notes_list = extract_js_array(js_raw, "ZG_NOTES")
    poem_m = re.search(r"var\s+ZG_POEM\s*=\s*(['\"])(.*?)\1;", js_raw)
    poem = poem_m.group(2) if poem_m else ""

    # Cross-fetch daizhigev20 周公解梦.txt to confirm opening poem
    dz_zg = gh_raw("garychowcmu", "daizhigev20", "master", "易藏/术数/周公解梦.txt")
    dz_poem_lines = [l.strip() for l in dz_zg.splitlines()[1:6] if l.strip()]
    dz_poem = " ".join(dz_poem_lines)

    notes_map: dict[str, str] = {}
    for entry in notes_list:
        if len(entry) >= 3:
            notes_map[f"{entry[0]}|{entry[1]}"] = entry[2]

    records: list[dict[str, Any]] = []
    if poem or dz_poem:
        poem_text = to_simp(poem or dz_poem, t2s)
        records.append(
            {
                "id": "zg27-0000",
                "book": "周公解梦",
                "era": "明清传本",
                "layer": "theory",
                "category": "卷首总诗",
                "motif": "卷首总诗",
                "reading": poem_text,
                "text": f"诗曰：{poem_text}",
                "polarity": "平/待参",
                "conditions": ["通用"],
                "keywords": ["神魂", "吉凶", "化蝶", "飞熊"],
                "note": "开篇总括历代应梦典故",
                "source_id": "daizhigev20:易藏/术数/周公解梦.txt",
            }
        )

    for idx, row in enumerate(sets, 1):
        cat_idx, motif, reading = row
        cat_name = to_simp(cats[cat_idx - 1], t2s)
        motif_s = to_simp(clean_whitespace(motif), t2s)
        reading_s = to_simp(clean_whitespace(reading), t2s)
        note_s = notes_map.get(f"{motif}|{reading}", "") or notes_map.get(f"{motif_s}|{reading_s}", "")
        full = f"{motif_s}，{reading_s}" if reading_s else motif_s
        records.append(
            {
                "id": f"zg27-{idx:04d}",
                "book": "周公解梦",
                "era": "明清传本",
                "layer": "omen",
                "category": cat_name,
                "motif": motif_s,
                "reading": reading_s,
                "text": full,
                "polarity": infer_polarity(full),
                "conditions": extract_conditions(full),
                "keywords": extract_keywords(motif_s, reading_s, cat_name),
                "note": to_simp(note_s, t2s),
                "source_id": "GaoRenYouShu/XuanJiPaiPan:assets/zhougong-data.js",
            }
        )
    return records


# ---------------------------------------------------------------------------
# 4. 钦定古今图书集成·历象汇编·庶徵典·梦部 (Wikisource 第144-152卷 PD)
# ---------------------------------------------------------------------------
class GJTSJCParser(HTMLParser):
    """Extract clean headings and paragraphs from Wikisource GJTSJC HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.skip_depth = 0
        self.in_block: str | None = None
        self.buf: list[str] = []
        self.blocks: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = dict(attrs)
        cls = ad.get("class") or ""
        el_id = ad.get("id") or ""
        if self.skip_depth > 0:
            self.skip_depth += 1
            return
        if (
            el_id in ("headerContainer", "plainSister", "toc", "catlinks")
            or any(
                c in cls
                for c in (
                    "mw-editsection",
                    "printfooter",
                    "mw-authority-control",
                    "ws-noexport",
                    "noprint",
                    "licensetpl",
                )
            )
            or tag in ("style", "script")
        ):
            self.skip_depth = 1
            return
        if tag in ("h1", "h2", "h3", "h4"):
            self._flush()
            self.in_block = tag
            self.buf = []
        elif tag in ("p", "dd", "li") and self.in_block is None:
            self.in_block = "p"
            self.buf = []
        elif tag == "br" and self.in_block is not None:
            self.buf.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.skip_depth > 0:
            self.skip_depth -= 1
            return
        if tag in ("h1", "h2", "h3", "h4") and self.in_block == tag:
            self._flush()
        elif tag in ("p", "dd", "li") and self.in_block == "p":
            self._flush()

    def handle_data(self, data: str) -> None:
        if self.skip_depth == 0 and self.in_block is not None:
            self.buf.append(data)

    def _flush(self) -> None:
        if self.in_block is not None:
            txt = clean_whitespace("".join(self.buf))
            if txt:
                self.blocks.append((self.in_block, txt))
        self.in_block = None
        self.buf = []


def split_chunks(text: str, max_len: int = 450) -> list[str]:
    """Split long classical text cleanly at sentence endings without cutting mid-sentence."""
    text = text.strip()
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    cur = ""
    # Split on sentence-ending punctuation keeping punctuation attached
    sents = re.split(r"(?<=[。！？；」』])", text)
    for s in sents:
        s = s.strip()
        if not s:
            continue
        if cur and len(cur) + len(s) > max_len:
            chunks.append(cur)
            cur = s
        else:
            cur = f"{cur}{s}" if cur else s
    if cur:
        chunks.append(cur)
    return chunks


def build_gujin_mengbu(t2s: dict[str, str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    idx = 1

    for vol in range(144, 153):
        page = f"欽定古今圖書集成/曆象彙編/庶徵典/第{vol}卷"
        html_raw = wikisource_parse(page)
        parser = GJTSJCParser()
        parser.feed(html_raw)

        # Skip TOC blocks until body heading (h2/h3) appears
        in_body = False
        sec_defaults = {
            144: "梦部汇考",
            145: "梦部艺文一",
            146: "梦部纪事一",
            147: "梦部纪事二",
            148: "梦部纪事三",
            149: "梦部纪事四",
            150: "梦部纪事五",
            151: "梦部纪事六",
            152: "梦部杂录",
        }
        cur_section = sec_defaults.get(vol, f"庶徵典第{vol}卷")
        cur_h2 = ""
        cur_h3 = ""
        footer_re = re.compile(
            r"欢迎各位持续修正标点|古诗文断句|知识共享|Public domain|此作品在全世界|本作品在全世界|版权协议|著作权"
        )
        for btype, btxt in parser.blocks:
            btxt_s = to_simp(btxt.replace("\n", ""), t2s)
            if footer_re.search(btxt_s):
                continue
            if not in_body:
                if btype in ("h1", "h2", "h3", "h4"):
                    in_body = True
                else:
                    continue

            if "谣谶部" in btxt_s:
                break

            # Only treat concise headings (<= 25 chars) as structural headers;
            # Wikisource occasionally wraps body text inside <h2> by mistake.
            if btype in ("h1", "h2") and len(btxt_s) <= 25:
                cur_h2 = btxt_s
                cur_h3 = ""
                if re.match(r"^梦部", cur_h2):
                    cur_section = cur_h2.replace("·", "")
                    cur_h2 = ""
                continue
            if btype in ("h3", "h4") and len(btxt_s) <= 25:
                cur_h3 = btxt_s
                if re.match(r"^梦部", cur_h3):
                    cur_section = cur_h3.replace("·", "")
                    cur_h3 = ""
                continue

            if len(btxt_s) < 8 or re.match(r"^《?庶徵典》?第[一二三四五六七八九十百]+卷。?$", btxt_s):
                continue

            # Determine layer & category
            src_label = " · ".join(x for x in (cur_section, cur_h2, cur_h3) if x and x != cur_section)
            if not src_label:
                src_label = cur_section

            if vol == 144:
                # Vol 144 has 梦部汇考 & 梦部总论; 梦书·解梦 contains direct omens!
                if "梦书" in cur_h2 and "解梦" in cur_h3:
                    layer = "omen"
                else:
                    layer = "theory"
            elif vol == 145:
                layer = "literature"
            else:
                layer = "case"

            # Special handling for 梦书·解梦 short clauses: split by `。` if multiple omens on one paragraph
            if layer == "omen" and "梦" in btxt_s and len(btxt_s) > 60:
                raw_items = [c.strip() + "。" for c in btxt_s.split("。") if c.strip()]
            else:
                raw_items = split_chunks(btxt_s, max_len=500)

            for chunk_i, chunk in enumerate(raw_items):
                if len(chunk) < 4:
                    continue
                prefix = cur_h2 if cur_h2 and not chunk.startswith(cur_h2) and not chunk.startswith("《") else ""
                if prefix and chunk_i == 0:
                    display_text = f"{prefix}：{chunk}"
                elif prefix:
                    display_text = f"（续{prefix}）{chunk}"
                else:
                    display_text = chunk

                motif = cur_h3 or cur_h2 or cur_section
                if layer == "omen" and "，" in chunk:
                    motif = chunk.split("，", 1)[0].strip()

                records.append(
                    {
                        "id": f"gjmb-{idx:04d}",
                        "book": "古今图书集成·梦部",
                        "era": "清",
                        "layer": layer,
                        "category": src_label,
                        "motif": motif,
                        "reading": display_text if layer != "omen" else chunk,
                        "text": display_text,
                        "polarity": infer_polarity(chunk) if layer == "omen" else "平/待参",
                        "conditions": extract_conditions(chunk),
                        "keywords": extract_keywords(motif, chunk, src_label),
                        "note": f"庶徵典第{vol}卷",
                        "source_id": f"zh.wikisource.org:钦定古今图书集成/历象汇编/庶徵典/第{vol}卷",
                    }
                )
                idx += 1
    return records


# ---------------------------------------------------------------------------
# 5. 先秦两汉医家与道藏占梦经典 (daizhigev20 + kanripo PD)
# ---------------------------------------------------------------------------
def clean_kanripo(raw: str, t2s: dict[str, str]) -> str:
    # Remove header metadata lines starting with #
    lines = [l for l in raw.splitlines() if not l.lstrip().startswith("#")]
    txt = "\n".join(lines)
    # Remove <pb:...> markers and ¶
    txt = re.sub(r"<pb:[^>]+>", "", txt)
    txt = txt.replace("¶", "")
    # Clean Kanripo glyph descriptions like {人同U+4F97} -> keep readable fallback or remove tag
    txt = re.sub(r"\{[^}]*U\+[0-9A-Fa-f]+[^}]*\}", "□", txt)
    # Collapse line breaks within paragraphs (Kanripo wraps at ~18 chars)
    txt = re.sub(r"\n(?![　\s]{2,})", "", txt)
    txt = clean_whitespace(txt)
    return to_simp(txt, t2s)


def extract_between(text: str, start_pat: str, end_pat: str) -> str:
    m1 = re.search(start_pat, text)
    if not m1:
        raise ValueError(f"Start pattern not found: {start_pat}")
    sub = text[m1.start() :]
    m2 = re.search(end_pat, sub[len(m1.group(0)) :])
    if m2:
        return sub[: len(m1.group(0)) + m2.start()]
    return sub


def build_classics_theory(t2s: dict[str, str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    idx = 1

    def add_rec(
        book: str,
        era: str,
        layer: str,
        category: str,
        motif: str,
        text: str,
        source_id: str,
        note: str = "",
    ) -> None:
        nonlocal idx
        for ci, chunk in enumerate(split_chunks(clean_whitespace(text), max_len=650)):
            tag = motif if ci == 0 else f"{motif}（续{ci}）"
            records.append(
                {
                    "id": f"clsc-{idx:04d}",
                    "book": book,
                    "era": era,
                    "layer": layer,
                    "category": category,
                    "motif": tag,
                    "reading": chunk,
                    "text": chunk,
                    "polarity": "平/待参",
                    "conditions": extract_conditions(chunk),
                    "keywords": extract_keywords(tag, chunk, category),
                    "note": note,
                    "source_id": source_id,
                }
            )
            idx += 1

    # 5A. 周礼·春官宗伯·占梦
    zl = to_simp(gh_raw("garychowcmu", "daizhigev20", "master", "儒藏/礼经/周礼.txt"), t2s)
    zl_seg = extract_between(zl, r"占梦掌其岁时", r"眡祲掌十煇之法")
    zl_seg = re.sub(r"眡祲掌十煇之法.*$", "", zl_seg).strip()
    add_rec(
        "周礼·占梦",
        "先秦",
        "theory",
        "六梦与岁终赠恶梦",
        "周礼占梦六梦",
        zl_seg,
        "daizhigev20:儒藏/礼经/周礼.txt",
    )

    # 5B. 潜夫论·梦列第二十八
    qfl = to_simp(gh_raw("garychowcmu", "daizhigev20", "master", "儒藏/语录/潜夫论.txt"), t2s)
    qfl_seg = extract_between(qfl, r"梦列第二十八", r"释难第二十九")
    qfl_seg = re.sub(r"释难第二十九.*$", "", qfl_seg).strip()
    add_rec(
        "潜夫论·梦列",
        "东汉",
        "theory",
        "王符十梦论",
        "梦列十梦总论",
        qfl_seg,
        "daizhigev20:儒藏/语录/潜夫论.txt",
    )

    # 5C. 列子·周穆王 (六候与阴阳致梦)
    lz = to_simp(gh_raw("garychowcmu", "daizhigev20", "master", "道藏/藏外/列子.txt"), t2s)
    lz_seg = extract_between(lz, r"觉有八征，梦有六候", r"郑人有薪于野者")
    lz_seg = re.sub(r"郑人有薪于野者.*$", "", lz_seg).strip()
    add_rec(
        "列子·周穆王",
        "先秦魏晋",
        "theory",
        "八征六候与阴阳盈虚",
        "列子六候",
        lz_seg,
        "daizhigev20:道藏/藏外/列子.txt",
    )

    # 5D. 黄帝内经灵枢·淫邪发梦第四十三
    ls = to_simp(gh_raw("garychowcmu", "daizhigev20", "master", "医藏/黄帝内经灵枢.txt"), t2s)
    ls_seg = extract_between(ls, r"淫邪发梦第四十三", r"顺气一日分为四时")
    ls_seg = re.sub(r"顺气一日分为四时.*$", "", ls_seg).strip()
    add_rec(
        "黄帝内经·灵枢",
        "汉代以前",
        "theory",
        "淫邪发梦·五脏盛虚病梦",
        "淫邪发梦第四十三",
        ls_seg,
        "daizhigev20:医藏/黄帝内经灵枢.txt",
    )

    # 5E. 论衡·订鬼篇 (思念存想与卧梦病象辨)
    lh = to_simp(gh_raw("garychowcmu", "daizhigev20", "master", "子藏/笔记/论衡.txt"), t2s)
    dg_seg = extract_between(lh, r"订鬼篇\s*凡天地之间有鬼", r"一曰鬼者人所见")
    dg_seg = re.sub(r"一曰鬼者人所见.*$", "", dg_seg, flags=re.S).strip()
    add_rec(
        "论衡·订鬼",
        "东汉",
        "theory",
        "思念存想与病梦辨",
        "论衡辨鬼梦",
        dg_seg,
        "daizhigev20:子藏/笔记/论衡.txt",
    )

    # 5F. 佛典旁证：阿难七梦经
    an = to_simp(
        gh_raw("garychowcmu", "daizhigev20", "master", "佛藏/大藏经/经藏/经集部/阿难七梦经.txt"),
        t2s,
    )
    an_seg = extract_between(an, r"阿难在舍卫国", r"$")
    add_rec(
        "阿难七梦经",
        "东晋译本",
        "theory",
        "佛典旁证",
        "阿难七梦",
        an_seg,
        "daizhigev20:佛藏/大藏经/经藏/经集部/阿难七梦经.txt",
        note="佛典示现比喻，仅作旁证",
    )

    # 5G. 道藏·黄帝龙首经·占怪祟恶梦法第六十六 (kanripo/KR5a0295)
    kr5a = clean_kanripo(
        gh_raw("kanripo", "KR5a0295", "master", "KR5a0295_002.txt"), t2s
    )
    kr5a_seg = extract_between(kr5a, r"占怪[祟崇]恶梦法第六十六", r"占知死人魂魄出否法")
    kr5a_seg = re.sub(r"占知死人魂魄出否法.*$", "", kr5a_seg).strip()
    add_rec(
        "道藏·黄帝龙首经",
        "汉晋",
        "rang",
        "占怪祟恶梦法",
        "占怪祟恶梦法第六十六",
        kr5a_seg,
        "kanripo/KR5a0295:KR5a0295_002.txt",
    )

    # 5H. 道藏·洞玄灵宝道学科仪·解恶梦品 (kanripo/KR5e0028)
    kr5e28 = clean_kanripo(
        gh_raw("kanripo", "KR5e0028", "master", "KR5e0028_000.txt"), t2s
    )
    kr5e28_seg = extract_between(kr5e28, r"解恶梦品", r"父[毋母]品")
    kr5e28_seg = re.sub(r"父[毋母]品.*$", "", kr5e28_seg).strip()
    add_rec(
        "道藏·洞玄灵宝道学科仪",
        "唐",
        "rang",
        "解恶梦品",
        "道学解恶梦法",
        kr5e28_seg,
        "kanripo/KR5e0028:KR5e0028_000.txt",
    )

    # 5I. 道藏·法海遗珠·应梦占验 & 附梦秘法 (kanripo/KR5e0068)
    kr5e68 = clean_kanripo(
        gh_raw("kanripo", "KR5e0068", "master", "KR5e0068_042.txt"), t2s
    )
    ym_seg = extract_between(kr5e68, r"应梦占验", r"$")
    add_rec(
        "道藏·法海遗珠",
        "明",
        "rang",
        "应梦占验",
        "应梦占验",
        ym_seg[:1200],
        "kanripo/KR5e0068:KR5e0068_042.txt",
    )
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> str:
    content = "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n"
    path.write_text(content, encoding="utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def main() -> None:
    REFS_DIR.mkdir(parents=True, exist_ok=True)
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)

    print("1/6 Building Traditional->Simplified dictionary...")
    t2s = build_t2s_map()
    syn_path = REFS_DIR / "synonym-xieyin.json"
    if syn_path.exists():
        syn_data = json.loads(syn_path.read_text(encoding="utf-8"))
        syn_data["trad_to_simp"] = t2s
        syn_path.write_text(json.dumps(syn_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        syn_path.write_text(
            json.dumps({"schema_version": 1, "trad_to_simp": t2s}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"    trad_to_simp in synonym-xieyin.json: {len(t2s)} chars")

    print("2/6 Building 梦林玄解...")
    ml_records = build_menglin(t2s)
    print(f"    梦林玄解 records: {len(ml_records)}")

    print("3/6 Building 断梦秘书...")
    dm_records = build_duanmeng(t2s)
    print(f"    断梦秘书 records: {len(dm_records)}")

    print("4/6 Building 古本周公解梦...")
    zg_records = build_zhougong(t2s)
    print(f"    周公解梦 records: {len(zg_records)}")

    print("5/6 Building 钦定古今图书集成·梦部 (Wikisource vol 144-152)...")
    gj_records = build_gujin_mengbu(t2s)
    print(f"    古今图书集成·梦部 records: {len(gj_records)}")

    print("6/6 Building 先秦两汉与道藏经典...")
    cl_records = build_classics_theory(t2s)
    print(f"    先秦两汉与道藏经典 records: {len(cl_records)}")

    files = {
        "menglin_xuanjie.jsonl": ml_records,
        "duanmeng_mishu.jsonl": dm_records,
        "zhougong_27.jsonl": zg_records,
        "gujin_mengbu.jsonl": gj_records,
        "classics_theory.jsonl": cl_records,
    }

    manifest_files: dict[str, Any] = {}
    book_counts: dict[str, int] = {}
    layer_counts: dict[str, int] = {}
    total = 0

    for fname, recs in files.items():
        fpath = CORPUS_DIR / fname
        sha = write_jsonl(fpath, recs)
        b_cnt: dict[str, int] = {}
        l_cnt: dict[str, int] = {}
        for r in recs:
            assert r["text"], f"Empty text in {fname}: {r['id']}"
            if fname == "classics_theory.jsonl":
                assert len(r["text"]) <= 1500, f"Oversized record in {fname}: {r['id']} ({len(r['text'])})"
            b_cnt[r["book"]] = b_cnt.get(r["book"], 0) + 1
            l_cnt[r["layer"]] = l_cnt.get(r["layer"], 0) + 1
            book_counts[r["book"]] = book_counts.get(r["book"], 0) + 1
            layer_counts[r["layer"]] = layer_counts.get(r["layer"], 0) + 1
        manifest_files[fname] = {
            "count": len(recs),
            "bytes": fpath.stat().st_size,
            "sha256": sha,
            "books": b_cnt,
            "layers": l_cnt,
        }
        total += len(recs)

    manifest = {
        "schema_version": 1,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_records": total,
        "books": book_counts,
        "layers": layer_counts,
        "files": manifest_files,
        "sources": [
            {
                "name": "梦林玄解（十六部类词典+卷首序论）",
                "upstream": "https://github.com/ycc77cn/skills",
                "license": "MIT",
            },
            {
                "name": "梦林玄解·卷之首占繇（观天地之会/辨二气之乘/审三辰之象）",
                "upstream": "https://zh.wikisource.org/wiki/夢林玄解/夢林玄解卷之首",
                "license": "Public Domain",
            },
            {
                "name": "断梦秘书（中编九类）",
                "upstream": "https://github.com/GaoRenYouShu/XuanJiPaiPan",
                "license": "MIT",
            },
            {
                "name": "古本周公解梦二十七类（951句+卷首诗）",
                "upstream": "https://github.com/GaoRenYouShu/XuanJiPaiPan & https://github.com/garychowcmu/daizhigev20",
                "license": "MIT / Public Domain",
            },
            {
                "name": "钦定古今图书集成·历象汇编·庶徵典·梦部（第144-152卷）",
                "upstream": "https://zh.wikisource.org/wiki/欽定古今圖書集成/曆象彙編/庶徵典/夢部",
                "license": "Public Domain",
            },
            {
                "name": "周礼·占梦 / 潜夫论·梦列 / 列子·周穆王 / 灵枢·淫邪发梦 / 论衡·订鬼 / 阿难七梦经",
                "upstream": "https://github.com/garychowcmu/daizhigev20",
                "license": "Public Domain",
            },
            {
                "name": "道藏占梦与梦禳（黄帝龙首经/洞玄灵宝道学科仪/法海遗珠）",
                "upstream": "https://github.com/kanripo",
                "license": "Public Domain",
            },
        ],
        "coverage_notes": [
            "《梦林玄解》当前收录卷首序论、占繇三篇正文与7部16类梦占辞条；其余梦占卷与梦禳正文如后续获得公版干净校本可继续扩充。",
            "《断梦秘书》中编十二地支类当前收录子至申九类；酉饮食、戌器物、亥珍宝三类公开文本暂缺。",
            "《周公解梦》二十七类951句完整收录并保留原刻异文校注。",
            "《古今图书集成·梦部》第144至152卷全数清洗分块入库，涵括汇考、总论、艺文、历代纪事六卷、杂录与外编。",
        ],
    }
    (CORPUS_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nDONE! Total records={total} written to {CORPUS_DIR}")


if __name__ == "__main__":
    main()
