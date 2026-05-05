#!/usr/bin/env Rscript
# run_plots.R — generate plot PNGs for a taxa-mapping run.
# Called by run.py when --plots is set.
# Usage: Rscript plot_r/run_plots.R <run_dir>

suppressPackageStartupMessages({
  library(tidyr)
  library(dplyr)
  library(ggplot2)
  library(patchwork)
  library(scales)
  library(forcats)
  library(stringr)
})

# ── Locate this script's directory (works both from Rscript and source()) ──────
initial_args <- commandArgs(trailingOnly = FALSE)
file_flag    <- grep("--file=", initial_args, value = TRUE)
if (length(file_flag) > 0) {
  script_dir <- dirname(normalizePath(sub("--file=", "", file_flag[1])))
} else {
  script_dir <- getwd()
}

source(file.path(script_dir, "auxiliary_functions.R"))

# ── Parse run_dir argument ─────────────────────────────────────────────────────
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) stop("Usage: Rscript run_plots.R <run_dir>")
run_dir <- normalizePath(args[1], mustWork = TRUE)

mapping_csv <- file.path(run_dir, "results", "final_mapping.csv")
if (!file.exists(mapping_csv)) {
  stop("final_mapping.csv not found: ", mapping_csv)
}

df <- readr::read_csv(mapping_csv, show_col_types = FALSE)
message("Loaded ", nrow(df), " rows from ", mapping_csv)

plots_dir <- file.path(run_dir, "plots")
dir.create(plots_dir, recursive = TRUE, showWarnings = FALSE)

# ── Panel A — Mapping quality landscape ──────────────────────────── (disabled)
# tryCatch({
#   pA <- plot_mapping_landscape(df)
#   ggsave(
#     filename = file.path(plots_dir, "panel_A_landscape.png"),
#     plot     = pA,
#     width    = 8, height = 6, dpi = 150, bg = "white"
#   )
#   message("Panel A saved: panel_A_landscape.png")
# }, error = function(e) {
#   message("Panel A FAILED: ", conditionMessage(e))
# })

# ── Panel B — Score × Tie-Bin heatmap ────────────────────────────── (disabled)
# tryCatch({
#   pB <- plot_score_tie_heatmap(df)
#   ggsave(
#     filename = file.path(plots_dir, "panel_B_heatmap.png"),
#     plot     = pB,
#     width    = 7, height = 4.5, dpi = 150, bg = "white"
#   )
#   message("Panel B saved: panel_B_heatmap.png")
# }, error = function(e) {
#   message("Panel B FAILED: ", conditionMessage(e))
# })

# ── Panel C — Sankey flow (networkD3 → PNG via webshot2) ──────────────────────
if (requireNamespace("networkD3", quietly = TRUE) &&
    requireNamespace("webshot2",  quietly = TRUE)) {
  tryCatch({
    out_png <- file.path(plots_dir, "panel_C_sankey.png")
    result  <- plot_mapping_sankey(df, output_png = out_png)
    if (!is.null(result)) message("Panel C saved: panel_C_sankey.png")
  }, error = function(e) {
    message("Panel C FAILED: ", conditionMessage(e))
  })
} else {
  message("Panel C skipped — run: install.packages(c('networkD3', 'webshot2'))")
}

message("Plots directory: ", plots_dir)
