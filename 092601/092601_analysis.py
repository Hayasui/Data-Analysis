# -*- coding: utf-8 -*-
"""日本 MMORPG 玩家定量调研 —— 投后数据分析（脚本 092601_analysis）

这一支与 092601_cleaning.py 配对：清洗脚本把平台导出收成分析文件，这一支从分析文件算读数，
每一步都留痕，第三方拿着两个脚本与原数据能重算出同一批数字。它不出结论、不写报告，
出的是报告要引用的分布表与精度。三件事按顺序做完：

  第一段  读入与口径核对。规模、列、人键、三个派生标记、剔除缺口都过一遍，对不上就停。
  第二段  逐题分布表：单选列摆出全部码，多选一项一行，矩阵按行按说法摆开。
          分母按各题清洗后的有效 N（不含 97／98／99），Q8／Q12／Q29／Q37 不再扣 98——
          文件里的 N 已经是扣完 98 的数。
  第三段  三块要单算的东西：Q22 的逐款并排与跨款配对（含 McNemar 精确检验）、
          两种口径的差（is_mmorpg 与 play_mmorpg，52 与 67 人）、Q9 的 381 条自由文本。

每个比例后面跟一个 ME（margin of error，误差幅度，95% 置信区间的半宽），
按正态近似 1.96×√(p(1−p)/n) 算，单位是百分点。N 小的时候 ME 会很大，
读的时候一并看：N=20 时最坏约 ±22pp、N=100 约 ±10pp、N=212 约 ±7pp。
它只管随机抽样误差，不含配额样本本身的选择偏差。

输入  data/RPG.csv        579 行 × 427 列，第一行是变量名，由 092601_cleaning.py 产出
      data/Original.csv   可选；给了就从它的第二行表头取题面与选项正文，标签不至于靠手抄
输出  data/分析表.csv      一行一个读数，长表，给机器读与比对
      data/分析结果.md     同一批数字按议题排开，给人读
      data/分析日志.txt    每一步做了什么、分母怎么来的、自检过没过
      data/Q9文本.csv      381 条自由文本的原文与标记，人工归类用

用法  python 092601_analysis.py                       默认读 data/RPG.csv，写 data/
      python 092601_analysis.py RPG.csv 输出目录      换路径；Original.csv 自动在输入旁边找
      python 092601_analysis.py RPG.csv 输出目录 --check   只重算并与现有产物比对，不写盘

口径出处：各题分母见 数据清洗说明.md 的「各题分母」一节，值码见 值码表.md；
本脚本里的单选题码表与那两张表逐项对齐，改了清洗脚本要一并核这里。
"""
import collections
import csv
import io
import math
import os
import sys

# =============================================================== 0 路径与常量
CHECK_ONLY = "--check" in sys.argv
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = ARGS[0] if ARGS else os.path.join(HERE, "data", "RPG.csv")
OUTDIR = ARGS[1] if len(ARGS) > 1 else os.path.dirname(os.path.abspath(SRC))
if len(ARGS) > 2:
    TEXTS_SRC = ARGS[2]
else:
    TEXTS_SRC = os.path.join(os.path.dirname(os.path.abspath(SRC)), "Original.csv")
RES_OUT = os.path.join(OUTDIR, "分析表.csv")
MD_OUT = os.path.join(OUTDIR, "分析结果.md")
LOG_OUT = os.path.join(OUTDIR, "分析日志.txt")
Q9_OUT = os.path.join(OUTDIR, "Q9文本.csv")

NA = ("97", "98", "99")
Z = 1.959964          # 95% 区间
SMALL_N = 20          # Q22 逐款并排的门槛：低于这个数只报数、不并排读
PAIR_N = 20           # 跨款配对进 CSV 的门槛
PAIR_MD = 40          # 跨款配对进 markdown 正文的门槛

LOG = []


def say(s=""):
    LOG.append(s)


def section(t):
    say("")
    say("=" * 78)
    say(t)
    say("=" * 78)


def pct(c, n):
    return None if not n or c < 0 else 100.0 * c / n


def me(c, n):
    """比例的 ME，单位百分点。N 为 0 时不报。"""
    if not n or c < 0:
        return None
    p = float(c) / n
    return Z * math.sqrt(p * (1.0 - p) / n) * 100.0


def r1(x):
    return "—" if x is None else x if isinstance(x, str) else "%.1f" % x


# --------------------------------------------------------------- 单选题的码
# 与 092601_cleaning.py 的 CODES 逐项对齐，也印在 值码表.md 里。
GAMES = ["ファイナルファンタジーXIV", "BLUE PROTOCOL", "黒い砂漠 MOBILE", "リネージュM",
         "リネージュ2M", "オーディン：ヴァルハラ・ライジング", "Ash Tale-風の大陸-",
         "ツリーオブセイヴァー：ネバーランド", "杖と剣の伝説", "AZUREA-空の唄-",
         "ディアブロ イモータル", "コード：ドラゴンブラッド", "二ノ国：Cross Worlds",
         "ラグナロクオンライン", "ラグナロク マスターズ", "ラグナロクX", "ラグナロクオリジン"]
PAY = ["課金はしていない", "1000円以内", "1000～3000円", "3000～5000円", "5000～1万円",
       "1万～3万円", "3万～5万円", "5万円以上"]
DUR = ["3 个月以内", "3–6 个月", "6 个月–1 年", "1–3 年", "3–5 年", "5 年以上"]
DUR2 = ["3ヶ月未満", "3～6ヶ月", "6ヶ月～1年", "1年～3年", "3年～5年", "5年以上"]
HRS = ["30分未満", "30分～1時間", "1時間～2時間", "2時間～3時間", "3時間～5時間", "5時間以上"]
JOB = ["学生", "一般社員", "管理職", "公務員", "フリーランス", "自営業・経営者",
       "専業主婦・主夫", "求職中・無職", "定年退職者", "その他（具体的にご記入ください）"]
INC37 = ["ほとんどない", "5000円未満", "5000～1万円", "1万～3万円", "3万～5万円",
         "5万～10万円", "10万円以上"]
REGION = ["Hokkaido", "Tohoku", "Kanto", "Chubu", "Kansai", "Chugoku", "Shikoku",
          "Kyushu / Okinawa"]
RO_CODES = ["このIPがとても好きで、ROシリーズ作品をプレイしたことがある",
            "ROシリーズ作品をプレイしたことはあるが、特に好きというわけではない",
            "IPの名前を聞いたことはあるが、ゲーム内容についてはよく知らない",
            "このIP自体を知らないし、ゲームについてもわからない"]
WANT_CODES = ["全くプレイしたくない", "プレイしたくない", "どちらとも言えない",
              "ややプレイしてみたい", "ぜひプレイしてみたい"]
STYLE_CODES = ["アクティブ型：自分から積極的に声をかけてパーティーを組んだり、ギルドイベントに参加する",
               "パッシブ（聞き専）型：自分から積極的には動かないが、他人のチャットを眺めたり、"
               "パーティー参加時も基本的には無言でついていく",
               "ソロプレイ型：基本的には誰ともコミュニケーションせず、ひとりでプレイする",
               "状況による（ゲームの雰囲気、リアルタイムの余裕、友人がプレイしているか等によって変わる）"]
AGE = ["18-29", "30-49", "50-60"]
def codes(lst, extra=None):
    """有序题的码：1 对应问卷里的第一个选项，另可追加缺失族或拒答码。"""
    d = dict(enumerate(lst, start=1))
    d.update(extra or {})
    return d


SINGLE = {
    "GENDER_NonBinary": ("S4", {0: "男性（分析侧约定）", 1: "女性（分析侧约定）",
                                98: "回答しない", 99: "その他（平台另加的类目）"}),
    "QUOTAGERANGE": ("S5", dict(enumerate(AGE, start=1))),
    "JPSTDREGION": ("（面板）", dict(enumerate(REGION, start=1))),
    "IDP52": ("Q5", dict(enumerate(GAMES, start=1))),
    "IDP34": ("Q6", dict(enumerate(DUR, start=1))),
    "IDP35": ("Q7", dict(enumerate(HRS, start=1))),
    "IDP36": ("Q8", codes(PAY, {98: "回答したくない"})),
    "IDP38": ("Q10", dict(enumerate(DUR2, start=1))),
    "IDP39": ("Q11", dict(enumerate(HRS, start=1))),
    "IDP40": ("Q12", codes(PAY, {98: "回答したくない"})),
    "IDP41": ("Q13", dict(enumerate(RO_CODES, start=1))),
    "IDP42": ("Q14", dict(enumerate(WANT_CODES, start=1))),
    "IDP55": ("Q23", dict(enumerate(STYLE_CODES, start=1))),
    "IDP61": ("Q29", codes(PAY, {98: "回答したくない"})),
    "IDP63": ("Q31", {1: "している", 2: "していない"}),
    "IDP68": ("Q36", dict(enumerate(JOB, start=1))),
    "IDP69": ("Q37", codes(INC37, {98: "回答したくない"})),
}
# 多选题的题号与前缀
MULTI = [("S3", "SCREENER3"), ("Q2", "IDP30"), ("Q3", "IDP50"), ("Q4", "IDP51"),
         ("Q15", "IDP43"), ("Q16", "IDP44"), ("Q18", "IDP46"), ("Q19", "IDP47"),
         ("Q20", "IDP48"), ("Q21", "IDP49"), ("Q24", "IDP56"), ("Q25", "IDP57"),
         ("Q26", "IDP58"), ("Q27", "IDP59"), ("Q30", "IDP62"), ("Q32", "IDP64"),
         ("Q33", "IDP65"), ("Q34", "IDP66"), ("Q35", "IDP67")]
RO_G = (14, 15, 16, 17)          # Q2／Q3 的 17 款里属于 RO 系列的那四款
RO_OTHER = "IDP30__18"           # Q2 的「その他 RO 系列」


# =============================================================== 1 读入
if not os.path.exists(SRC):
    print("找不到输入文件：%s" % SRC)
    print("先用 092601_cleaning.py 从原始导出生成 RPG.csv，再把它指到这里。")
    sys.exit(2)

with io.open(SRC, encoding="utf-8-sig", newline="") as fh:
    rd = csv.reader(fh)
    HEAD = next(rd)
    BODY = [list(r) for r in rd]
N = len(BODY)
P = {h: i for i, h in enumerate(HEAD)}
section("一、读入与口径核对")
say("输入 %s：%d 行 × %d 列。" % (os.path.basename(SRC), N, len(HEAD)))
say("这份表是受访者级的，一人一行；第一行是变量名，没有第二行表头。")

FAIL = []


def need(cond, msg):
    if not cond:
        FAIL.append(msg)


need(N == 579, "行数应为 579（600 人剔除 21 人），实测 %d" % N)
need(len(HEAD) == 427, "列数应为 427，实测 %d" % len(HEAD))
need(HEAD[-4:] == ["is_mmorpg", "play_mmorpg", "not_mmo_mostplay", "nested_ok"],
     "末四列不是四个派生标记：%s" % HEAD[-4:])
need("ID" in P and "iirepSerial" in P, "缺 ID 或 iirepSerial，这不像清洗脚本产出的文件")

COL = {h: [r[P[h]] for r in BODY] for h in HEAD}
for h, i in P.items():
    COL[h] = [r[i] for r in BODY]
ID = [r[P["ID"]] for r in BODY]


def yes(h):
    return {k for k, v in enumerate(COL[h]) if v == "1"}


def valid(h):
    return {k for k, v in enumerate(COL[h]) if v not in NA and v != ""}


def count(h, code):
    return sum(1 for v in COL[h] if v == str(code))


need(len(set(ID)) == N, "ID 不是 %d 个唯一值" % N)
GONE = sorted(set(range(1, 601)) - {int(x) for x in ID})
need(GONE == [11, 15, 33, 118, 140, 161, 282, 311, 312, 335, 348, 378, 387, 391, 435, 495,
              501, 564, 576, 582, 594], "ID 的缺口与既定的剔除名单不符：%s" % GONE)
need(not [1 for r in BODY for v in r if v == ""], "表里还有空白")

# ---- 题面与选项正文：可选，从原始导出的第二行表头取
TEXTS = {}
if os.path.exists(TEXTS_SRC):
    with io.open(TEXTS_SRC, encoding="utf-8-sig", newline="") as fh:
        rd = csv.reader(fh)
        h1 = next(rd)
        h2 = next(rd)
    TEXTS = dict(zip(h1, h2))
    say("题面与选项正文取自 %s 的第二行表头。" % os.path.basename(TEXTS_SRC))
else:
    say("没有找到 %s，题面一栏留空，选项标签用脚本里的码表（与 值码表.md 一致）。"
        % os.path.basename(TEXTS_SRC))


def opt(h):
    """某一列在原始导出第二行里的选项正文（「题干 - 选项」的右半边）。"""
    t = TEXTS.get(h, "")
    return (t.split(" - ", 1)[1] if " - " in t else t).strip() or h


def stem(h):
    """题干：原始导出第二行里「题干 - 选项」的左半边，截到 46 字。"""
    t = TEXTS.get(h, "")
    t = (t.split(" - ", 1)[0] if " - " in t else t).strip() or h
    return t if len(t) <= 46 else t[:45] + "…"


# 行标记的款式与顺序必须与问卷一致：拿原始表头核一遍，题序错位立刻拦下
for g in range(1, 18):
    lab = opt("IDP53__%d" % g)
    if TEXTS:
        need(lab == GAMES[g - 1], "Q22 第 %d 行是「%s」，码表里第 %d 款是「%s」"
             % (g, lab, g, GAMES[g - 1]))
CLAIMS = []
for s in range(1, 9):
    t = opt("IDP54/L469__%d" % s)
    CLAIMS.append(t if t != "IDP54/L469__%d" % s else "说法 %d" % s)

# ---- 三个派生标记与两个口径
PLAY = yes("play_mmorpg")
IS_MMO = yes("is_mmorpg")
NOT_MAIN = yes("not_mmo_mostplay")          # 1 = 走 Q9 至 Q12 的支线
NESTED = yes("nested_ok")
Q4_PICK = {k for k in range(N) if any(COL["IDP51__%d" % g][k] == "1" for g in range(1, 18))}
Q3_PICK = {k for k in range(N) if any(COL["IDP50__%d" % g][k] == "1" for g in range(1, 18))}
need(len(PLAY) == 293, "play_mmorpg=1 应为 293，实测 %d" % len(PLAY))
need(len(IS_MMO) == 278, "is_mmorpg=1 应为 278，实测 %d" % len(IS_MMO))
need(Q3_PICK == PLAY, "play_mmorpg 与 Q3 的勾选不是同一批人")
need(Q4_PICK == yes("IDP51__1") or len(Q4_PICK) == 198,
     "Q4 勾到至少一款的应为 198，实测 %d" % len(Q4_PICK))
need(NOT_MAIN == set(range(N)) - Q4_PICK, "not_mmo_mostplay 与「Q4 没勾到游戏」不是同一批人")
need(len(IS_MMO - PLAY) == 52 and len(PLAY - IS_MMO) == 67,
     "两个口径之差应为 52／67，实测 %d／%d" % (len(IS_MMO - PLAY), len(PLAY - IS_MMO)))

# ---- 各题分母锚点：与 数据清洗说明.md 的「各题分母」一节同源
BASE_ANCHOR = [("SCREENER1__1", 579, "S1 全卷"), ("IDP30__1", 579, "Q2 全卷"),
               ("IDP50__1", 510, "Q3 Q2 未走逃亡口"), ("IDP51__1", 293, "Q4 = play_mmorpg"),
               ("IDP52", 198, "Q5 主支"), ("IDP34", 198, "Q6"), ("IDP35", 198, "Q7"),
               ("IDP36", 196, "Q8 主支、扣 98"), ("IDP37", 381, "Q9 支线"),
               ("IDP40", 371, "Q12 支线、扣 98"), ("IDP41", 579, "Q13 全卷"),
               ("IDP42", 579, "Q14 全卷"), ("IDP43__1", 146, "Q15 Q14 选不想"),
               ("IDP44__1", 221, "Q16 Q14 选想"), ("IDP46__1", 293, "Q18 = play_mmorpg"),
               ("IDP49__1", 268, "Q21 门槛内且未一直在玩"), ("IDP53__1", 293, "Q22"),
               ("IDP55", 293, "Q23"), ("IDP56__1", 206, "Q24 门槛内且非独狼"),
               ("IDP61", 564, "Q29 全卷、扣 98"), ("IDP64__1", 232, "Q32 关注 KOL 的人"),
               ("IDP69", 565, "Q37 全卷、扣 98")]
for h, want, why in BASE_ANCHOR:
    need(len(valid(h)) == want, "%s（%s）的有效 N 应为 %d，实测 %d"
         % (h, why, want, len(valid(h))))
say("")
say("分母锚点 %d 处全部对上；三个派生标记逐行一致；剔除的 21 人 ID 缺口与既定名单一致。"
    % len(BASE_ANCHOR))

# =============================================================== 2 读数
# 一行一个读数：议题、题号、组标题、变量、选项、基数、计数、占比、ME、备注
R = []


def add(block, q, title, var, label, base, cnt, note="", pctv=None, mev=None, md=True):
    """一条读数。配对比较那几个数不是「占比」，用 pctv 与 mev 直接给。
    md=False 的只进 分析表.csv，不进 markdown（配对样本太小的那些）。"""
    R.append({"block": block, "q": q, "title": title, "var": var, "label": label,
              "base": base, "cnt": cnt,
              "pct": pct(cnt, base) if pctv is None else pctv,
              "me": me(cnt, base) if mev is None else mev,
              "note": note, "md": md})


def single(block, q, var, base_var=None, note="", title=None):
    """单选题：一个码一行，码按问卷顺序摆全，没人选的也留着。"""
    codes = SINGLE[var][1]
    b = len(valid(base_var or var))
    title = title or "%s　%s" % (q, stem(base_var or var))
    for c in sorted(codes):
        miss = c in (98, 99)
        add(block, q, title, var,
            "%s = %s%s" % (c, codes[c], "（不进基数）" if miss else ""),
            b, count(var, c), note,
            pctv="—" if miss else None, mev="—" if miss else None)


def multi(block, q, prefix, title=None, note=""):
    """多选题：一项一行，按勾选数从多到少排。"""
    cols = [h for h in HEAD if h == prefix or h.startswith(prefix + "__")]
    base = len(valid(cols[0])) if cols else 0
    title = title or "%s　%s" % (q, stem(cols[0]))
    rows = [(len(yes(h)), h) for h in cols]
    for c, h in sorted(rows, key=lambda x: (-x[0], HEAD.index(x[1]))):
        add(block, q, title, h, opt(h), base, c, note)


section("二、逐题分布表")
say("分母取各题清洗后的有效 N（不含 97／98／99）。Q8／Q12／Q29／Q37 报告时扣 98，")
say("文件里的有效 N 已经是扣完的数，所以直接用；四题的 98 分别是 %d／%d／%d／%d 人。"
    % (count("IDP36", 98), count("IDP40", 98), count("IDP61", 98), count("IDP69", 98)))

B1 = "议题一　MMORPG 与 RO IP 的基本盘"
B2 = "议题二　品类形象（Q22）"
B3 = "议题三　卖点与痛点"
B4 = "议题四　社交惯习与付费"
B5 = "议题五　触媒与内容消费"
B6 = "附　两个口径的差与 Q9 待归类文本"

say("")
say("—— 议题一：样本构成与主玩游戏 ——")
for v, q in [("GENDER_NonBinary", "S4"), ("QUOTAGERANGE", "S5"), ("JPSTDREGION", "（面板）")]:
    single(B1, q, v)
multi(B1, "S3", "SCREENER3")
multi(B1, "Q2", "IDP30", note="全卷 579 人；本题是「听说过」层")
multi(B1, "Q3", "IDP50", note="Q2 未走逃亡口的 510 人；__18 是「一款都没玩过」的逃亡项")
multi(B1, "Q4", "IDP51", note="play_mmorpg=1 的 293 人；Q3 逃亡口的 217 人在本题作废")

# Q2 → Q3 → Q4 的逐款漏斗，另给同基数（293 人）的转化
title = "Q2→Q3→Q4 逐款漏斗（三列各有各的分母）"
for g in range(1, 18):
    h2, h3, h4 = ("IDP30__%d" % g, "IDP50__%d" % g, "IDP51__%d" % g)
    a, b, c = len(yes(h2)), len(yes(h3)), len(yes(h4))
    in_gate_heard = len(yes(h2) & PLAY)
    add(B1, "漏斗", title, "Q2__%d" % g,
        "%s：听说过（/579）" % GAMES[g - 1], N, a, "")
    add(B1, "漏斗", title, "Q3__%d" % g,
        "%s：玩过（/510）" % GAMES[g - 1], len(valid("IDP50__1")), b, "")
    add(B1, "漏斗", title, "Q4__%d" % g,
        "%s：还在玩（/293）" % GAMES[g - 1], len(valid("IDP51__1")), c, "")
    add(B1, "漏斗", title, "同基数__%d" % g,
        "%s：293 人里听说过的人中有多少玩过" % GAMES[g - 1], in_gate_heard, b,
        "分子分母都在 play_mmorpg=1 的 293 人内部，不受 Q2／Q3 越界影响")

single(B1, "Q13", "IDP41", note="全卷；1＝最喜欢且玩过 RO 系列，4＝完全不了解")
single(B1, "Q14", "IDP42", note="全卷；1＝完全不想，5＝非常想")
for c in sorted(SINGLE["IDP41"][1]):
    grp = {k for k in range(N) if COL["IDP41"][k] == str(c)}
    w = len({k for k in grp if COL["IDP42"][k] in ("4", "5")})
    add(B1, "Q13×Q14", "Q13 各层的新作意愿", "Q13=%d" % c,
        "%s → 想玩（4／5 码）" % SINGLE["IDP41"][1][c], len(grp), w,
        "新作意愿是 Q14 的 4／5 码合计；基数只有本案 579 人")

say("")
say("—— 议题二：Q22 逐款并排与跨款配对 ——")
Q22_ROWS = {}
for g in range(1, 18):
    Q22_ROWS[g] = yes("IDP53__%d" % g)
    need(Q22_ROWS[g] == (yes("IDP50__%d" % g) & PLAY),
         "Q22 第 %d 行应等于「Q3 勾了这款且在 play_mmorpg 门槛内」的人" % g)
    need(len(Q22_ROWS[g]) >= SMALL_N,
         "Q22 第 %d 行只有 %d 人，低于并排门槛 %d" % (g, len(Q22_ROWS[g]), SMALL_N))
need(len(Q22_ROWS[1]) == 212, "FFXIV 一行的 N 应为 212，实测 %d" % len(Q22_ROWS[1]))
add(B2, "Q22", "应答题人群", "（基数）",
    "play_mmorpg=1 的 293 人；逐款 N 从 %d 到 %d"
    % (min(len(Q22_ROWS[g]) for g in range(1, 18)),
       max(len(Q22_ROWS[g]) for g in range(1, 18))), 293, 293,
    "八条说法各是 0/1，只能读勾选率，不能当量表算均分")
for g in range(1, 18):
    b = len(Q22_ROWS[g])
    for s in range(1, 9):
        h = "IDP54/L%d__%d" % (468 + g, s)
        cnt = sum(1 for k in Q22_ROWS[g] if COL[h][k] == "1")
        note = "八条说法之一，0/1 变量" if b >= SMALL_N else "N<20，只报数"
        add(B2, "Q22", "%s（N=%d）" % (GAMES[g - 1], b), h, "C%d %s" % (s, CLAIMS[s - 1]),
            b, cnt, note)

# 跨款配对：同一人给两款都打过勾的，才算得进配对
PAIRS = []
for a in range(1, 18):
    for b in range(a + 1, 18):
        both = Q22_ROWS[a] & Q22_ROWS[b]
        if len(both) >= PAIR_N:
            PAIRS.append((len(both), a, b))


def mcnemar_exact(b, c):
    """配对二值比例的精确 McNemar：在 b＋c 次不一致里，一边不占优。"""
    m = b + c
    if m == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(m, i) for i in range(k + 1)) / float(2 ** m)
    return min(1.0, 2 * tail)


say("")
say("跨款配对：17 款两两组合里，同一个人给两款都打过勾的共 %d 对达到 N≥%d。" % (len(PAIRS), PAIR_N))
for n_pair, a, b in sorted(PAIRS, key=lambda x: (-x[0], x[1], x[2])):
    both = Q22_ROWS[a] & Q22_ROWS[b]
    for s in range(1, 9):
        ha = "IDP54/L%d__%d" % (468 + a, s)
        hb = "IDP54/L%d__%d" % (468 + b, s)
        pa = sum(1 for k in both if COL[ha][k] == "1")
        pb = sum(1 for k in both if COL[hb][k] == "1")
        only_a = sum(1 for k in both if COL[ha][k] == "1" and COL[hb][k] == "0")
        only_b = sum(1 for k in both if COL[hb][k] == "1" and COL[ha][k] == "0")
        se = math.sqrt(max(0.0, (only_a + only_b) - (only_a - only_b) ** 2 / float(n_pair))) \
            / n_pair
        p = mcnemar_exact(only_a, only_b)
        add(B2, "Q22 配对", "%s − %s（配对 N=%d）" % (GAMES[a - 1], GAMES[b - 1], n_pair),
            "配对 C%d" % s, "C%d %s" % (s, CLAIMS[s - 1]), n_pair, only_a - only_b,
            "%s %.1f%% ／ %s %.1f%%；差 %+.1fpp，ME ±%.1fpp，McNemar 精确 p=%.3f"
            % (GAMES[a - 1], pct(pa, n_pair), GAMES[b - 1], pct(pb, n_pair),
               pct(pa, n_pair) - pct(pb, n_pair), Z * se * 100, p),
            pctv=pct(pa, n_pair) - pct(pb, n_pair), mev=Z * se * 100,
            md=(n_pair >= PAIR_MD))

say("")
say("—— 议题三：卖点与痛点 ——")
for q, pre, note in [("Q18", "IDP46", "门槛内 293 人；本题是清单内部的相对排序，读不出因果"),
                     ("Q19", "IDP47", "同上"),
                     ("Q20", "IDP48", "同上"),
                     ("Q21", "IDP49", "门槛内且 Q20 未选「一直在玩」的 268 人"),
                     ("Q15", "IDP43", "Q14 选不想体验的 146 人；清单内相对排序"),
                     ("Q16", "IDP44", "Q14 选想体验的 221 人；清单内相对排序")]:
    multi(B3, q, pre, note=note)

say("")
say("—— 议题四：社交惯习与付费 ——")
single(B4, "Q23", "IDP55", note="门槛内 293 人；选独狼的不答 Q24 与 Q25")
multi(B4, "Q24", "IDP56", note="门槛内且非独狼 206 人；需要说明这是清单内的相对排序")
multi(B4, "Q25", "IDP57", note="同 Q24；本题不设上限，各项之和大于人数")
multi(B4, "Q26", "IDP58", note="门槛内 293 人；没有「从未付费」的出口")
multi(B4, "Q27", "IDP59", note="门槛内 293 人；同上")
for q, v, note in [("Q8", "IDP36", "主支自报的那一款，196 人（另有 2 人拒答已扣）"),
                   ("Q12", "IDP40", "支线那款，371 人（另有 10 人拒答已扣）"),
                   ("Q29", "IDP61", "全游戏合计，564 人（另有 15 人拒答已扣）")]:
    single(B4, q, v, note=note)
    b = len(valid(v))
    paid = b - count(v, 1)
    add(B4, q, v, v, "（派生）有过付费：除第一项以外的所有档位", b, paid,
        "上端封在「5 万円以上」，这一档里读不出倍数")
for q, v in [("Q8", "IDP36"), ("Q29", "IDP61")]:
    b = len(valid(v))
    add(B4, "付费近似切分", "%s 的未付费出口" % q, v, "课金はしていない 一项的比例", b,
        count(v, 1), "Q26 与 Q27 没有未付费出口，要切分只能用这几题的第一项近似")
multi(B4, "S3", "SCREENER3", title="S3 设备（全卷 579 人）")

say("")
say("—— 议题五：触媒与内容消费 ——")
multi(B5, "Q30", "IDP62", note="全卷 579 人")
single(B5, "Q31", "IDP63", note="全卷；1＝关注 KOL／VTuber")
multi(B5, "Q32", "IDP64", note="Q31 选关注的人 232 人")
multi(B5, "Q33", "IDP65", note="全卷")
multi(B5, "Q34", "IDP66", note="全卷")
multi(B5, "Q35", "IDP67", note="全卷")
for h in [c for c in HEAD if c.startswith("SCREENER3__")]:
    b = len(valid(h))
    add(B5, "S3×is_mmorpg", "设备与两种口径", h, "%s（全卷）" % opt(h), b, len(yes(h)), "")
    add(B5, "S3×is_mmorpg", "设备与两种口径", h, "%s（is_mmorpg=1，%d 人）" % (opt(h), len(IS_MMO)),
        len(IS_MMO), len(yes(h) & IS_MMO), "对照维度，不做门槛")
    add(B5, "S3×is_mmorpg", "设备与两种口径", h, "%s（play_mmorpg=1，%d 人）" % (opt(h), len(PLAY)),
        len(PLAY), len(yes(h) & PLAY), "门槛口径")

say("")
say("—— 附：两个口径的差、RO 漏斗、Q9 文本 ——")
add(B6, "口径差", "两个口径", "is_mmorpg", "自我标签：S1 或 S2 勾了 MMORPG 品类", N,
    len(IS_MMO), "只作对照维度，不再做门槛")
add(B6, "口径差", "两个口径", "play_mmorpg", "行为：在 Q3 的 17 款里玩过至少一款", N,
    len(PLAY), "Q3 至 Q8 与 Q18 至 Q27 的分母")
add(B6, "口径差", "两个口径", "play−is", "自认品类却一款都没玩过（is=1 且 play=0）", N,
    len(IS_MMO - PLAY), "清单对日本 MMORPG 大盘的覆盖度之一：这些人不在任何一款的射程内")
add(B6, "口径差", "两个口径", "is−play", "玩过却没把 MMORPG 算作自己玩的品类（play=1 且 is=0）", N,
    len(PLAY - IS_MMO), "每一个都勾了 S1 的 RPG；他们答过 Q18 至 Q27 的门槛题")
ESC2 = yes("IDP30__19")
ESC3 = yes("IDP50__18")
add(B6, "口径差", "两个口径", "play−is 的构成",
    "选了 Q3「一款都没玩过」的 %d 人" % len((IS_MMO - PLAY) & ESC3), N,
    len((IS_MMO - PLAY) & ESC3), "另外 %d 人走的是 Q2 的「以上都没听过」"
    % len((IS_MMO - PLAY) & ESC2))
# RO 漏斗
q2_ro = {k for k in range(N) if any(COL["IDP30__%d" % g][k] == "1" for g in RO_G)}
q3_ro = {k for k in range(N) if any(COL["IDP50__%d" % g][k] == "1" for g in RO_G)}
q4_ro = {k for k in range(N) if any(COL["IDP51__%d" % g][k] == "1" for g in RO_G)}
LAPSED = q3_ro - q4_ro
LAPSED_Q9 = LAPSED & valid("IDP37")
add(B6, "RO 漏斗", "RO 四款", "Q2", "听说过至少一款 RO（オンライン／マスターズ／X／オリジン）",
    N, len(q2_ro), "另有 %d 人勾了「その他 RO 系列」" % len(yes(RO_OTHER)))
add(B6, "RO 漏斗", "RO 四款", "Q3", "玩过至少一款 RO", len(valid("IDP50__1")), len(q3_ro),
    "Q3 分母是 Q2 未走逃亡口的 510 人")
add(B6, "RO 漏斗", "RO 四款", "Q4", "现在还有一款 RO 在玩", len(valid("IDP51__1")), len(q4_ro),
    "Q4 分母是 play_mmorpg=1 的 293 人")
add(B6, "RO 漏斗", "RO 四款", "流失", "玩过 RO、Q4 里一款 RO 都没勾（已不再玩 RO）", len(q3_ro),
    len(LAPSED), "需求方问题二的近似人群；其中 %d 人走支线、在 Q9 留了文本" % len(LAPSED_Q9))

# =============================================================== 3 Q9 文本
Q9_IDX = P["IDP37"]
Q9_ROWS = []
for k in range(N):
    t = BODY[k][Q9_IDX]
    if t in NA:
        continue
    Q9_ROWS.append([BODY[k][P["ID"]], t, BODY[k][P["play_mmorpg"]], BODY[k][P["is_mmorpg"]],
                    "1" if k in LAPSED else "0", "1" if k in LAPSED_Q9 else "0"])
say("")
say("Q9 自由文本：有文本的 %d 条，其中 %d 条是「玩过 RO、已不再玩 RO」的人写的，"
    % (len(Q9_ROWS), len(LAPSED_Q9)))
say("这 %d 条正好对上需求方问题二的口径。文本没做自动归类——同义的写法很多，"
    "硬匹配会把「ドラクエ10」「DQ10」分成两类；先落成 Q9文本.csv，人工过一遍再统计。"
    % len(LAPSED_Q9))
top = collections.Counter(r[1] for r in Q9_ROWS).most_common(8)
say("原文里出现最多的几种写法（原样，未归类）：")
for t, c in top:
    say("  %2d 次  %s" % (c, t[:50]))

# =============================================================== 4 自检结果
section("三、自检")
say("分母锚点 %d 处、三个派生标记、Q22 的 17 个行标记、剔除名单、空白与列数都过了一遍。"
    % len(BASE_ANCHOR))
say("Q22 逐款 N：%s" % "、".join("%s %d" % (GAMES[g - 1][:8], len(Q22_ROWS[g]))
                                 for g in range(1, 18)))
say("逐款 N≥%d 的款数 %d／17；跨款配对 N≥%d 的 %d 对，N≥%d 的 %d 对。"
    % (SMALL_N, sum(1 for g in range(1, 18) if len(Q22_ROWS[g]) >= SMALL_N),
       PAIR_N, len(PAIRS), PAIR_MD, sum(1 for n, _, _ in PAIRS if n >= PAIR_MD)))
say("读数一共 %d 行，落在 %d 个议题下。" % (len(R), len({x["block"] for x in R})))
if FAIL:
    say("")
    say("自检未通过 %d 项：" % len(FAIL))
    for f in FAIL:
        say("  ✗ %s" % f)

# =============================================================== 5 出表
CSV_HEAD = ["议题", "题号", "组", "变量", "选项或取值", "基数N", "计数", "占比%", "ME(pp)", "备注"]


def csv_rows():
    out = [CSV_HEAD]
    for x in R:
        out.append([x["block"], x["q"], x["title"], x["var"], x["label"], str(x["base"]),
                    str(x["cnt"]), r1(x["pct"]), r1(x["me"]), x["note"]])
    return out


def md_lines():
    L = ["# 分析读数：五组议题的分布表（092601_analysis 产出）",
         "",
         "这份文件由 `092601_analysis.py` 从 `RPG.csv` 算出，给报告提供可引用的分布与精度，",
         "本身不是报告，也没有结论。每个比例后面的 ME 是 95% 置信区间的半宽（百分点），",
         "按正态近似算，只覆盖随机抽样误差。选项标签用问卷原文（日文），码与 `值码表.md` 一致。",
         "",
         "分母一律取各题清洗后的有效 N。Q8／Q12／Q29／Q37 报的是扣掉「不愿回答」之后的数。",
         "原因类题（Q15、Q16、Q19、Q20、Q26）只给清单内部的相对排序，产出不了因果。",
         "",
         "97／98／99 那几行只报人数，不进基数。配对表里的计数与占比是两款的差值（前者减后者），",
         "不是占比本身；差值与它的 ME、McNemar 精确检验的 p 值写在备注里。",
         ""]
    seen_block = None
    seen_title = None
    nrow = 0
    for x in R:
        if not x["md"]:
            continue
        if x["block"] != seen_block:
            seen_block = x["block"]
            seen_title = None
            L += ["", "## %s" % seen_block, ""]
        if x["title"] != seen_title:
            seen_title = x["title"]
            L += ["", "### %s" % seen_title, "",
                  "| 选项或取值 | 变量 | 计数 | 基数 N | 占比 | ME | 备注 |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        pc = r1(x["pct"])
        mc = r1(x["me"])
        L.append("| %s | `%s` | %d | %d | %s | %s | %s |"
                 % (x["label"].replace("|", "/"), x["var"], x["cnt"], x["base"],
                    pc if pc == "—" else pc + "%",
                    mc if mc == "—" else "±" + mc + "pp", x["note"]))
        nrow += 1
    L += ["", "---", "",
          "Q22 的八条说法（C1 至 C8 的对照）：", ""]
    for s, t in enumerate(CLAIMS, start=1):
        L.append("%d. C%d —— %s" % (s, s, t))
    L += ["",
          "Q22 的一行只由给这款游戏打过勾的人构成，逐款 N 从 %d 到 %d；N≥%d 的并排只够读方向，"
          % (min(len(Q22_ROWS[g]) for g in range(1, 18)),
             max(len(Q22_ROWS[g]) for g in range(1, 18)), SMALL_N),
          "读不出差距大小。跨款比较走配对：同一个人在同一个矩阵里给两款都打过勾，差值与其 ME、",
          "以及 McNemar 精确检验的 p 值一并列在上面（markdown 只列配对 N≥%d 的，"% PAIR_MD,
          "N≥%d 的全部 %d 对在 分析表.csv 里）。" % (PAIR_N, len(PAIRS)), "",
          "Q9 的 %d 条自由文本没有自动归类，原文与标记在 `Q9文本.csv`，归类后再回来补一张小表。"
          % len(Q9_ROWS)]
    return L, nrow


section("四、产出")
A_MD, md_n = md_lines()
A_CSV = csv_rows()
A_Q9 = [["ID", "Q9原文", "play_mmorpg", "is_mmorpg", "玩过RO已不玩RO", "其中走支线"]] + Q9_ROWS
say("读数 %d 行；分析表.csv %d 行；分析结果.md 折成 %d 张表；Q9文本.csv %d 行。"
    % (len(R), len(A_CSV), md_n, len(A_Q9)))


def read_csv(path):
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        return [list(r) for r in csv.reader(fh)]


check_lines = []
if CHECK_ONLY:
    for path, new, kind in ((RES_OUT, A_CSV, "csv"), (MD_OUT, A_MD, "md"),
                            (LOG_OUT, "\n".join(LOG).splitlines(), "md"),
                            (Q9_OUT, A_Q9, "csv")):
        name = os.path.basename(path)
        if not os.path.exists(path):
            check_lines.append("--check：%s 不存在，跳过。" % name)
            continue
        old = read_csv(path) if kind == "csv" \
            else io.open(path, encoding="utf-8-sig").read().splitlines()
        if old == new:
            check_lines.append("--check：%s 完全一致" % name)
            continue
        m = min(len(old), len(new))
        at = next((k for k in range(m) if old[k] != new[k]), m)
        check_lines.append("--check：%s 不一致（行数 %d／%d，第一处在第 %d 行）"
                           % (name, len(old), len(new), at + 1))

if FAIL:
    print("analysis FAILED：%d 项自检未通过" % len(FAIL))
    for f in FAIL:
        print("  ✗ %s" % f)
    sys.exit(1)
if CHECK_ONLY:
    print("\n".join(check_lines))
    sys.exit(0)

os.makedirs(OUTDIR, exist_ok=True)
with io.open(RES_OUT, "w", encoding="utf-8-sig", newline="") as fh:
    csv.writer(fh).writerows(A_CSV)
with io.open(MD_OUT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(A_MD) + "\n")
with io.open(Q9_OUT, "w", encoding="utf-8-sig", newline="") as fh:
    csv.writer(fh).writerows(A_Q9)
with io.open(LOG_OUT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(LOG))
print("analysis OK: %d rows x %d cols; 读数 %d 行；Q9 文本 %d 条"
      % (N, len(HEAD), len(R), len(Q9_ROWS)))
