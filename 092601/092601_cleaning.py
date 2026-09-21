# -*- coding: utf-8 -*-
"""日本 MMORPG 玩家定量调研 —— 投后数据集清洗（脚本 092601）

把一份平台导出的原始数据收成一个开箱即用的分析文件。三件事顺序做完：

  第一段  按问卷流向逐题切分。先算「谁该答这道题」，再决定这处保留、作废还是写缺失码。
          方向只有一个：用前面的答案决定后面那道题作不作数，不拿后题反推前题。
  第二段  加受访者键、补掉所有空白、删掉不该随数据发布的列。
  第三段  文本型分类变量编成数字，缺失码按 UKDS 的口径按原因拆开。

输入  data/Original.csv    600 行 × 438 列，前两行都是表头（第一行变量名，第二行题目与选项正文）
输出  data/RPG.csv         579 行 × 427 列（剔除 21 人后；见下「剔除」一段）
      data/值码表.md        数据集里每一列的值码，markdown（见第五段末尾的构造器）
      data/各题分母.csv     逐题清洗后的有效 N、MMORPG 人数、三种缺失码的处数
      data/清洗日志.txt     每一步动了什么、动了多少处

用法  python 092601_cleaning.py                    默认读 data/Original.csv，写 data/
      python 092601_cleaning.py 原始.csv 输出.csv   换路径
      python 092601_cleaning.py --check            只重算并与现有输出逐项比对，不写盘

逐题口径与理由写在下面的注释里——本仓库的 README 只讲仓库怎么用，不涉及具体数据的口径。
随数据走的清洗说明与码本放在项目目录里，不进本仓库。

2026-09-20 两处口径落定：Q18 至 Q27 的门槛收到清洗阶段，非 MMORPG 玩家的作答置 97；
Q9 那 2 名异常人在开放填空上的作废作答由 99 改记 97。

2026-09-21 用户裁定三处：① Q18 至 Q27 的门槛由「自认 MMORPG 品类」（is_mmorpg）改成
「在这 17 款里玩过至少一款」（play_mmorpg），前一条的置 97 范围随之重算；② Q2 与 Q3 的勾选
完全不相交的 21 人整人剔除；③ 派生标记：elig_q4 改名 play_mmorpg，新增 not_mmo_mostplay
与 nested_ok。三个派生标记的定义见第三段。剔除之后 ID 保留原始导出行号，不再连续。

2026-09-21 后补：删掉 branch（1＝在玩组／2＝不在玩组）。它与 not_mmo_mostplay 逐行相同，两列里留一个
名字更好用的；列数因此从 428 变成 427。在玩组与不在玩组各有多少人，仍可从 Q5 与 Q9 的有效 N 读出。
"""
import csv
import io
import os
import sys
import collections

# =============================================================== 0 缺失码与路径
# UKDS 把「不适用」按原因分开：not applicable / not provided / not recorded。
# 本项目据此把缺失拆成三个码，95（error）与 96（not known）本卷不用。
NA_SKIP = "97"      # 跳转未出示，以及清洗时事后作废的作答
NA_REFUSE = "98"    # 明确表示不愿回答／不便回答
NA_NOREC = "99"     # 无可用记录：整题无数据、开放题没写、性别落不进二值
NA_ALL = (NA_SKIP, NA_REFUSE, NA_NOREC)

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK_ONLY = "--check" in sys.argv
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
SRC = ARGS[0] if ARGS else os.path.join(HERE, "data", "Original.csv")
DST = ARGS[1] if len(ARGS) > 1 else os.path.join(HERE, "data", "RPG.csv")
OUTDIR = os.path.dirname(os.path.abspath(DST))
CODES_OUT = os.path.join(OUTDIR, "值码表.md")
DEN_OUT = os.path.join(OUTDIR, "各题分母.csv")
LOG_OUT = os.path.join(OUTDIR, "清洗日志.txt")


# 问卷变量区：只有这一区里的缺失才用 97／98／99。ID 与 iirepSerial 里的 97／98／99
# 是真实取值（ID=97 的那一行、序列号里带 98 的受访者），动不得。
def is_survey(h):
    return h.startswith("SCREENER") or h.startswith("IDP")


# =============================================================== 1 读入
if not os.path.exists(SRC):
    print("找不到输入文件：%s" % SRC)
    print("把平台导出的原始数据放到 data/Original.csv，或者用两个参数指定路径：")
    print("  python %s <原始数据.csv> <输出数据.csv>" % os.path.basename(__file__))
    sys.exit(2)

with io.open(SRC, encoding="utf-8-sig", newline="") as fh:
    rd = csv.reader(fh)
    NAMES = next(rd)              # 第一行：变量名
    TEXTS_ROW = next(rd)          # 第二行：题目与选项正文，不是数据；留着做值码表的标签
    RAW = [list(r) for r in rd]   # 第三行起才是受访者
SRC_ROWS = len(RAW)
RAW_IDX = {h: i for i, h in enumerate(NAMES)}
TEXTS = dict(zip(NAMES, TEXTS_ROW))

# --------------------------------------------------------------- 剔除
# Q3 设计上只出示 Q2 勾过的游戏，实投没有落位：有 83 人在 Q3 勾了 Q2 里说没听过的款。
# 其中两题勾选毫无交集的一批（Q3 有勾选，但与 Q2 一项都不重合），作答质量不可用，整人剔除。
# 判定只看这两个条件，用原始作答。剔除后 ID 保留原始导出行号、不做重排，
# 序列里的缺口就是被剔除的人——任何一个 ID 都能直接对回原始导出的行。


def _yes(k, h):
    return RAW[k][RAW_IDX[h]] == "Yes"


Q2_SEEN = {k: {g for g in range(1, 18) if _yes(k, "IDP30__%d" % g)} for k in range(SRC_ROWS)}
Q3_PLAYED = {k: {g for g in range(1, 18) if _yes(k, "IDP50__%d" % g)} for k in range(SRC_ROWS)}
DROPPED = sorted(k for k in range(SRC_ROWS)
                 if Q3_PLAYED[k] and not (Q2_SEEN[k] & Q3_PLAYED[k]))
DROPPED_IDS = [k + 1 for k in DROPPED]
KEEP_IDX = [k for k in range(SRC_ROWS) if k not in set(DROPPED)]
RAW = [RAW[k] for k in KEEP_IDX]
ORIG_ID = [k + 1 for k in KEEP_IDX]
N = len(RAW)
# nested_ok：Q3 的勾选是否完全落在 Q2 之内（Q4 落在 Q3 之内由自检保证，实测 0 例外）。
NESTED_OK = {j for j, k in enumerate(KEEP_IDX) if Q3_PLAYED[k] <= Q2_SEEN[k]}

# 工作副本。第四段删完列之后，CUR_ROWS／CUR_IDX 指向收窄后的表，后面的自检都读它。
WORK = [list(r) + [""] * (len(NAMES) - len(r)) for r in RAW]
CUR_ROWS = WORK
CUR_IDX = RAW_IDX

LOG = []


def say(s=""):
    LOG.append(s)


def section(title):
    say("")
    say("=" * 72)
    say(title)
    say("=" * 72)


def GV(h, k):
    """某人在某列上的现值。"""
    return CUR_ROWS[k][CUR_IDX[h]]


def PUT(h, k, v):
    CUR_ROWS[k][CUR_IDX[h]] = v


def y_raw(h):
    """从原始数据里取勾了 Yes 的人。所有判定都基于原始作答，不看中间状态。"""
    i = RAW_IDX[h]
    return {k for k, row in enumerate(RAW) if row[i] == "Yes"}


def filled_raw(h):
    """从原始数据里取非空的人。"""
    i = RAW_IDX[h]
    return {k for k, row in enumerate(RAW) if row[i] != ""}


def valid(h):
    """清洗后某列的有效人数（不含 97／98／99，也不含空）。"""
    return {k for k in range(N) if GV(h, k) not in NA_ALL and GV(h, k) != ""}


def n_of(h, code):
    return sum(1 for k in range(N) if GV(h, k) == code)


def pick(prefix):
    """取某个变量名下面的全部列：主列、__n 选项列、_IDPAxxx 开放伴随列，按原表列序。"""
    cols = [h for h in NAMES
            if h == prefix or h.startswith(prefix + "__") or h.startswith(prefix + "_IDPA")]
    extra = {"SCREENER1": "SCREENER1_12", "SCREENER2": "SCREENER2_10",
             "SCREENER3": "SCREENER3_5"}.get(prefix)
    if extra and extra in RAW_IDX:
        cols.append(extra)
    order = {h: i for i, h in enumerate(NAMES)}
    return sorted(set(cols), key=lambda h: order[h])


# 开放题与整题无数据的列：空白写 99（无文本），不写 97。
# 开放题的 99 是「出示了但没写」，与「跳转没出示」不是一回事。
OPEN_TEXT = ["SCREENER1_12", "SCREENER2_10", "SCREENER3_5", "IDP37",
             "IDP43_IDPA390", "IDP44_IDPA399", "IDP46_IDPA422", "IDP47_IDPA432",
             "IDP48_IDPA605", "IDP49_IDPA441", "IDP57_IDPA492", "IDP58_IDPA506",
             "IDP59_IDPA513", "IDP62_IDPA543", "IDP64_IDPA552", "IDP65_IDPA560",
             "IDP67_IDPA575"]
COL_NOTEXT = set(OPEN_TEXT) | {"IDP45_IDPA413", "IDP60_IDPA522", "IDP45", "IDP60"}

# 2026-09-20 修正：Q9 至 Q12 那 2 名异常人在 Q9 开放填空（IDP37）上的作答被作废，
# 记 97「作废的作答」。旧版先用 99 做单一占位码、事后拆码时把开放列整列保留成 99，
# 漏掉了这两处，现在按口径直写 97。

# 待删的 16 列：整列常数、重复变量、平台不该有的选项列。
DROP = (["BlocksOrder", "iirepEveryone", "resp_gender", "language",
         "respondent_gender_recoded", "age_group",
         "IDP51__18", "IDP53__18"]
        + ["IDP54/L486__%d" % s for s in range(1, 9)])

# Q22 矩阵：18 个行标记配 18 个评分块，每块 8 条说法。第 18 行是平台自己加的，稍后整块删掉。
Q22_FLAG = ["IDP53__%d" % g for g in range(1, 19)]
Q22_RATE = ["IDP54/L%d__%d" % (468 + g, s) for g in range(1, 19) for s in range(1, 9)]
Q22_ROW18 = ["IDP53__18"] + ["IDP54/L486__%d" % s for s in range(1, 9)]


def fill_blanks(cols):
    """这一组列里的空白一律写缺失码：开放题与整题无数据的列写 99，其余写 97。"""
    n = collections.Counter()
    for h in cols:
        code = NA_NOREC if h in COL_NOTEXT else NA_SKIP
        for k in range(N):
            if GV(h, k) == "":
                PUT(h, k, code)
                n[code] += 1
    return n


def void(cols, people):
    """作废：这批人在这些列上的作答抹掉，写成 97。
    返回「原有作答被抹掉的处数」与「本来就是空的处数」，好让日志说实话。"""
    had = blank = 0
    for h in cols:
        for k in people:
            v = GV(h, k)
            if v == NA_SKIP:
                continue
            if v == "":
                blank += 1
            else:
                had += 1
            PUT(h, k, NA_SKIP)
    return had, blank


# =============================================================== 2 事前事实
section("一、清洗前算好的原始事实")
S1_RPG = y_raw("SCREENER1__1")
S1_MMO = y_raw("SCREENER1__2")
S2_MMO = y_raw("SCREENER2__1")
IS_MMO = S1_MMO | S2_MMO                      # 并集：S1 或 S2 任一处勾了 MMORPG 都算
# play_mmorpg：Q3 实际勾了至少一款的人。它与 is_mmorpg 是两条轴，互不包含——
# 有人玩过 FF14 却不把「MMORPG」这个品类算在自己头上，也有人自认 MMORPG 却一款都没玩过。
PLAY_MMO = {k for k in range(N)
            if any(RAW[k][RAW_IDX["IDP50__%d" % g]] == "Yes" for g in range(1, 18))}
Q2_ESC = y_raw("IDP30__19")                   # Q2 选「以上都没听过」
Q3_ESC = y_raw("IDP50__18")                   # Q3 选「一款都没玩过」
Q4_GAME = ["IDP51__%d" % j for j in range(1, 18)]
BRANCH_DUP = filled_raw("IDP52") & filled_raw("IDP37")   # 在玩组与不在玩组都答了的异常人

say("原始表 %d 行 × %d 列，剔除 %d 人后 %d 人 × %d 列。" % (SRC_ROWS, len(NAMES),
                                                          len(DROPPED), N, len(NAMES)))
say("剔除的是 Q2 与 Q3 勾选毫无交集的人（设计上 Q3 只出示 Q2 勾过的游戏，两种答案对不上）。")
say("剔除的原始行号：%s。ID 保留原始行号、不重排，序列里的缺口就是他们。"
    % "、".join(str(i) for i in DROPPED_IDS))
say("文件里只有完成的访谈，被终止的人不在其中，所以留下来的 %d 人本身就是" % N)
say("「S1 勾了 RPG 或 MMORPG」的合处样本，样本口径不需要再裁切。")
say("S1 勾 RPG = %d；S1 勾 MMORPG = %d；S2 补进 MMORPG = %d；并集 is_mmorpg=1 共 %d 人。"
    % (len(S1_RPG), len(S1_MMO), len(S2_MMO), len(IS_MMO)))
say("play_mmorpg=1（在这个 17 款清单里玩过至少一款）= %d 人。" % len(PLAY_MMO))
say("  两者差 %d 人：is_mmorpg=1 而 play_mmorpg=0 的 %d 人（自认品类却一款没玩过），"
    % (len(IS_MMO ^ PLAY_MMO), len(IS_MMO - PLAY_MMO)))
say("  play_mmorpg=1 而 is_mmorpg=0 的 %d 人（玩过却没有把 MMORPG 算作自己玩的品类）。"
    % len(PLAY_MMO - IS_MMO))
say("Q2 逃亡口 = %d 人；Q3 逃亡口 = %d 人。" % (len(Q2_ESC), len(Q3_ESC)))
say("在玩组与不在玩组都答了的异常人 = %d 人（原始行 %s）。"
    % (len(BRANCH_DUP), "、".join(str(ORIG_ID[k]) for k in sorted(BRANCH_DUP))))
say("nested_ok=1（Q3 的勾选完全落在 Q2 之内）的 %d 人；余下 %d 人有一到两处越界，"
    % (len(NESTED_OK), N - len(NESTED_OK)))
say("这批人不剔除，只在 nested_ok 上标出来，分析时可以按需过滤。")

# =============================================================== 3 逐题切分
# 顺序与问卷流向一致：S1 → S2 → S3 → Q2 → Q3 → Q4 → 两支 → Q13…Q37。
section("二、按问卷流向逐题切分（补缺失码与作废作答）")
say("")
say("S1 游戏类型：全卷作答，无空值。勾 RPG 或 MMORPG 者进入正式样本，无子样本可裁。")

c = fill_blanks(pick("SCREENER2"))
say("")
say("S2 RPG 细分：只对 S1 勾了 RPG 的 %d 人出示，另 %d 人在本题写 97（%d 处）。"
    % (len(S1_RPG), N - len(S1_RPG), sum(c.values())))

say("")
say("S3 设备：全卷作答，无空值。")

say("")
say("Q2 听说过哪些 MMORPG：全卷作答，无空值。选「以上都没听过」的 %d 人跳过 Q3。" % len(Q2_ESC))

c = fill_blanks(pick("IDP50"))
say("")
say("Q3 玩过哪些 MMORPG：Q2 逃亡口的 %d 人写 97（%d 处）。" % (len(Q2_ESC), sum(c.values())))
say("IDP50__18（一款都没玩过）= %d 人，是有效作答，保留。" % len(Q3_ESC))
say("★ 平台侧失误：这 %d 人本应直接跳到 Q9，实投被继续问了 Q4，也被带进了 Q22。" % len(Q3_ESC))

Q4_COLS = pick("IDP51")
c = fill_blanks(Q4_COLS)
n4_had, n4_blank = void(Q4_COLS, Q3_ESC)
say("")
say("Q4 还在玩的有哪些：第一层，Q2 逃亡口的 %d 人写 97（%d 处）；" % (len(Q2_ESC), sum(c.values())))
say("第二层，Q3 逃亡口的 %d 人在本题的作答全部作废，原有作答 %d 处，另有 %d 处本来就是空的。"
    % (len(Q3_ESC), n4_had, n4_blank))
say("作废的理由：本题的选项集由 Q3 的勾选生成，Q3 说「一款都没玩过」的人没有任何可出示的")
say("游戏，本题对他们不成立。处理方式是作废作答而不是剔除样本——这 %d 人在 Q3 与 Q9 及之后" % len(Q3_ESC))
say("的题目上都有有效作答，删人会连带毁掉不在玩组与后段各题的分母。")
say("清洗后本题有效 = %d 人。IDP51__18 是平台串过来的 Q3 文本，已整项作废，第四段删列。"
    % len(valid("IDP51__1")))
Q4_PICK = {k for k in range(N) if any(GV(h, k) in ("Yes", "1") for h in Q4_GAME)}
say("本题勾到至少一款游戏、继续走 Q5 至 Q8 的有 %d 人。" % len(Q4_PICK))

c = fill_blanks(pick("IDP52") + pick("IDP34") + pick("IDP35") + pick("IDP36"))
say("")
say("Q5 至 Q8 自报主玩的那一款（是哪一款、玩多久、每天多久、月消费）：")
say("Q4 没勾到游戏的 %d 人写 97（%d 处）。这一段跳转本来就对，清洗只补空白。"
    % (N - len(Q4_PICK), sum(c.values())))

Q9_COLS = pick("IDP37") + pick("IDP38") + pick("IDP39") + pick("IDP40")
c = fill_blanks(Q9_COLS)
n9_had, n9_blank = void(Q9_COLS, BRANCH_DUP)
say("")
say("Q9 至 Q12 这条平行分支（最常玩的那一款，自由填写）：空白写缺失码（%d 处）；" % sum(c.values()))
say("那 %d 名异常人在 Q9 至 Q12 的作答作废，原有作答 %d 处（另有 %d 处本来就是空的），"
    % (len(BRANCH_DUP), n9_had, n9_blank))
say("按问卷流向他们只该走 Q5 至 Q8；Q9 的开放填空（IDP37）那两处也一并记 97。")
say("两组恰好覆盖 %d 人：在玩组 %d ＋ 不在玩组 %d。" % (N, len(valid("IDP52")), len(valid("IDP37"))))

c = fill_blanks(pick("IDP41") + pick("IDP42") + pick("IDP43") + pick("IDP44"))
say("")
say("Q13 至 Q16 RO 认知与新作意愿：全卷适用，空白写缺失码（%d 处）。" % sum(c.values()))
say("Q15 与 Q16 互斥：Q14 选不想体验的 %d 人答 Q15，选想体验的 %d 人答 Q16，"
    % (len(valid("IDP43__1")), len(valid("IDP44__1"))))
say("选「一般」的 %d 人两题都不答。"
    % (len(valid("IDP42")) - len(valid("IDP43__1")) - len(valid("IDP44__1"))))

say("")
say("Q17 看重因素：★ 投放时本题没有出出来，数据集里连选项列都没有，两列全空，写 99。")
say("这里的 99 是「整题无数据」，与跳转不适用不是一回事，报告里要单独说明。")
say("（这四列由第二段末尾的兜底扫描补上，那里会把处数一并报出来。）")

for p in ("IDP46", "IDP47", "IDP48"):
    fill_blanks(pick(p))
say("")
say("Q18 至 Q20 卖点、痛点、流失原因：空白写缺失码。这几题的门槛在第二段末尾统一处理。")
say("Q20 另有分流：选「还没引退过」的 %d 人不答 Q21。" % (N - len(valid("IDP49__1"))))

c = fill_blanks(pick("IDP49"))
say("")
say("Q21 回流吸引点：Q20 选「一直在玩」的 %d 人写 97（%d 处）。"
    % (N - len(valid("IDP49__1")), sum(c.values())))

n1_had, n1_blank = void(Q22_FLAG + Q22_RATE, Q3_ESC)
n2_had, n2_blank = void(Q22_ROW18, set(range(N)))
c = fill_blanks(Q22_FLAG + Q22_RATE)
say("")
say("Q22 重点游戏形象的评分矩阵（%d 个行标记 ＋ %d 个评分项）：" % (len(Q22_FLAG), len(Q22_RATE)))
say("第一层，Q3 逃亡口的 %d 人在本题的作答全部作废，原有作答 %d 处；"
    % (len(Q3_ESC), n1_had))
say("他们没有可出示的游戏行，本题对他们不成立。")
say("第二层，平台自己加的第 18 行「一款都没玩过」整行作废，原有作答 %d 处，问卷里没有这一行。"
    % n2_had)
say("第三层，其余空白写缺失码（%d 处）。空白来自 Q2 逃亡口的 %d 人，" % (sum(c.values()), len(Q2_ESC)))
say("以及各人没勾过的游戏行——评分列按人按行铺开，某人在某行没被出示就没有值。")
say("本段清洗后本题有效 = %d 人，保留 17 款游戏；MMORPG 门槛落位后见第二段末尾。"
    % len(valid("IDP53__1")))
say("★ 报告要注明：有 %d 名受访者在这 17 款游戏中一款都没有玩过。" % len(Q3_ESC))
say("这个事实由 Q3 的 IDP50__18 承载，不依赖被作废的那一行。")

SOLO = {k for k in range(N) if GV("IDP55", k).startswith("ソロ")}
say("")
say("Q23 社交形态：全卷适用。选「独狼」的 %d 人跳过 Q24 与 Q25。" % len(SOLO))
c = fill_blanks(pick("IDP56") + pick("IDP57"))
say("Q24 与 Q25：这 %d 人写 97（%d 处）。这两题的门槛落在 Q23 的「独狼」上。"
    % (len(SOLO), sum(c.values())))
for p in ("IDP58", "IDP59"):
    fill_blanks(pick(p))
say("Q26 付费动机、Q27 付费形式：空白写缺失码。")

say("")
say("Q28 游戏外社群：★ 与 Q17 同因，投放时没有出题，两列全空，写 99。")
say("Q29 全游戏月消费：全卷适用，无空值。原 Q31 与原 Q34 已并成此题，累计金额不再采集。")

for p in ("IDP62", "IDP64", "IDP65", "IDP66", "IDP67"):
    fill_blanks(pick(p))
say("")
say("Q30 至 Q35 信息触达与背景信息：空白写缺失码。")
say("Q31 关注 → Q32：%d 人关注，%d 人不关注、不答 Q32。" % (len(valid("IDP64__1")), N - len(valid("IDP64__1"))))
say("Q36 职业、Q37 可支配金额：单选，无空值。")

# Q18 至 Q27 的门槛是 play_mmorpg：设计上这几题问的是「玩这个 17 款清单的人怎么看 MMORPG」，
# 实投时门槛没落位、全卷都被问了，不在门槛内的人的作答不是「他们答了」，是平台漏了门槛，置 97。
# 2026-09-21 之前这里用的是 is_mmorpg；换成 play_mmorpg 之后，52 名自认 MMORPG 却没玩过清单里
# 任何一款的作答被作废，67 名玩过却没自认 MMORPG 品类的作答被恢复。
# Q17 与 Q28 不在此列：那两题整题无数据，全体 99。
GATE_COLS = (pick("IDP46") + pick("IDP47") + pick("IDP48") + pick("IDP49")
             + Q22_FLAG + Q22_RATE + pick("IDP55") + pick("IDP56") + pick("IDP57")
             + pick("IDP58") + pick("IDP59"))
g_had, g_blank = void(GATE_COLS, set(range(N)) - PLAY_MMO)
say("")
say("Q18 至 Q27 的门槛：设计上只对「在这 17 款里玩过至少一款」的人出示，实投门槛没落位、")
say("全卷 %d 人都被问了。那 %d 名 play_mmorpg=0 的人的作答一律置 97，"
    % (N, N - len(PLAY_MMO)))
say("原有作答 %d 处（另有 %d 处本来就是空的）。"
    % (g_had, g_blank))
say("门槛内另有 %d 人是自认 MMORPG 品类却一款都没玩过的，他们的作答同样不在门槛内。"
    % len(IS_MMO - PLAY_MMO))
say("Q17 与 Q28 不在此列：那两题整题无数据，全体写 99。")
say("门槛收到清洗阶段之后，这一块的分母就是文件里的 N：")
say("  Q18 至 Q20、Q23、Q26、Q27 各 %d 人；" % len(valid("IDP46__1")))
say("  Q21 再叠加 Q20 未选「一直在玩」得 %d 人；Q22 就是门槛内的 %d 人；"
    % (len(valid("IDP49__1")), len(valid("IDP53__1"))))
say("  Q24 与 Q25 再叠加 Q23 非独狼得 %d 人。" % len(valid("IDP56__1")))
say("做全卷对照要另立一次导出：本文件里那一块的 %d 人口径已经没有了。" % N)

c = fill_blanks([h for h in NAMES if is_survey(h)])
say("")
say("兜底扫描：问卷变量区剩下的空白一并写缺失码（%d 处）。" % sum(c.values()))
say("面板元数据列（QUOTAGERANGE／GENDER_NonBinary／JPSTDREGION／resp_gender）的空值不动——")
say("它们的语义是「面板没给」或平台内部字段，与跳转不适用不是一回事。")

# =============================================================== 4 数字化与新增列
section("三、哑变量数字化、新增三个标记变量")
dummy = 0
for i, h in enumerate(NAMES):
    vals = {row[i] for row in WORK}
    if vals <= {"Yes", "No"} | set(NA_ALL) and (vals & {"Yes", "No"}):
        dummy += 1
        for k in range(N):
            if WORK[k][i] == "Yes":
                WORK[k][i] = "1"
            elif WORK[k][i] == "No":
                WORK[k][i] = "0"
say("多选哑变量 Yes→1、No→0：共 %d 列。缺失码不动，所以每一列都是三态。" % dummy)

for k in range(N):
    WORK[k].append("1" if k in IS_MMO else "0")
    WORK[k].append("1" if k in PLAY_MMO else "0")
    WORK[k].append("0" if k in Q4_PICK else "1")
    WORK[k].append("1" if k in NESTED_OK else "0")
NEW = ["is_mmorpg", "play_mmorpg", "not_mmo_mostplay", "nested_ok"]
say("")
say("新增四列，供分析直接引用，不占问卷题号：")
say("  is_mmorpg        1 = S1 或 S2 勾了 MMORPG 这个品类（%d 人）／0 = 都不是（%d 人）"
    % (len(IS_MMO), N - len(IS_MMO)))
say("                   这是「自我标签」口径，用于把两种口径的差写进报告，不再做门槛")
say("  play_mmorpg      1 = 在 Q3 的 17 款里玩过至少一款（%d 人）／0 = 一款都没玩过（%d 人）"
    % (len(PLAY_MMO), N - len(PLAY_MMO)))
say("                   这是「行为」口径；Q3 至 Q8 与 Q18 至 Q27 的分母都用它")
say("  not_mmo_mostplay 1 = 走 Q9 至 Q12、报的是自由填写的最常玩游戏（%d 人）／0 = 走 Q5 至 Q8（%d 人）"
    % (N - len(Q4_PICK), len(Q4_PICK)))
say("                   「没有一款还在玩的 MMORPG 可追问」的人，Q9 至 Q12 的分母")
say("                   在玩组与不在玩组原来是 branch 的两个码，2026-09-21 删掉 branch：它与这一列")
say("                   逐行相同，留一个名字更好用的。在玩组人数看 Q5 的有效 N，不在玩组看 Q9 的。")
say("  nested_ok        1 = Q3 的勾选完全落在 Q2 之内（%d 人）／0 = 有一到两处越界（%d 人）"
    % (len(NESTED_OK), N - len(NESTED_OK)))
say("                   Q4 落在 Q3 之内实测 0 例外，所以这一列只反映 Q2 与 Q3 的差")

# =============================================================== 5 加 ID、删列
section("四、加受访者键、删掉不该随数据发布的列")
HEAD = NAMES + NEW
BODY = WORK

if "ID" in HEAD:
    say("已有 ID 列，跳过。")
else:
    HEAD = ["ID"] + HEAD
    BODY = [[str(ORIG_ID[i])] + r for i, r in enumerate(BODY)]
    say("最前面加 ID 列：取原始导出的行号，剔除 %d 人之后不连续，缺口即那 %d 人。"
        % (len(DROPPED), len(DROPPED)))
    say("不重排是有意的：任何一个 ID 都能直接对回原始导出的第几行，删了谁一眼看得见。")
    say("ID 用来 join 与按人聚类；平台序列号 iirepSerial 留着，用来向平台回溯。")

missing = [h for h in DROP if h not in HEAD]
keep = [i for i, h in enumerate(HEAD) if h not in set(DROP)]
HEAD = [HEAD[i] for i in keep]
BODY = [[r[i] for i in keep] for r in BODY]
say("")
say("删掉 %d 列，删后 %d 行 × %d 列。" % (len(DROP), len(BODY), len(HEAD)))
say("  整列同一个值，或与别的列重复：BlocksOrder、iirepEveryone、resp_gender、language、")
say("  respondent_gender_recoded（GENDER_NonBinary 的粗化派生）、age_group（与 QUOTAGERANGE 逐行相同）。")
say("  平台自己多加、问卷里没有的选项列：IDP51__18（Q3 的文本串进了 Q4）、IDP53__18 与 L486 的 8 列")
say("  （Q22 的第 18 行「一款都没玩过」）。这两处不是值本身错，是列或行本身不该存在。")
say("iirepSerial 现在落在第 %d 列（删列前在第 %d 列）。"
    % (HEAD.index("iirepSerial") + 1, NAMES.index("iirepSerial") + 1))

# 收窄后的表接管全局访问器，后面的自检都读这一份
CUR_ROWS = BODY
CUR_IDX = {h: j for j, h in enumerate(HEAD)}
P = CUR_IDX

# =============================================================== 6 编数字码
section("五、文本型分类变量编成数字")

GAMES_Q2 = ["ファイナルファンタジーXIV", "BLUE PROTOCOL", "黒い砂漠 MOBILE", "リネージュM",
            "リネージュ2M", "オーディン：ヴァルハラ・ライジング", "Ash Tale-風の大陸-",
            "ツリーオブセイヴァー：ネバーランド", "杖と剣の伝説", "AZUREA-空の唄-",
            "ディアブロ イモータル", "コード：ドラゴンブラッド", "二ノ国：Cross Worlds",
            "ラグナロクオンライン", "ラグナロク マスターズ", "ラグナロクX", "ラグナロクオリジン"]
DUR = ["3 个月以内", "3–6 个月", "6 个月–1 年", "1–3 年", "3–5 年", "5 年以上"]
DUR2 = ["3ヶ月未満", "3～6ヶ月", "6ヶ月～1年", "1年～3年", "3年～5年", "5年以上"]
HRS = ["30分未満", "30分～1時間", "1時間～2時間", "2時間～3時間", "3時間～5時間", "5時間以上"]
PAY = ["課金はしていない", "1000円以内", "1000～3000円", "3000～5000円", "5000～1万円",
       "1万～3万円", "3万～5万円", "5万円以上"]
JOB = ["学生", "一般社員", "管理職", "公務員", "フリーランス", "自営業・経営者",
       "専業主婦・主夫", "求職中・無職", "定年退職者", "その他（具体的にご記入ください）"]
INC37 = ["ほとんどない", "5000円未満", "5000～1万円", "1万～3万円", "3万～5万円",
         "5万～10万円", "10万円以上"]
REGION = ["Hokkaido", "Tohoku", "Kanto", "Chubu", "Kansai", "Chugoku", "Shikoku",
          "Kyushu / Okinawa"]
REFUSE = {"回答したくない": NA_REFUSE}      # 付费与金额几题印的是这个说法
GENDER_REFUSE = {"回答しない": NA_REFUSE}   # 性别那题印的是这个说法，两者不通假


def seq(lst):
    """按问卷选项顺序升序赋值：1 对应问卷里的选项 1。"""
    return {v: str(i) for i, v in enumerate(lst, start=1)}


# （变量，题号，测量层级，码映射，备注）。性别按分析侧的要求编成男性 0、女性 1，
# 其余两项进缺失族：问卷 S4 只印了三项，「その他」是平台另加的类目。
CODES = [
    ("QUOTAGERANGE", "S5", "ordinal", seq(["18-29", "30-49", "50-60"]),
     "面板配额变量，数据里只有三档；升序：1＝最年轻档"),
    ("GENDER_NonBinary", "S4", "nominal",
     dict({"男性": "0", "女性": "1", "その他": NA_NOREC}, **GENDER_REFUSE),
     "男 0／女 1；「回答しない」＝98；平台另加的「その他」＝99"),
    ("JPSTDREGION", "（面板）", "nominal", seq(REGION), "按日本标准地域顺序，北海道到九州"),
    ("IDP52", "Q5", "nominal", seq(GAMES_Q2), "码序＝Q2 的 17 款游戏顺序"),
    ("IDP34", "Q6", "ordinal", seq(DUR), "升序：1＝3 个月以内"),
    ("IDP35", "Q7", "ordinal", seq(HRS), "升序：1＝30 分未满"),
    ("IDP36", "Q8", "ordinal", dict(seq(PAY), **REFUSE), "升序；末项不便回答＝98"),
    ("IDP38", "Q10", "ordinal", seq(DUR2), "升序：1＝3 个月未满"),
    ("IDP39", "Q11", "ordinal", seq(HRS), "升序：1＝30 分未满"),
    ("IDP40", "Q12", "ordinal", dict(seq(PAY), **REFUSE), "升序；末项不便回答＝98"),
    ("IDP41", "Q13", "ordinal",
     seq(["このIPがとても好きで、ROシリーズ作品をプレイしたことがある",
          "ROシリーズ作品をプレイしたことはあるが、特に好きというわけではない",
          "IPの名前を聞いたことはあるが、ゲーム内容についてはよく知らない",
          "このIP自体を知らないし、ゲームについてもわからない"]),
     "降序：1＝最喜欢且玩过，4＝完全不了解"),
    ("IDP42", "Q14", "ordinal",
     seq(["全くプレイしたくない", "プレイしたくない", "どちらとも言えない",
          "ややプレイしてみたい", "ぜひプレイしてみたい"]),
     "升序：1＝完全不想，5＝非常想"),
    ("IDP55", "Q23", "nominal",
     seq(["アクティブ型：自分から積極的に声をかけてパーティーを組んだり、ギルドイベントに参加する",
          "パッシブ（聞き専）型：自分から積極的には動かないが、他人のチャットを眺めたり、パーティー参加時も基本的には無言でついていく",
          "ソロプレイ型：基本的には誰ともコミュニケーションせず、ひとりでプレイする",
          "状況による（ゲームの雰囲気、リアルタイムの余裕、友人がプレイしているか等によって変わる）"]),
     "码序＝问卷顺序：主动／被动／独狼／视情况而定"),
    ("IDP61", "Q29", "ordinal", dict(seq(PAY), **REFUSE), "升序；末项不便回答＝98"),
    ("IDP63", "Q31", "nominal", seq(["している", "していない"]), "1＝关注，2＝不关注"),
    ("IDP68", "Q36", "nominal", seq(JOB), "码序＝问卷顺序"),
    ("IDP69", "Q37", "ordinal", dict(seq(INC37), **REFUSE), "升序；末项不愿回答＝98"),
]

CODE_TABLE = {}        # 变量 → (题号, 测量层级, {码: 原取值})，值码表用
for var, qno, lvl, mp, note in CODES:
    j = P[var]
    seen = collections.Counter(r[j] for r in BODY)
    bad = sorted(v for v in seen if v not in mp and v not in NA_ALL)
    if bad:
        say("★ %s 有没进码表的取值：%s" % (var, bad))
        continue
    for r in BODY:
        r[j] = r[j] if r[j] in NA_ALL else mp[r[j]]
    unseen = sorted(k for k in mp if k not in seen)
    CODE_TABLE[var] = (qno, lvl, {v: k for k, v in mp.items()})
    say("%-17s 编 %2d 个码，覆盖 %d 处；从没被选的码：%s"
        % (var, len(set(mp.values())), sum(seen.values()), "、".join(unseen) if unseen else "无"))
say("")
say("表里原本是文本的分类变量共 %d 个，编完后除开放题外全列都是数字。" % len(CODES))

# ---------- 值码表 ----------
# 按问卷的题目排，读起来像附在问卷上的一张码表：开头把通用码讲清，正文一题一段，
# 单选与有序题的码逐题列全，多选的选项列一行一个变量。数据集里的每一列都要有落点。
COMMON = [
    ("1", "选中／确认", "多选题的每个选项列、二值标记"),
    ("0", "没选／否", "同上"),
    ("97", "不适用", "跳转未出示、门槛过滤，以及清洗时事后作废的作答"),
    ("98", "明确表示不愿回答／不便回答", "问卷里印了这个选项的题：付费与金额四题、性别一题"),
    ("99", "无可用记录", "整题无数据；开放题没有文本"),
    ("自由文本", "受访者手写的文字", "开放题列"),
]

QUESTION_ORDER = [
    ("甄别", ["S1", "S2", "S3", "S4", "S5", "REGION"]),
    ("一、MMORPG 认知与主玩游戏",
     ["Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8", "Q9", "Q10", "Q11", "Q12"]),
    ("二、RO 认知与新作意愿", ["Q13", "Q14", "Q15", "Q16"]),
    ("三、品类形象与卖点", ["Q17", "Q18", "Q19", "Q20", "Q21", "Q22"]),
    ("四、社交与付费", ["Q23", "Q24", "Q25", "Q26", "Q27", "Q28", "Q29"]),
    ("五、信息触达", ["Q30", "Q31", "Q32", "Q33"]),
    ("六、背景信息", ["Q34", "Q35", "Q36", "Q37"]),
]
Q_PREFIX = {
    "S1": "SCREENER1", "S2": "SCREENER2", "S3": "SCREENER3",
    "Q2": "IDP30", "Q3": "IDP50", "Q4": "IDP51", "Q5": "IDP52", "Q6": "IDP34",
    "Q7": "IDP35", "Q8": "IDP36", "Q9": "IDP37", "Q10": "IDP38", "Q11": "IDP39",
    "Q12": "IDP40", "Q13": "IDP41", "Q14": "IDP42", "Q15": "IDP43", "Q16": "IDP44",
    "Q17": "IDP45", "Q18": "IDP46", "Q19": "IDP47", "Q20": "IDP48", "Q21": "IDP49",
    "Q22": "IDP53", "Q23": "IDP55", "Q24": "IDP56", "Q25": "IDP57", "Q26": "IDP58",
    "Q27": "IDP59", "Q28": "IDP60", "Q29": "IDP61", "Q30": "IDP62", "Q31": "IDP63",
    "Q32": "IDP64", "Q33": "IDP65", "Q34": "IDP66", "Q35": "IDP67", "Q36": "IDP68",
    "Q37": "IDP69",
}
Q_FIXED = {"S4": ["GENDER_NonBinary"], "S5": ["QUOTAGERANGE"], "REGION": ["JPSTDREGION"]}
Q_STEM = {"Q22": "IDP53__1", "S4": "GENDER_NonBinary", "S5": "QUOTAGERANGE",
          "REGION": "JPSTDREGION"}
Q_TITLE = {"REGION": "（面板）地域"}
Q_GATE = {
    "S1": "全卷作答；RPG 与 MMORPG 都没勾的人会被终止，被终止的人不在本数据里",
    "S2": "只对 S1 勾了 RPG 的 %d 人出示，另 %d 人写 97"
          % (len(valid("SCREENER2__1")), N - len(valid("SCREENER2__1"))),
    "S3": "全卷作答",
    "S4": "面板配额变量，全卷都有",
    "S5": "面板配额变量，数据里只有三档",
    "REGION": "面板配额变量",
    "Q2": "全卷作答；选「以上都没听过」的 %d 人跳过 Q3" % len(Q2_ESC),
    "Q3": "Q2 走了逃亡口的 %d 人跳过" % len(Q2_ESC),
    "Q4": "Q3 勾过至少一款的 %d 人作答；Q3 逃亡口的 %d 人在这里的作答作废，记 97"
          % (len(valid("IDP51__1")), len(Q3_ESC)),
    "Q5": "Q4 勾到游戏的 %d 人作答" % len(valid("IDP52")),
    "Q6": "同 Q5",
    "Q7": "同 Q5",
    "Q8": "同 Q5",
    "Q9": "三个逃亡口之一；走 Q5 至 Q8 的 %d 人跳过" % len(valid("IDP52")),
    "Q10": "同 Q9",
    "Q11": "同 Q9",
    "Q12": "同 Q9",
    "Q13": "全卷作答",
    "Q14": "全卷作答",
    "Q15": "Q14 选「完全不想」「不太想」的 %d 人作答" % len(valid("IDP43__1")),
    "Q16": "Q14 选「比较想」「非常想」的 %d 人作答，与 Q15 互斥" % len(valid("IDP44__1")),
    "Q18": "门槛是 `play_mmorpg=1`；实投门槛没落位，清洗时把门槛外的人的作答置 97，清洗后 %d 人"
           % len(valid("IDP46__1")),
    "Q19": "门槛是 `play_mmorpg=1`；清洗后 %d 人" % len(valid("IDP46__1")),
    "Q20": "门槛是 `play_mmorpg=1`；清洗后 %d 人" % len(valid("IDP46__1")),
    "Q21": "门槛是 `play_mmorpg=1`，且 Q20 未选「一直在玩」；清洗后 %d 人" % len(valid("IDP49__1")),
    "Q22": "门槛是 `play_mmorpg=1`（在 Q3 的 17 款里玩过至少一款）；清洗后 %d 人"
           % len(valid("IDP53__1")),
    "Q23": "门槛是 `play_mmorpg=1`；清洗后 %d 人" % len(valid("IDP55")),
    "Q24": "门槛是 `play_mmorpg=1` 且 Q23 非独狼；清洗后 %d 人" % len(valid("IDP56__1")),
    "Q25": "同 Q24",
    "Q26": "门槛是 `play_mmorpg=1`；清洗后 %d 人" % len(valid("IDP58__1")),
    "Q27": "门槛是 `play_mmorpg=1`；清洗后 %d 人" % len(valid("IDP59__1")),
    "Q29": "全卷作答；%d 人「不愿回答」记 98" % n_of("IDP61", NA_REFUSE),
    "Q32": "Q31 选「关注」的 %d 人作答" % len(valid("IDP64__1")),
    "Q37": "全卷作答；%d 人「不愿回答」记 98" % n_of("IDP69", NA_REFUSE),
}
MISSING_MEAN = {
    NA_SKIP: "不适用：跳转未出示、门槛过滤，或清洗时事后作废的作答",
    NA_REFUSE: "明确表示不愿回答／不便回答",
    NA_NOREC: "无可用记录：整题无数据，或这一处没有文本",
}
WHOLE_MISSING = {"IDP45", "IDP45_IDPA413", "IDP60", "IDP60_IDPA522"}
OPEN_ALSO = set(COL_NOTEXT) | {"IDP56_IDPA480", "IDP66_IDPA567"}


def short(text, n=80):
    # 标签按 UKDS 的口径不超过 80 字符。
    t = " ".join(str(text).split())
    return t if len(t) <= n else t[:n - 1] + "…"


def label_stem(h):
    # 题干：原始表第二行里「题干 - 选项」的左半边。
    t = TEXTS.get(h, h)
    return short(t.split(" - ", 1)[0])


def label_opt(h):
    # 选项正文：右半边；没有分隔符就用整句。
    t = TEXTS.get(h, h)
    return short(t.split(" - ", 1)[1]) if " - " in t else short(t)


def q_cols(q):
    # 这一题的列，按数据集列序。
    if q in Q_FIXED:
        return [h for h in Q_FIXED[q] if h in P]
    if q == "Q22":
        return ([h for h in pick("IDP53") if h in P]
                + [h for h in HEAD if h.startswith("IDP54/")])
    return [h for h in pick(Q_PREFIX[q]) if h in P]


def question_block(q):
    # 一题一段：题号加题干，下面按题型摆码。
    cols = q_cols(q)
    if not cols:
        return [], set()
    head = ("（面板配额）地域 `JPSTDREGION`" if q == "REGION"
            else "%s %s" % (Q_TITLE.get(q, q), label_stem(Q_STEM.get(q, cols[0]))))
    L = ["### %s" % head, ""]
    rec = [h for h in cols if h in CODE_TABLE]
    whole = [h for h in cols if h in WHOLE_MISSING]
    opens = [h for h in cols if h in OPEN_ALSO]
    opts = [h for h in cols if h not in rec + whole + opens]

    if whole:                      # 整题无数据的题
        L.append("整题无数据：投放时这道题没有出出来，%s 全列 99，保留列作占位等重投回填。"
                 % "、".join("`%s`" % h for h in whole))
        L.append("")
        return L, set(cols)

    if rec:                        # 单选与面板配额变量
        h = rec[0]
        back = CODE_TABLE[h][2]
        form = "单选（面板配额）" if h in ("QUOTAGERANGE", "GENDER_NonBinary",
                                     "JPSTDREGION") else "单选"
        L.append("%s，%s。变量 `%s`。" % (form, Q_GATE.get(q, "全卷作答"), h))
        L.append("")
        for c in sorted(back, key=int):
            L.append("%s = %s" % (c, back[c] if c not in NA_ALL else MISSING_MEAN[c]))
        L.append("")
        return L, set(cols)

    if opens and not opts:         # 只有开放题的题（Q9）
        L.append("填空（开放题），%s。变量 %s，写的是自由文本，缺失用通用码。"
                 % (Q_GATE.get(q, "全卷作答"), "、".join("`%s`" % h for h in opens)))
        L.append("")
        return L, set(cols)

    if q == "Q22":                 # 矩阵：行标记 + 评分列
        flags = [h for h in cols if h.startswith("IDP53__")]
        rates = [h for h in cols if h.startswith("IDP54/")]
        L.append("矩阵，%s。%d 款游戏各一行，每行 %d 条说法，共 %d 个评分项。"
                 % (Q_GATE.get(q, ""), len(flags), len(rates) // max(len(flags), 1), len(rates)))
        L.append("")
        L.append("行标记（1＝Q3 勾过这款、要给它打分；0＝没勾，这一行不给他看）：")
        L.append("")
        for h in flags:
            L.append("- `%s` = %s" % (h, label_opt(h)))
        L.append("")
        L.append("八条说法，每款游戏各一列：")
        L.append("")
        for s in range(1, 9):
            t = TEXTS.get("IDP54/L469__%d" % s, "")
            L.append("%d. %s" % (s, short(t.split(" - ", 1)[1]) if " - " in t else ""))
        L.append("")
        L.append("评分列的列名是 `IDP54/L{468+行序}__{说法号}`，例如第 1 款游戏第 3 条说法是 "
                 "`IDP54/L469__3`，第 17 款游戏第 8 条是 `IDP54/L485__8`。取值用通用码："
                 "1＝选了这条说法、0＝没选、97＝不适用。")
        L.append("")
        return L, set(cols)

    # 其余是多选：一项一列，取值用通用码
    L.append("多选，共 %d 个选项列，%s。" % (len(opts), Q_GATE.get(q, "全卷作答")))
    L.append("")
    L.append("每一列取值用通用码：1＝选了下面这一项、0＝没选、97＝本题对他不适用。")
    L.append("")
    for h in opts:
        L.append("- `%s` = %s" % (h, label_opt(h)))
    for h in opens:
        L.append("- `%s` = %s（自由文本；没写记 99）" % (h, label_opt(h)))
    L.append("")
    return L, set(cols)


def build_code_table():
    # 出值码表：返回 (markdown 文本, 覆盖到的列名集合)。
    L = ["# 值码表",
         "",
         "由 `092601_cleaning.py` 生成，随 `RPG.csv` 一起走。数据改了要重跑脚本重出，别手工改这张表。",
         "下面按问卷的题目排，读起来就是一张附在问卷上的码表；数据集里的 %d 列在这个文件里都有落点。"
         % len(HEAD),
         "",
         "## 剔除记录（2026-09-21）",
         "",
         "Q3 在问卷上有两个条件：只出示 Q2 勾过的游戏。实投没有按 Q2 过滤，有 83 人在 Q3 勾了",
         "Q2 里说没听过的款。其中 **%d 人**两道题的勾选毫无交集（Q3 有勾选，但与 Q2 一项都不重合），"
         % len(DROPPED),
         "作答质量不可用，整人剔除，不在这份数据里。",
         "",
         "剔除的原始行号：%s" % "、".join(str(i) for i in DROPPED_IDS),
         "",
         "其余留有越界的人（%d 人）没有剔除，由 `nested_ok` 标出来：0 表示他的 Q3 勾选里有"
         % (N - len(NESTED_OK)),
         "Q2 说没听过的款，1 表示两层完全套得上。分析要更严的口径时按这一列过滤即可。",
         "",
         "**ID 不重排**：取值仍是原始导出的行号，上面那串号码就是序列里缺的那些，任何一个 ID",
         "都能直接对回原始导出的第几行。",
         "",
         "## 通用码",
         "",
         "| 码 | 含义 | 用在哪儿 |",
         "| --- | --- | --- |"]
    for c, mean, where in COMMON:
        L.append("| %s | %s | %s |" % (c, mean, where))
    L += ["",
          "一处例外：性别（S4）的 0 与 1 是两个取值本身（0＝男性、1＝女性），不是「没选／选中」。"
          "四个派生标记（`is_mmorpg`、`play_mmorpg`、`not_mmo_mostplay`、`nested_ok`）都走通用码的 1 与 0。",
          "单选与有序题的码（1、2、3……）逐题列在下面。",
          "",
          "---",
          ""]
    covered = set()
    for mod, qs in QUESTION_ORDER:
        L.append("## %s" % mod)
        L.append("")
        for q in qs:
            block, cols = question_block(q)
            L += block
            covered |= cols
    L += ["---", "",
          "## 标识与派生变量",
          "",
          "- `ID`：原始导出的行号，剔除 %d 人之后不连续（缺 %s）；用来 join 与按人聚类"
          % (len(DROPPED), "、".join(str(i) for i in DROPPED_IDS)),
          "- `iirepSerial`：平台序列号，%d 个唯一值，不编码；用来向平台回溯" % N,
          "- `is_mmorpg`：1＝S1 或 S2 勾了 MMORPG 这个品类、0＝都不是（%d／%d）。"
          % (len(IS_MMO), N - len(IS_MMO)),
          "  自我标签口径，与 `play_mmorpg` 互不包含，用来把两种口径的差写进报告",
          "- `play_mmorpg`：1＝在 Q3 的 17 款里玩过至少一款、0＝一款都没玩过（%d／%d）。"
          % (len(PLAY_MMO), N - len(PLAY_MMO)),
          "  行为口径；Q3 至 Q8 与 Q18 至 Q27 的分母都用它",
          "- `not_mmo_mostplay`：1＝走 Q9 至 Q12、报的是自由填写的最常玩游戏，0＝走 Q5 至 Q8（%d／%d）。"
          % (N - len(Q4_PICK), len(Q4_PICK)),
          "  Q9 至 Q12 的分母。在玩组与不在玩组原来是 branch 这一列，2026-09-21 删掉，只留这一列",
          "- `nested_ok`：1＝Q3 的勾选完全落在 Q2 之内、0＝有一到两处越界（%d／%d）"
          % (len(NESTED_OK), N - len(NESTED_OK)),
          ""]
    covered |= set(NEW) | {"ID", "iirepSerial"}
    return "\n".join(L) + "\n", covered


# =============================================================== 7 自检
section("六、自检与各题分母")
FAIL = []


def need(cond, msg):
    if not cond:
        FAIL.append(msg)


need(SRC_ROWS == 600, "原始表行数应为 600，实测 %d" % SRC_ROWS)
need(len(DROPPED) == 21, "剔除人数应为 21，实测 %d" % len(DROPPED))
need(DROPPED_IDS == [11, 15, 33, 118, 140, 161, 282, 311, 312, 335, 348, 378, 387, 391,
                     435, 495, 501, 564, 576, 582, 594],
     "剔除名单与既定名单不符：%s" % DROPPED_IDS)
need(N == 579, "剔除后行数应为 579，实测 %d" % N)
need(len(HEAD) == 427, "列数应为 427，实测 %d" % len(HEAD))
need(all(len(r) == len(HEAD) for r in BODY), "有行列数不齐")
need(not [1 for r in BODY for v in r if v == ""], "还留着空白")
need(len(S1_RPG) == 536, "S1 勾 RPG 应为 536，实测 %d" % len(S1_RPG))
need(len(S1_MMO) == 210 and len(S2_MMO) == 68, "S1／S2 勾 MMORPG 应为 210／68，实测 %d／%d"
     % (len(S1_MMO), len(S2_MMO)))
need(len(IS_MMO) == 278, "is_mmorpg=1 应为 278，实测 %d" % len(IS_MMO))
need(len(PLAY_MMO) == 293, "play_mmorpg=1 应为 293，实测 %d" % len(PLAY_MMO))
need(len(PLAY_MMO - IS_MMO) == 67 and len(IS_MMO - PLAY_MMO) == 52,
     "两口径之差应为 67／52，实测 %d／%d" % (len(PLAY_MMO - IS_MMO), len(IS_MMO - PLAY_MMO)))
need(not (S1_MMO & S2_MMO), "S1 与 S2 的 MMORPG 不应有人重叠")
need(len(Q2_ESC) == 69, "Q2 逃亡口应为 69，实测 %d" % len(Q2_ESC))
need(len(Q3_ESC) == 217, "Q3 逃亡口应为 217，实测 %d" % len(Q3_ESC))
need(len(BRANCH_DUP) == 2, "在玩组与不在玩组的重叠应为 2 人，实测 %d" % len(BRANCH_DUP))
need(len(valid("IDP50__1")) == 510, "Q3 有效应为 510，实测 %d" % len(valid("IDP50__1")))
need(len(valid("IDP51__1")) == 293, "Q4 有效应为 293（= play_mmorpg=1 的同一批人），实测 %d"
     % len(valid("IDP51__1")))
need(valid("IDP51__1") == PLAY_MMO, "Q4 的应答题人群与 play_mmorpg=1 不是同一批人")
need(len(valid("IDP52")) == 198 and len(valid("IDP37")) == 381,
     "在玩组／不在玩组应为 198／381，实测 %d／%d" % (len(valid("IDP52")), len(valid("IDP37"))))
need(len(valid("IDP43__1")) == 146 and len(valid("IDP44__1")) == 221,
     "Q15／Q16 应为 146／221，实测 %d／%d" % (len(valid("IDP43__1")), len(valid("IDP44__1"))))
need(len(valid("IDP46__1")) == 293, "Q18 至 Q20、Q26、Q27 的分母应为 293，实测 %d"
     % len(valid("IDP46__1")))
need(len(valid("IDP55")) == 293, "Q23 的分母应为 293，实测 %d" % len(valid("IDP55")))
need(len(valid("IDP49__1")) == 268, "Q21 有效应为 268，实测 %d" % len(valid("IDP49__1")))
need(len(valid("IDP56__1")) == 206, "Q24 有效应为 206，实测 %d" % len(valid("IDP56__1")))
need(len(valid("IDP64__1")) == 232, "Q32 有效应为 232，实测 %d（本题不在 play_mmorpg 那一块里）"
     % len(valid("IDP64__1")))
need(len(valid("IDP53__1")) == 293, "Q22 有效应为 293，实测 %d" % len(valid("IDP53__1")))

# 三个派生标记各自与源事实一致
need({k for k in range(N) if GV("play_mmorpg", k) == "1"} == PLAY_MMO, "play_mmorpg 与 Q3 的勾选对不上")
need({k for k in range(N) if GV("nested_ok", k) == "1"} == NESTED_OK, "nested_ok 与 Q2／Q3 的关系对不上")
need({k for k in range(N) if GV("not_mmo_mostplay", k) == "1"} == set(range(N)) - Q4_PICK,
     "not_mmo_mostplay 应与「Q4 没勾到游戏」的人逐行相同")
need({k for k in range(N) if GV("is_mmorpg", k) == "1"} == IS_MMO, "is_mmorpg 与 S1／S2 的勾选对不上")

# Q4 必须落在 Q3 之内（Q4 的设计前提）；Q3 越界 Q2 的人保留，由 nested_ok 标出
need(not [1 for k in range(N) for g in range(1, 18)
          if GV("IDP51__%d" % g, k) == "1" and GV("IDP50__%d" % g, k) != "1"],
     "有人的 Q4 勾了 Q3 里没勾过的款")
need(len(NESTED_OK) == 517, "nested_ok=1 应为 517 人，实测 %d" % len(NESTED_OK))

# Q22 的每一行都要与 Q3 的勾选逐行一致，勾了行的人八条说法都得是 0／1
for g in range(1, 18):
    a = {k for k in range(N) if GV("IDP53__%d" % g, k) == "1"}
    b = {k for k in range(N) if GV("IDP50__%d" % g, k) == "1"} & PLAY_MMO
    need(a == b, "Q22 第 %d 行应等于「Q3 勾了这款且在 play_mmorpg 门槛内」的人" % g)
    rate = ["IDP54/L%d__%d" % (468 + g, s) for s in range(1, 9)]
    for k in range(N):
        if k in a and not {GV(h, k) for h in rate} <= {"0", "1"}:
            need(False, "Q22 第 %d 行有人勾了行却没打分" % g)

# Q17 与 Q28 整题无数据。日后重投有值，这里会拦下来，提醒重新对口径。
for h in ("IDP45", "IDP60", "IDP45_IDPA413", "IDP60_IDPA522"):
    need(n_of(h, NA_NOREC) == N,
         "%s 应整列 99（整题无数据），实测 99 有 %d 处" % (h, n_of(h, NA_NOREC)))

# 数字性：留下的文本列只能是那 17 个开放题，编码过的列不许还带文字。
# 「是文本列型」与「现在有没有文本」是两件事：Q25 的「其他」列现在整列没有文本
# （写了话的 16 人全在 play_mmorpg 门槛之外），它仍然是开放题列，只是这一轮空着。
text_cols = sorted(h for h in HEAD
                   if any(not v.isdigit() for r in BODY for v in [r[P[h]]]))
need(set(text_cols) <= set(OPEN_TEXT), "有编码过的列还留着文字：%s" % sorted(set(text_cols) - set(OPEN_TEXT)))
open_with_text = sorted(set(text_cols))
open_empty = sorted(set(OPEN_TEXT) - set(open_with_text))
say("")
say("开放题列 %d 个，其中这一轮有文本的 %d 个；整列没有文本的 %d 个：%s"
    % (len(OPEN_TEXT), len(open_with_text), len(open_empty),
       "、".join(open_empty) if open_empty else "无"))
if open_empty:
    say("  （这些列的作答人都落在 play_mmorpg 门槛之外，取值只剩 97／99。）")

# 受访者键：ID 是原始导出行号（剔除后有缺口），iirepSerial 是平台序列号，两者都不许被动
need([r[P["ID"]] for r in BODY] == [str(i) for i in ORIG_ID], "ID 不等于原始导出的行号")
need(not (set(map(int, [r[P["ID"]] for r in BODY])) & set(DROPPED_IDS)), "被剔除的人还在文件里")
need(len(set(r[P["iirepSerial"]] for r in BODY)) == N, "iirepSerial 不是 %d 个唯一值" % N)
need(HEAD[:5] == ["ID", "QUOTAGERANGE", "GENDER_NonBinary", "JPSTDREGION", "SCREENER1__1"],
     "前五列与预期不符：%s" % HEAD[:5])
need(HEAD[-4:] == NEW, "末四列应为新增标记：%s" % HEAD[-4:])
_md, COVER = build_code_table()
missing_code = [h for h in HEAD if h not in COVER]
need(not missing_code, "值码表漏了这些列：%s" % missing_code[:10])

fmt = "%-5s %-16s %7s %9s %9s  %s"
say(fmt % ("题", "变量", "清洗后N", "is_mmorpg", "play_mmorpg", "缺失码数量"))
GATES = [
    ("S1", "SCREENER1__1", "全卷"), ("S2", "SCREENER2__1", "仅 S1 勾 RPG"),
    ("S3", "SCREENER3__1", "全卷"), ("Q2", "IDP30__1", "全卷"),
    ("Q3", "IDP50__1", "Q2 未走逃亡口"), ("Q4", "IDP51__1", "Q3 勾过至少一款"),
    ("Q5", "IDP52", "Q4 仍有在玩"), ("Q6", "IDP34", "同 Q5"),
    ("Q7", "IDP35", "同 Q5"), ("Q8", "IDP36", "同 Q5；报告分母扣掉 98"),
    ("Q9", "IDP37", "三个逃亡口之一"), ("Q10", "IDP38", "同 Q9"),
    ("Q11", "IDP39", "同 Q9"), ("Q12", "IDP40", "同 Q9；报告分母扣掉 98"),
    ("Q13", "IDP41", "全卷"), ("Q14", "IDP42", "全卷"),
    ("Q15", "IDP43__1", "Q14 选不想体验"), ("Q16", "IDP44__1", "Q14 选想体验"),
    ("Q17", "IDP45", "play_mmorpg=1（整题无数据）"),
    ("Q18", "IDP46__1", "play_mmorpg=1"),
    ("Q19", "IDP47__1", "play_mmorpg=1"),
    ("Q20", "IDP48__1", "play_mmorpg=1"),
    ("Q21", "IDP49__1", "play_mmorpg=1，且 Q20 未选一直在玩"),
    ("Q22", "IDP53__1", "play_mmorpg=1（这 17 款里玩过至少一款）"),
    ("Q23", "IDP55", "play_mmorpg=1"),
    ("Q24", "IDP56__1", "play_mmorpg=1 且 Q23 非独狼"), ("Q25", "IDP57__1", "同 Q24"),
    ("Q26", "IDP58__1", "play_mmorpg=1"),
    ("Q27", "IDP59__1", "play_mmorpg=1"),
    ("Q28", "IDP60", "全卷（整题无数据）"), ("Q29", "IDP61", "全卷；报告分母扣掉 98"),
    ("Q30", "IDP62__1", "全卷"), ("Q31", "IDP63", "全卷"),
    ("Q32", "IDP64__1", "Q31 选关注"), ("Q33", "IDP65__1", "全卷"),
    ("Q34", "IDP66__1", "全卷"), ("Q35", "IDP67__1", "全卷"),
    ("Q36", "IDP68", "全卷"), ("Q37", "IDP69", "全卷；报告分母扣掉 98"),
]
den_rows = [["题号", "变量", "清洗后 N", "其中 is_mmorpg", "其中 play_mmorpg", "缺失 97",
             "缺失 98", "缺失 99", "设计门槛"]]
for q, h, gate in GATES:
    v = valid(h)
    say(fmt % (q, h, len(v), len(v & IS_MMO), len(v & PLAY_MMO),
               "97=%-6d 98=%-4d 99=%d" % (n_of(h, "97"), n_of(h, "98"), n_of(h, "99"))))
    den_rows.append([q, h, str(len(v)), str(len(v & IS_MMO)), str(len(v & PLAY_MMO)),
                     str(n_of(h, "97")), str(n_of(h, "98")), str(n_of(h, "99")), gate])

s97 = sum(1 for r in BODY for j, h in enumerate(HEAD) if is_survey(h) and r[j] == "97")
s98 = sum(1 for r in BODY for j, h in enumerate(HEAD) if is_survey(h) and r[j] == "98")
s99 = sum(1 for r in BODY for j, h in enumerate(HEAD) if is_survey(h) and r[j] == "99")
say("")
say("问卷变量区一共用掉：97 = %d 处，98 = %d 处，99 = %d 处。" % (s97, s98, s99))
say("98 另有 3 处在性别上（问卷 S4 的「回答しない」），不在问卷变量区内，合计 %d 处。" % (s98 + 3))
say("ID 与 iirepSerial 没被动过；这两列里的 97／98／99 是真实取值，不是缺失码。")
if FAIL:
    say("")
    say("自检未通过 %d 项：" % len(FAIL))
    for f in FAIL:
        say("  ✗ %s" % f)

# =============================================================== 8 写盘
section("七、产出")
check_lines = []
if CHECK_ONLY:
    # 漂移比对：把这次算出来的表与磁盘上现有的产物逐处比，只看不写。
    CODE_MD, _cover = build_code_table()
    for path, kind, head, rows in ((DST, "csv", HEAD, BODY),
                                   (DEN_OUT, "csv", den_rows[0], den_rows[1:]),
                                   (CODES_OUT, "md", None, CODE_MD.splitlines())):
        name = os.path.basename(path)
        if not os.path.exists(path):
            check_lines.append("--check：%s 不存在，跳过。" % name)
            continue
        if kind == "md":
            old = io.open(path, encoding="utf-8").read().splitlines()
            if old == rows:
                check_lines.append("--check：%s 完全一致" % name)
                continue
            n = min(len(old), len(rows))
            at = next((k for k in range(n) if old[k] != rows[k]), n)
            check_lines.append("--check：%s 不一致，行数 %d／%d，第一处在第 %d 行"
                               % (name, len(old), len(rows), at + 1))
            continue
        with io.open(path, encoding="utf-8-sig", newline="") as fh:
            rd = csv.reader(fh)
            old_head = next(rd)
            old = [r for r in rd]
        if old_head != head or len(old) != len(rows):
            check_lines.append("--check：%s 不一致，表头或行数不同。" % name)
            continue
        where = ""
        for k, (a, b) in enumerate(zip(old, rows)):
            if a != b:
                where = "第 %d 行" % (k + 1)
                break
        check_lines.append("--check：%s %s"
                           % (name, "完全一致" if not where else "不一致，第一处在 " + where))
    say("\n".join(check_lines))
if FAIL:
    print("cleaning FAILED：%d 项自检未通过" % len(FAIL))
    for f in FAIL:
        print("  ✗ %s" % f)
    sys.exit(1)
if CHECK_ONLY:
    print("\n".join(check_lines))
    sys.exit(0)

os.makedirs(OUTDIR, exist_ok=True)
with io.open(DST, "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(HEAD)
    w.writerows(BODY)
CODE_MD, COVER = build_code_table()
with io.open(CODES_OUT, "w", encoding="utf-8") as fh:
    fh.write(CODE_MD)
say("值码表：%d 行，按 %d 道题排，覆盖数据集里全部 %d 列（markdown）。"
    % (CODE_MD.count("\n"), sum(len(qs) for _, qs in QUESTION_ORDER), len(COVER)))
with io.open(DEN_OUT, "w", encoding="utf-8-sig", newline="") as fh:
    csv.writer(fh).writerows(den_rows)
with io.open(LOG_OUT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(LOG))
print("cleaning OK: %d rows x %d cols; 97=%d 98=%d 99=%d" % (len(BODY), len(HEAD), s97, s98, s99))
