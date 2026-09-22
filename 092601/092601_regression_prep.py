# -*- coding: utf-8 -*-
"""日本 MMORPG 玩家定量调研 —— Q22 品类形象矩阵的回归输入（脚本 092601_regression_prep）

这一支与 092601_cleaning.py、092601_analysis.py 配对：清洗脚本把平台导出收成分析文件，
分析脚本算分布与配对，这一支把 Q22 的矩形矩阵摊平成回归能直接读的长表，交给
092601_regression.Rmd 建模。分工的理由是 R 侧不碰清洗——形状与标签在这里定死，
R 里只做模型与表格，第三支脚本才能与前面两支对上账。

为什么要把中文标签单独出一份：UKDS 的规矩是标签随文件走，长表里全是数字码，
游戏名、国别名、八条说法的中文名放在同一目录的 q22_labels.csv 里，
改标签不用动数据，R 侧也不出现硬编码的中文对照。

  ｜ 输出一行一条「受访者 × 游戏 × 说法」记录，共 8544 行：
  ｜   pid    受访者 ID（原始导出行号，作聚类变量用）
  ｜   gidx   游戏序号 1–17，顺序与问卷 Q22 的 17 个游戏一致
  ｜   claim  说法序号 1–8
  ｜   y      因变量，1＝勾了这条说法、0＝没勾
  ｜   ctry   开发主导方，1 日、2 韩、3 中、4 美中；由 gidx 唯一决定，不是独立自变量
  ｜   isro   RO 四个游戏之一
  ｜   nowp   现在还在玩这个游戏（0／1），来自 Q4 的同序项
  ｜   nrat   这位受访者一共评了几个游戏
  ｜   age／sex／social／budget  受访者属性，见下；缺失写 −1，R 侧转回 NA

受访者属性的出处：age 取面板配额 S5（1＝18–29、2＝30–49、3＝50–60），
sex 取 S4（0＝男性、1＝女性），social 取 Q23（1 主动、2 被动、3 独狼、4 视情况），
budget 取 Q37（1 几乎没有 ～ 7 十万円以上）。四者都按「谁在答」这一层解释，
不含任何游戏侧信息。

输入  Datasets/RPG.csv        579 行，由 092601_cleaning.py 产出
输出  <输出目录>/q22_long_ascii.csv   8544 行，全 ASCII 数字码，给 R 读
      <输出目录>/q22_labels.csv       游戏、国别、说法的中文与日文对照
      <输出目录>/regression_prep_log.txt

用法  python 092601_regression_prep.py RPG.csv 输出目录
      python 092601_regression_prep.py RPG.csv 输出目录 --check   只重算比对，不写盘
"""
import csv
import io
import os
import sys

CHECK_ONLY = "--check" in sys.argv
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = ARGS[0] if ARGS else os.path.join(HERE, "data", "RPG.csv")
OUTDIR = ARGS[1] if len(ARGS) > 1 else os.path.dirname(os.path.abspath(SRC))
LONG_OUT = os.path.join(OUTDIR, "q22_long_ascii.csv")
LABEL_OUT = os.path.join(OUTDIR, "q22_labels.csv")
LOG_OUT = os.path.join(OUTDIR, "regression_prep_log.txt")

NA = ("97", "98", "99")

# 17 个游戏的短名（ASCII，R 侧认这一套）、中文名、日文原名、开发主导方
GAMES = [
    ("FFXIV", "最终幻想14", "ファイナルファンタジーXIV", 1),
    ("BLUE_PROTOCOL", "蓝色协议", "BLUE PROTOCOL", 1),
    ("BDO_MOBILE", "黑色沙漠 MOBILE", "黒い砂漠 MOBILE", 2),
    ("LINEAGE_M", "天堂M", "リネージュM", 2),
    ("LINEAGE2M", "天堂2M", "リネージュ2M", 2),
    ("ODIN_RAISING", "奥丁：神叛", "オーディン：ヴァルハラ・ライジング", 2),
    ("ASHTALE", "风之大陆", "Ash Tale-風の大陸-", 3),
    ("TOS_NEVERLAND", "救世之树：Neverland", "ツリーオブセイヴァー：ネバーランド", 2),
    ("ZHANGJIAN", "杖剑传说", "杖と剣の伝説", 3),
    ("AZUREA", "天谕", "AZUREA-空の唄-", 3),
    ("DIABLO_IMMORTAL", "暗黑破坏神：不朽", "ディアブロ イモータル", 4),
    ("COD_DRAGONBLOOD", "龙族幻想", "コード：ドラゴンブラッド", 3),
    ("NINOKUNI_CW", "二之国：交错世界", "二ノ国：Cross Worlds", 2),
    ("RO_ONLINE", "仙境传说 Online", "ラグナロクオンライン", 2),
    ("RO_MASTERS", "仙境传说RO：守护永恒的爱", "ラグナロク マスターズ", 2),
    ("RO_X", "仙境传说：新世代的诞生", "ラグナロクX", 2),
    ("RO_ORIGIN", "仙境传说 ORIGIN", "ラグナロクオリジン", 2),
]
CTRY_CN = {1: "日系", 2: "韩系", 3: "中系", 4: "美中联合"}
CLAIMS = [
    ("画面音乐", "グラフィックや音楽が非常に魅力的である"),
    ("战斗手感", "戦闘システムや操作の手応えが良い"),
    ("系统深度", "ゲームシステムや育成要素に十分な深みがある"),
    ("故事世界观", "ストーリーや世界観に強い魅力がある"),
    ("角色设计", "キャラクターデザインやグラフィックのクオリティが高い"),
    ("找得到队友", "一緒にプレイする仲間が見つかりやすい"),
    ("课金友善", "課金システムがプレイヤーに対して親切である"),
    ("社区热闹", "コミュニティが盛り上がっており、ネット上での議論や話題が多い"),
]
HEAD = ["pid", "gidx", "claim", "y", "ctry", "isro", "nowp", "nrat",
        "age", "sex", "social", "budget", "play", "notplay"]
LOG = []


def say(s=""):
    LOG.append(s)


def section(t):
    say("")
    say("=" * 78)
    say(t)
    say("=" * 78)


def build():
    with io.open(SRC, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    COL = {h: j for j, h in enumerate(rows[0])}
    D = rows[1:]
    n = len(D)
    assert n == 579, "应为 579 行，实测 %d" % n
    section("一、读入与自检")
    say("  %s：%d 行 × %d 列" % (os.path.basename(SRC), n, len(rows[0])))

    def num(h, k):
        v = D[k][COL[h]]
        return None if v in NA or v == "" else int(float(v))

    pid = [int(D[k][COL["ID"]]) for k in range(n)]
    play = [num("play_mmorpg", k) for k in range(n)]
    notplay = [num("not_mmo_mostplay", k) for k in range(n)]
    row_of, now_of = {}, {}
    for g in range(1, 18):
        row_of[g] = [num("IDP53__%d" % g, k) for k in range(n)]
        now_of[g] = [num("IDP51__%d" % g, k) for k in range(n)]
    nrat = [sum(1 for g in range(1, 18) if row_of[g][k] == 1) for k in range(n)]

    # 行标记与 Q3 的一致性：Q22 出过题的人，人都落在 play_mmorpg=1 里
    rated = [k for k in range(n) if nrat[k] > 0]
    assert all(play[k] == 1 for k in rated), "有行标记的人必须都 play_mmorpg=1"
    say("  出过 Q22 的受访者 %d 人，都在 play_mmorpg=1 的 293 人里（本文件用不到未出题者的空行）"
        % len(rated))
    for g in range(1, 18):
        c = sum(1 for k in range(n) if row_of[g][k] == 1)
        assert c >= 20, "第 %d 个游戏只有 %d 人评过，低于 N≥20 的门槛" % (g, c)
    say("  逐个游戏评过的人数：%d–%d" % (
        min(sum(1 for k in range(n) if row_of[g][k] == 1) for g in range(1, 18)),
        max(sum(1 for k in range(n) if row_of[g][k] == 1) for g in range(1, 18))))

    def code(v):
        return -1 if v is None else v

    out = [HEAD]
    n_miss = 0
    for g in range(1, 18):
        ks = [k for k in range(n) if row_of[g][k] == 1]
        for s in range(1, 9):
            vals = [num("IDP54/L%d__%d" % (468 + g, s), k) for k in range(n)]
            for k in ks:
                v = vals[k]
                if v is None:
                    # 与 092601_analysis.py 的口径一致：基数取行内人数，缺失按未勾处理
                    v = 0
                    n_miss += 1
                out.append([pid[k], g, s, v, GAMES[g - 1][3],
                            1 if g in (14, 15, 16, 17) else 0,
                            now_of[g][k] if now_of[g][k] is not None else 0,
                            nrat[k], code(num("QUOTAGERANGE", k)),
                            code(num("GENDER_NonBinary", k)), code(num("IDP55", k)),
                            code(num("IDP69", k)), play[k], notplay[k]])

    section("二、长表规模")
    per_claim = [sum(1 for r in out[1:] if r[2] == s) for s in range(1, 9)]
    assert len(set(per_claim)) == 1, "八条说法的人-游戏记录数应完全一致：%s" % per_claim
    assert per_claim[0] == 1068, "每条说法应有 1068 条人-游戏记录，实测 %d" % per_claim[0]
    assert len(out) - 1 == 1068 * 8, "长表应为 8544 行，实测 %d" % (len(out) - 1)
    assert all(r[3] in (0, 1) for r in out[1:]), "因变量只能是 0 或 1"
    say("  %d 条人-游戏记录 × 8 条说法 = %d 行" % (per_claim[0], len(out) - 1))
    say("  出题时按未勾处理的缺失处：%d 处（同一个受访者、同一个游戏）" % n_miss)

    section("三、逐条说法的事件数")
    for s in range(1, 9):
        rs = [r for r in out[1:] if r[2] == s]
        say("  第 %d 条　%-6s  行 %d，勾了 %d（%.1f%%）"
            % (s, CLAIMS[s - 1][0], len(rs), sum(r[3] for r in rs),
               100.0 * sum(r[3] for r in rs) / len(rs)))

    section("四、协变量的取值分布（缺失写 −1，R 侧转 NA）")
    for name, idx in (("age", 8), ("sex", 9), ("social", 10), ("budget", 11)):
        vals = sorted(set(r[idx] for r in out[1:]))
        ctl = {}
        for r in out[1:]:
            if r[2] == 1:
                ctl[r[idx]] = ctl.get(r[idx], 0) + 1
        say("  %-7s 取值 %s" % (name, ", ".join("%d(%d 人-游戏)" % (v, ctl[v]) for v in vals)))

    labels = [["type", "key", "short", "cn", "jp_or_cn"]]
    for i, (short, cn, jp, ctry) in enumerate(GAMES, start=1):
        labels.append(["game", i, short, cn, jp])
    for i, (cn, jp) in enumerate(CLAIMS, start=1):
        labels.append(["claim", i, "C%d" % i, cn, jp])
    for k in sorted(CTRY_CN):
        labels.append(["ctry", k, str(k), CTRY_CN[k], ""])
    for k, lab in ((0, "已不在玩"), (1, "现在还在玩")):
        labels.append(["nowp", k, str(k), lab, ""])
    labels.append(["cov", "age", "age", "面板年龄档（1=18–29、2=30–49、3=50–60）", "S5"])
    labels.append(["cov", "sex", "sex", "性别（0=男性、1=女性，缺失=98/99）", "S4"])
    labels.append(["cov", "social", "social", "社交方式（1=主动、2=被动、3=独狼、4=视情况）", "Q23"])
    labels.append(["cov", "budget", "budget", "每月娱乐预算（1=几乎没有 ～ 7=十万円以上）", "Q37"])
    return out, labels


def compare(dst, text):
    """--check：重算出来的东西与盘上的逐行比，不一致就报出来。"""
    if not os.path.exists(dst):
        say("  [x] %s 不存在，无法比对" % os.path.basename(dst))
        return False
    old = io.open(dst, encoding="utf-8", newline="").read()
    if old == text:
        say("  [v] %s 与盘上逐字一致" % os.path.basename(dst))
        return True
    a, b = old.splitlines(), text.splitlines()
    say("  [x] %s 与盘上不一致：盘上 %d 行，重算 %d 行" % (os.path.basename(dst), len(a), len(b)))
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            say("      第 %d 行：盘上 %r ／ 重算 %r" % (i + 1, a[i], b[i]))
            break
    return False


def dump(rows):
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue()


def main():
    out, labels = build()
    long_text, label_text = dump(out), dump(labels)

    section("五、落盘")
    ok = True
    if CHECK_ONLY:
        say("  --check：只比对，不写盘")
        ok &= compare(LONG_OUT, long_text)
        ok &= compare(LABEL_OUT, label_text)
    else:
        with io.open(LONG_OUT, "w", encoding="ascii", newline="") as f:
            f.write(long_text)
        with io.open(LABEL_OUT, "w", encoding="utf-8", newline="") as f:
            f.write(label_text)
        say("  %s：%d 行（含表头）" % (os.path.basename(LONG_OUT), len(out)))
        say("  %s：%d 行（含表头）" % (os.path.basename(LABEL_OUT), len(labels)))
    if not ok:
        say("  自检未通过，视为不通过")
        sys.stdout.write("\n".join(LOG) + "\n")
        sys.exit(1)

    say("")
    say("  结论：长表 %d 行、每条说法 1068 条人-游戏记录、17 个游戏、293 位受访者。" % (len(out) - 1))
    text = "\n".join(LOG) + "\n"
    if not CHECK_ONLY:
        with io.open(LOG_OUT, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    sys.stdout.write(text)


if __name__ == "__main__":
    main()
