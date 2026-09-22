# -*- coding: utf-8 -*-
# 预测概率：每条说法用它那一个最优模型，算每个游戏的平均预测概率。
#
#   Rscript 092601_regression_pred.R <长表.csv> <产物目录> <输出.csv>
#
# 为什么另出一支：现有产物只有 β／SE／OR／95%CI 与原始勾选率，没有模型预测概率。
# 业务结论要说的「低约几个百分点」是控制受访者属性与偏好之后，每个游戏的平均预测
# 概率与《最终幻想14》之差；拿原始勾选率之差顶替，量的是「谁在评这一组游戏」，
# 两件事不能当一句读。
#
# 口径：分析样本（协变量不缺答的 1052 条「人-游戏」记录），与最优模型同一批行；
# predict(type = "response", re.form = NA) 把随机截距取 0，得到总体层面的预测概率。
# 模型按 回归表_最优模型.csv 的「保留的项」重建，项的顺序照逐步链的
# 游戏→年龄档→性别→在玩与否→评了几个→社交方式→预算→偏好项，与 Rmd 里的 setdiff 同序。
# 重拟合之后核对 logLik 与 AIC 与那两列存的读数是否一致，不一致就停、不写盘。
#
# 这一支只拟合八条说法各自的一个最优模型，不重跑逐步链，几分钟跑得完。

Sys.setlocale("LC_CTYPE", "en_US.UTF-8")
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 3) {
  stop("用法：Rscript 092601_regression_pred.R <长表.csv> <产物目录> <输出.csv>")
}
SRC <- normalizePath(args[1], winslash = "/")
DIR <- normalizePath(args[2], winslash = "/", mustWork = FALSE)
OUTP <- args[3]

suppressPackageStartupMessages(library(lme4))

LB <- read.csv(file.path(DIR, "q22_labels.csv"), stringsAsFactors = FALSE,
               fileEncoding = "UTF-8")
GT <- LB[LB$type == "game", ]
CT <- LB[LB$type == "claim", ]
PT <- LB[LB$type == "pref", ]
GAME_SHORT <- GT$short
GAME_CN <- setNames(GT$cn, GT$short)
CLAIM_CN <- setNames(CT$cn, as.character(CT$key))
PREF_IDX <- setNames(suppressWarnings(as.integer(PT$short)), PT$key)

OPT <- read.csv(file.path(DIR, "回归表_最优模型.csv"), stringsAsFactors = FALSE,
                fileEncoding = "UTF-8")
stopifnot(nrow(OPT) == 8L)

D <- read.csv(SRC, stringsAsFactors = FALSE)
stopifnot(nrow(D) == 8544L, all(D$y %in% c(0L, 1L)))
D$pid <- factor(D$pid)
D$game <- factor(GAME_SHORT[D$gidx], levels = GAME_SHORT)
na0 <- function(x) ifelse(x < 0, NA, x)
D$age <- factor(na0(D$age))
D$sex <- factor(na0(D$sex))
D$social <- factor(na0(D$social))
D$budget <- factor(na0(D$budget))
D$stillply <- factor(D$nowp, levels = c(0, 1))
Q18C <- paste0("q18_", 1:9)
for (h in Q18C) D[[h]] <- na0(D[[h]])

# 分析样本：与 Rmd 同一套条件、同一批行
COV <- c("stillply", "nrat", "social", "budget", "sex", "age")
D <- D[complete.cases(D[, COV]), ]
D$pid <- droplevels(D$pid)
# 8544 行减去 16 条缺答记录 × 8 条说法 = 8416 行；每条说法 1052 行、287 位受访者
stopifnot(nrow(D) == 8416L, length(unique(D$pid)) == 287L)

# 最优模型的固定效应项：照逐步链的顺序排，与 Rmd 里 setdiff() 的结果同序
CANON <- c("game", "age", "sex", "stillply", "nrat", "social", "budget", "pref")
CTRL <- glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5))

RES <- NULL
LOG <- character(0)
add_log <- function(...) LOG <<- c(LOG, sprintf(...))

for (i in seq_len(nrow(OPT))) {
  s <- as.integer(OPT$说法号[i])
  cn <- OPT$说法[i]
  kept <- strsplit(OPT$保留的项[i], "＋")[[1]]
  terms <- CANON[CANON %in% kept]
  dd <- D[D$claim == s, ]
  pi_ <- PREF_IDX[[as.character(s)]]
  if ("pref" %in% terms) {
    if (is.na(pi_)) stop(sprintf("%s 的最优模型含偏好项，但标签表里没有对位项", cn))
    dd$pref <- dd[[Q18C[pi_]]]
  }
  f <- as.formula(paste("y ~", paste(terms, collapse = " + "), "+ (1 | pid)"))
  T0 <- Sys.time()
  m <- glmer(f, data = dd, family = binomial, control = CTRL)
  mins <- as.numeric(difftime(Sys.time(), T0, units = "mins"))

  # 自检：重拟合的 logLik 与 AIC 必须与 回归表_最优模型.csv 存的读数一致
  ll_got <- as.numeric(logLik(m)); aic_got <- AIC(m)
  ll_ref <- as.numeric(OPT$logLik[i]); aic_ref <- as.numeric(OPT$AIC[i])
  ok <- abs(ll_got - ll_ref) < 0.01 && abs(aic_got - aic_ref) < 0.05
  add_log("%s｜项 %s｜logLik %.2f（存 %.2f）｜AIC %.2f（存 %.2f）｜%.1f 分钟",
          cn, paste(terms, collapse = "+"), ll_got, ll_ref, aic_got, aic_ref, mins)
  if (!ok) stop(sprintf("%s 的重拟合与盘上读数不一致，停在这里不写盘", cn))

  # 平均预测概率：随机截距取 0，对每个游戏的记录取均值
  pr <- predict(m, newdata = dd, type = "response", re.form = NA)
  base <- mean(pr[dd$game == "FFXIV"])
  for (g in GAME_SHORT) {
    idx <- dd$game == g
    RES <- rbind(RES, data.frame(
      说法 = cn, 说法号 = s, 游戏 = GAME_CN[[g]], 游戏代号 = g,
      记录数 = sum(idx),
      平均预测概率 = round(mean(pr[idx]), 4),
      基准平均预测概率 = round(base, 4),
      与基准差_pp = round(100 * (mean(pr[idx]) - base), 2),
      stringsAsFactors = FALSE))
  }
}

write.csv(RES, OUTP, row.names = FALSE, fileEncoding = "UTF-8")
writeLines(LOG, file.path(DIR, "预测概率日志.txt"), useBytes = TRUE)
cat(paste(LOG, collapse = "\n"), "\n")
cat(sprintf("写了 %s（%d 行）\n", OUTP, nrow(RES)))
