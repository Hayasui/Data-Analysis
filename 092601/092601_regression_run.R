# -*- coding: utf-8 -*-
# 命令行外壳：把参数交给 092601_regression.Rmd 渲染，本身不做任何计算。
# 与 Python 那两支的用法对齐：
#   Rscript 092601_regression_run.R <长表.csv> <输出目录> [--check] [--claims=7,8]
#   --check        只重算并与盘上的表比对，不写盘
#   --claims=a,b   只跑这几条说法（冒烟测试用），不给就八条全跑
args <- commandArgs(trailingOnly = TRUE)
Sys.setlocale("LC_CTYPE", "en_US.UTF-8")
check <- "--check" %in% args
cl <- grep("^--claims=", args, value = TRUE)
only <- if (length(cl)) as.integer(strsplit(sub("^--claims=", "", cl[1]), ",")[[1]]) else integer(0)
pos <- args[!startsWith(args, "--")]
fa <- grep("^--file=", commandArgs(FALSE), value = TRUE)
HERE <- if (length(fa)) dirname(normalizePath(sub("^--file=", "", fa[1]))) else getwd()
src <- if (length(pos) > 0) pos[1] else file.path(HERE, "data", "q22_long_ascii.csv")
out <- if (length(pos) > 1) pos[2] else dirname(src)
# knitr 渲染时会把工作目录切到 Rmd 所在目录，相对路径会失效，这里先转成绝对路径
src <- normalizePath(src, winslash = "/")
out <- normalizePath(out, winslash = "/", mustWork = FALSE)
dir.create(out, showWarnings = FALSE, recursive = TRUE)
cat(sprintf("Rmd  %s\n输入 %s\n输出 %s\n", file.path(HERE, "092601_regression.Rmd"), src, out))
rmarkdown::render(file.path(HERE, "092601_regression.Rmd"),
                  output_file = "regression_archive.html", output_dir = out,
                  params = list(src = src, outdir = out,
                                check_only = check, only_claims = only),
                  quiet = TRUE)
cat("done: ", file.path(out, "regression_archive.html"), "\n", sep = "")
