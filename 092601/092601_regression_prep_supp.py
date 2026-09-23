# -*- coding: utf-8 -*-
"""日本 MMORPG 玩家定量调研 —— 补充样本的 Q22 回归输入（2026-09-23 下午轮改版）

**与上一版的差别（用户 2026-09-23 裁定）**：

  一、输入换成合并清洗后的 `Datasets/JP_RPG.csv`（不再直接读原始 xlsx／Batch2_Original.csv）。
      只取 `is_batch2=1` 的 145 行（原 150 行剔掉 Q2 与 Q3 勾选完全不相交的 5 人）。
  二、年龄回到长表：`age` 取 `age_group` 的四档（1＝18–29、2＝30–39、3＝40–49、4＝50–60），
      逐步链因此恢复六步、属性项恢复六项，与主样本那一支同形。
  三、勇者斗恶龙X 进同一块长表：`gidx=18`，与 17 个共有游戏一处，只出一份主表
      （上一版另出的 `q22_long_ascii_supp_dqx.csv` 取消）。
  四、取值已由清洗阶段编成数字码：多选与评分列 1／0／97，单选按值码表；不再做 Yes／No 转换。

输出两件，沿用主样本那一套列名：

  主表  q22_long_ascii_supp.csv    18 个游戏的框架：482 条人-游戏记录 × 8 条说法 ＝ 3856 行
  附  q22_labels_supp.csv          标签表，含 gidx=18 那一行

用法  python 092601_regression_prep_supp.py [JP_RPG.csv [输出目录]] [--check]
"""
import csv
import io
import os
import sys

CHECK_ONLY = "--check" in sys.argv
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SRC = ARGS[0] if ARGS else os.path.join(ROOT, "Datasets", "JP_RPG.csv")
OUTDIR = ARGS[1] if len(ARGS) > 1 else os.path.join(ROOT, "Datasets", "_derived", "regression_batch2")
LONG_OUT = os.path.join(OUTDIR, "q22_long_ascii_supp.csv")
LABEL_OUT = os.path.join(OUTDIR, "q22_labels_supp.csv")
LOG_OUT = os.path.join(OUTDIR, "regression_prep_supp_log.txt")

NA_ALL = ("97", "98", "99")

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
DQX = ("DQX", "勇者斗恶龙X", "ドラゴンクエストX", 1)
CTRY_CN = {1: "日系", 2: "韩系", 3: "中系", 4: "美中联合"}
CLAIMS = [
    ("画面音乐", "グラフィックや音楽が非常に魅力的である"),
    ("战斗手感", "戦闘システムや操作の手応えが良い"),
    ("系统深度", "ゲームシステムや育成要素に十分な深みがある"),
    ("故事世界观", "ストーリーや世界観に強い魅力がある"),
    ("角色设计", "キャラクターデザインやグラフィックのクオリティが高い"),
    ("找得到队友", "一緒にプレイする仲間が見つけやすい"),
    ("课金友善", "課金システムがプレイヤーに対して親切である"),
    ("社区热闹", "コミュニティが盛り上がっており、ネット上の議論や話題が多い"),
]
Q18_ITEMS = [
    ("探索大世界", "オープンワールドの探索"),
    ("角色养成与职业构筑", "キャラクターの育成やビルド"),
    ("大规模公会对抗", "大規模なギルド対戦（攻城戦、拠点戦など）"),
    ("组队打副本", "他人と協力して高難易度ダンジョン（コンテンツ）を攻略する"),
    ("收集与生活玩法", "アイテム収集や生活系コンテンツ（採掘、製作など）"),
    ("剧情与世界观", "ストーリーや世界観"),
    ("画面表现与音乐", "グラフィックや音楽"),
    ("自由的交易与经济", "自由度の高いトレードや金策システム"),
    ("其他", "その他（具体的にご記入ください）"),
]
PREF_MAP = {
    1: (7, "完全对位"), 2: (None, ""), 3: (2, "部分对位"), 4: (6, "完全对位"),
    5: (None, ""), 6: (None, ""), 7: (8, "部分对位"), 8: (None, ""),
}
HEAD = ["pid", "gidx", "claim", "y", "ctry", "isro", "nowp", "nrat",
        "age", "sex", "social", "budget", "play", "notplay"] + \
       ["q18_%d" % i for i in range(1, 10)]
LOG = []


def say(s=""):
    LOG.append(s)


def section(t):
    say("")
    say("=" * 78)
    say(t)
    say("=" * 78)


def gcol(g):
    """第 g 个游戏的 Q22 行标记列名（1–17 是共有游戏，18 是勇者斗恶龙X）。"""
    return "IDP53__DQX" if g == 18 else "IDP53__%d" % g


def rcol(g, s):
    """第 g 个游戏第 s 条说法的列名。"""
    return "IDP54/L577__%d" % s if g == 18 else "IDP54/L%d__%d" % (468 + g, s)


def build():
    with io.open(SRC, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    HEADIN = rows[0]
    D = [r for r in rows[1:] if r and r[0] != ""]
    J = {h: i for i, h in enumerate(HEADIN)}
    section("一、读入与自检")
    say("  %s：%d 行 × %d 列（单行表头）" % (os.path.basename(SRC), len(D), len(HEADIN)))
    batch2 = [r for r in D if r[J["is_batch2"]] == "1"]
    assert len(batch2) == 145, "补充样本应为 145 行，实测 %d" % len(batch2)
    say("  is_batch2=1 的 %d 行入选（原 150 行里剔掉 Q2∩Q3 不相交的 5 人）。" % len(batch2))

    def val(r, h):
        return r[J[h]]

    pid = [int(val(r, "ID")) for r in batch2]
    assert len(set(pid)) == 145, "pid 不唯一"
    assert all(601 <= p <= 750 for p in pid), "补充样本的 ID 应在 601–750"

    mark = {}
    for g in range(1, 19):
        mark[g] = [val(r, gcol(g)) == "1" for r in batch2]
    nrat = [sum(mark[g][k] for g in range(1, 19)) for k in range(145)]
    play = [val(r, "play_mmorpg") for r in batch2]
    assert all(play[k] == "1" for k in range(145) if nrat[k] > 0), "有行标记的人必须都在 play 里"
    rated = [k for k in range(145) if nrat[k] > 0]
    n_dqx = sum(mark[18])
    rec17 = sum(1 for k in range(145) for g in range(1, 18) if mark[g][k])
    say("  出过 Q22 的受访者 %d 人；人-游戏记录：17 个共有游戏 %d 条 ＋ 勇者斗恶龙X %d 条 ＝ %d 条。"
        % (len(rated), rec17, n_dqx, rec17 + n_dqx))
    assert len(rated) == 123 and rec17 == 392 and n_dqx == 90, \
        "Q22 读数与预期不符：%d／%d／%d" % (len(rated), rec17, n_dqx)

    q18 = [[("1" if val(r, "IDP46__%d" % i) == "1" else "0") for r in batch2]
           for i in range(1, 10)]
    q18_sel = [sum(1 for i in range(9) if q18[i][k] == "1") for k in range(145)]
    ans18 = {k for k in range(145) if q18_sel[k] > 0}
    assert ans18 == set(rated), "Q18 的作答人与 Q22 的出题人不是同一批"

    out = [HEAD]
    ys = {s: 0 for s in range(1, 9)}
    for g in range(1, 19):
        _ctry = GAMES[g - 1][3] if g <= 17 else DQX[3]
        for s in range(1, 9):
            for k in range(145):
                if not mark[g][k]:
                    continue
                y = val(batch2[k], rcol(g, s))
                assert y in ("0", "1"), "因变量只能是 0／1，实测 %r（g=%d s=%d）" % (y, g, s)
                ys[s] += int(y)
                rec = [pid[k], g, s, int(y), _ctry,
                       1 if g in (14, 15, 16, 17) else 0,
                       int(val(batch2[k], "IDP51__DQX" if g == 18 else "IDP51__%d" % g)),
                       nrat[k],
                       int(val(batch2[k], "age_group")),
                       int(val(batch2[k], "GENDER_NonBinary"))
                       if val(batch2[k], "GENDER_NonBinary") in ("0", "1") else -1,
                       int(val(batch2[k], "IDP55"))
                       if val(batch2[k], "IDP55") not in NA_ALL else -1,
                       int(val(batch2[k], "IDP69"))
                       if val(batch2[k], "IDP69") not in NA_ALL else -1,
                       int(play[k]),
                       1 if val(batch2[k], "not_mmo_mostplay") == "1" else 0] + \
                      [int(q18[i][k]) for i in range(9)]
                out.append(rec)
    section("二、长表规模")
    say("  主表：%d 条人-游戏记录 × 8 条说法 ＝ %d 行"
        % ((len(out) - 1) // 8, len(out) - 1))
    assert (len(out) - 1) % 8 == 0
    per = [sum(1 for r in out[1:] if r[2] == s) for s in range(1, 9)]
    assert len(set(per)) == 1, "八条说法的人-游戏记录数应完全一致：%s" % per
    say("  八条说法的人-游戏记录数逐条一致（各 %d 条）；逐条说法的事件数：%s"
        % (per[0], "　".join("%s %d" % (CLAIMS[s - 1][0], ys[s]) for s in range(1, 9))))
    section("三、协变量（缺失写 −1）")
    for name, idx in (("age", 8), ("sex", 9), ("social", 10), ("budget", 11)):
        ctl = {}
        for r in out[1:]:
            if r[2] == 1:
                ctl[r[idx]] = ctl.get(r[idx], 0) + 1
        say("  %-7s 取值 %s" % (name, ", ".join("%d(%d 条人-游戏)" % (v, ctl[v])
                                                for v in sorted(ctl))))
    say("  age ＝ age_group 的四档（1＝18–29、2＝30–39、3＝40–49、4＝50–60），全员齐。")
    miss = [r for r in out[1:] if r[9] < 0]
    say("  性别缺答：%d 条记录（%d 位受访者，id %s）"
        % (len(miss), len({r[0] for r in miss}), sorted({r[0] for r in miss})))

    labels = [["type", "key", "short", "cn", "jp_or_cn"]]
    for i, (short, cn, jp, ctry) in enumerate(GAMES, start=1):
        labels.append(["game", i, short, cn, jp])
    labels.append(["game", 18, DQX[0], DQX[1], DQX[2]])
    for i, (cn, jp) in enumerate(CLAIMS, start=1):
        labels.append(["claim", i, "C%d" % i, cn, jp])
    for k in sorted(CTRY_CN):
        labels.append(["ctry", k, str(k), CTRY_CN[k], ""])
    for k, lab in ((0, "已不在玩"), (1, "现在还在玩")):
        labels.append(["nowp", k, str(k), lab, ""])
    for i, (cn, jp) in enumerate(Q18_ITEMS, start=1):
        labels.append(["q18", i, "Q18_%d" % i, cn, jp])
    for s in range(1, 9):
        i, tag = PREF_MAP[s]
        labels.append(["pref", s, "" if i is None else str(i), tag, ""])
    labels.append(["cov", "age", "age", "年龄档四档：1＝18–29、2＝30–39、3＝40–49、4＝50–60", "S5"])
    labels.append(["cov", "sex", "sex", "性别（0=男性、1=女性），缺失 = −1", "S4"])
    labels.append(["cov", "social", "social", "社交方式（1=主动、2=被动、3=独狼、4=视情况）", "Q23"])
    labels.append(["cov", "budget", "budget", "每月娱乐预算（1=几乎没有 ～ 7=十万日元以上）", "Q37"])
    return out, labels, ys


def compare(dst, text):
    if not os.path.exists(dst):
        say("  [x] %s 不存在，无法比对" % os.path.basename(dst))
        return False
    old = io.open(dst, encoding="utf-8", newline="").read()
    if old == text:
        say("  [v] %s 与盘上逐字一致" % os.path.basename(dst))
        return True
    say("  [x] %s 与盘上不一致" % os.path.basename(dst))
    return False


def dump(rows):
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue()


def main():
    out, labels, ys = build()
    texts = [(LONG_OUT, dump(out)), (LABEL_OUT, dump(labels))]
    section("四、落盘")
    ok = True
    if CHECK_ONLY:
        say("  --check：只比对，不写盘")
        for p, t in texts:
            ok &= compare(p, t)
    else:
        for p, t in texts:
            enc = "utf-8" if p == LABEL_OUT else "ascii"
            with io.open(p, "w", encoding=enc, newline="") as f:
                f.write(t)
            say("  %s：%d 行（含表头）" % (os.path.basename(p), t.count("\n") + 1))
    if not ok:
        say("  自检未通过，视为不通过")
        sys.stdout.write("\n".join(LOG) + "\n")
        sys.exit(1)
    say("")
    say("  结论：18 个游戏、%d 行；出过 Q22 的 123 人、482 条人-游戏记录。" % (len(out) - 1))
    text = "\n".join(LOG) + "\n"
    if not CHECK_ONLY:
        with io.open(LOG_OUT, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    sys.stdout.write(text)


if __name__ == "__main__":
    main()
