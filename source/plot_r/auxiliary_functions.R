# =============================================================================
# auxiliary_functions.R
# All helper functions for main-diet-case.R
# =============================================================================

# ── 1.  General utilities ─────────────────────────────────────────────────────

clean_name <- function(x) {
  x %>%
    str_replace_all("\\[|\\]", "") %>%
    str_replace_all("_", " ") %>%
    str_squish()
}

extract_genus <- function(x) {
  stringr::str_extract(x, "^[A-Za-z]+")
}

# Filters out pairwise comparisons where both groups have zero variance,
# preventing crashes in stat_compare_means() / stat_signif().
safe_comparisons <- function(df, var = "relative_abundance_log", group = "Diet") {
  pairs <- list(
    c("Omnivorous", "Vegetarian"),
    c("Omnivorous", "Vegan"),
    c("Vegetarian", "Vegan")
  )
  Filter(function(p) {
    g1 <- df[[var]][df[[group]] == p[1]]
    g2 <- df[[var]][df[[group]] == p[2]]
    isTRUE(sd(g1, na.rm = TRUE) > 0) || isTRUE(sd(g2, na.rm = TRUE) > 0)
  }, pairs)
}

# ── 2.  Mapping data utilities ────────────────────────────────────────────────

# Coerce CSV-loaded mapping df to correct types.
# Python writes booleans as "True"/"False"; numeric columns need explicit cast.
coerce_mapping_types <- function(df) {
  df %>%
    mutate(
      j_score        = as.numeric(j_score),
      n_candidates   = as.integer(n_candidates),
      top_score      = as.numeric(top_score),
      n_top_ties     = as.integer(n_top_ties),
      n_100s         = as.numeric(n_100s),
      has_code_or_cc = as.integer(has_code_or_cc),
      anchor_tokens  = as.integer(anchor_tokens),
      has_gs         = tolower(has_gs)       == "true",
      is_not_found   = tolower(is_not_found) == "true"
    )
}

# Add input_type label column derived from taxon name characteristics.
classify_input_type <- function(df) {
  df %>%
    mutate(
      input_type = case_when(
        has_code_or_cc == 1L                              ~ "CAG / unculture",
        str_detect(taxa_name, "(?i)\\bbacterium\\b") &
          has_code_or_cc == 0L                            ~ "Higher-rank label",
        j_score == 0                                      ~ "Absent from reference",
        TRUE                                              ~ "Canonical binomial"
      ),
      input_type = factor(input_type,
                          levels = c("Canonical binomial", "CAG / unculture",
                                     "Higher-rank label",  "Absent from reference"))
    )
}

# ── 3.  Shared colour palettes ────────────────────────────────────────────────

BAND_FINAL_COLOURS <- c(
  "green"        = "#1B5E20",
  "yellow_green" = "#8BC34A",
  "yellow"       = "#F9A825",
  "red"          = "#C62828",
  "black"        = "#212121"
)

BAND_JACCARD_COLOURS <- c(
  "auto-accept" = "#1B5E20",
  "grey-zone"   = "#F57F17",
  "flag"        = "#E64A19",
  "not-accept"  = "#B71C1C"
)

INPUT_TYPE_COLOURS <- c(
  "Canonical binomial"    = "#37474F",
  "CAG / unculture"       = "#78909C",
  "Higher-rank label"     = "#90A4AE",
  "Absent from reference" = "#B0BEC5"
)

BAND_FINAL_ORDER  <- c("green", "yellow_green", "yellow", "red", "black")

BAND_FINAL_LABELS <- c(
  "green"        = "Green — unambiguous",
  "yellow_green" = "Yellow-green — high similarity",
  "yellow"       = "Yellow — multi-strain tie",
  "red"          = "Red — low similarity",
  "black"        = "Black — no correspondence"
)

# ── 4.  Panel A: Mapping quality landscape ────────────────────────────────────

plot_mapping_landscape <- function(df, title = "Mapping quality landscape") {
  df <- coerce_mapping_types(df) %>%
    mutate(taxa_name = forcats::fct_reorder(taxa_name, j_score))

  # top marginal: Jaccard score distribution
  p_top <- ggplot(df, aes(x = j_score, fill = bands)) +
    geom_histogram(binwidth = 0.05, colour = "white", linewidth = 0.25) +
    scale_fill_manual(values = BAND_JACCARD_COLOURS, guide = "none") +
    scale_x_continuous(limits = c(-0.05, 1.05), expand = c(0, 0)) +
    labs(x = NULL, y = "n") +
    theme_bw(base_size = 9) +
    theme(
      axis.text.x      = element_blank(),
      axis.ticks.x     = element_blank(),
      panel.grid.minor = element_blank()
    )

  # main scatter: taxon × j_score coloured by Jaccard tier
  p_main <- ggplot(df, aes(x = j_score, y = taxa_name, colour = bands)) +
    annotate("rect", xmin =   0, xmax = 1/3, ymin = -Inf, ymax = Inf,
             fill = "#FFEBEE", alpha = 0.35) +
    annotate("rect", xmin = 1/3, xmax = 2/3, ymin = -Inf, ymax = Inf,
             fill = "#FFFDE7", alpha = 0.35) +
    annotate("rect", xmin = 2/3, xmax =   1, ymin = -Inf, ymax = Inf,
             fill = "#E8F5E9", alpha = 0.35) +
    geom_vline(xintercept = c(1/3, 2/3),
               linetype = "dashed", colour = "grey55", linewidth = 0.35) +
    geom_point(aes(shape = has_gs), size = 2.8, alpha = 0.9) +
    scale_colour_manual(values = BAND_JACCARD_COLOURS, name = "Jaccard tier") +
    scale_shape_manual(
      values = c("TRUE" = 16, "FALSE" = 1),
      labels = c("TRUE" = "genus + species in DB", "FALSE" = "genus absent"),
      name   = NULL
    ) +
    scale_x_continuous(limits  = c(-0.05, 1.05),
                       breaks  = seq(0, 1, 0.25),
                       labels  = c("0", "0.25", "0.50", "0.75", "1.00")) +
    labs(x = "Jaccard similarity (LF)", y = NULL) +
    theme_bw(base_size = 9) +
    theme(
      axis.text.y      = element_text(size = 7, face = "italic"),
      axis.text.x      = element_text(size = 8),
      panel.grid.minor = element_blank(),
      legend.position  = "bottom",
      legend.text      = element_text(size = 7),
      legend.key.size  = unit(0.35, "cm")
    )

  # right sidebar: candidate count (log scale)
  p_right <- ggplot(df, aes(x = n_candidates, y = taxa_name)) +
    geom_col(fill = "grey55", width = 0.6) +
    scale_x_log10(labels = scales::label_comma(),
                  breaks = c(1, 10, 100, 1000, 10000)) +
    labs(x = "Candidates (log₁₀)", y = NULL) +
    theme_bw(base_size = 9) +
    theme(
      axis.text.y      = element_blank(),
      axis.ticks.y     = element_blank(),
      axis.text.x      = element_text(size = 7, angle = 30, hjust = 1),
      panel.grid.minor = element_blank()
    )

  patchwork::wrap_plots(
    p_top,  patchwork::plot_spacer(),
    p_main, p_right,
    ncol    = 2,
    widths  = c(5, 1.4),
    heights = c(1, 4)
  ) +
    patchwork::plot_annotation(
      title = title,
      theme = theme(plot.title = element_text(size = 10, face = "bold"))
    )
}

# ── 5.  Panel B: Score × Tie-Bin heatmap ─────────────────────────────────────

plot_score_tie_heatmap <- function(df,
                                    title = "Score × Tie-Bin Frequency by Tier") {
  df <- coerce_mapping_types(df)
  rescued <- df %>% filter(!is_not_found)

  if (nrow(rescued) == 0) {
    return(
      ggplot() +
        annotate("text", x = 0.5, y = 0.5,
                 label = "No rescued taxa in this run", size = 4.5, colour = "grey40") +
        theme_void() + labs(title = title)
    )
  }

  rescued <- rescued %>%
    mutate(
      tie_bin = cut(
        n_top_ties,
        breaks = c(0, 1, 3, 7, 15, 31, 63, Inf),
        labels = c("1", "2–3", "4–7", "8–15",
                   "16–31", "32–63", "≥64"),
        right  = TRUE
      ),
      score_bin  = factor(round(top_score / 25) * 25),
      final_band = factor(final_band, levels = BAND_FINAL_ORDER)
    )

  tiles <- rescued %>%
    count(score_bin, tie_bin, final_band, .drop = FALSE) %>%
    filter(!is.na(score_bin), !is.na(tie_bin))

  ggplot(tiles, aes(x = score_bin, y = tie_bin, fill = final_band)) +
    geom_tile(colour = "white", linewidth = 0.6) +
    geom_text(aes(label = ifelse(n > 0, as.character(n), "")),
              size = 3.8, colour = "white", fontface = "bold") +
    scale_fill_manual(
      values = BAND_FINAL_COLOURS,
      labels = BAND_FINAL_LABELS,
      name   = "Final tier",
      drop   = FALSE
    ) +
    labs(x = "Rescue score", y = "Tie-bin (n top candidates)", title = title) +
    theme_bw(base_size = 9) +
    theme(
      panel.grid      = element_blank(),
      legend.position = "right",
      legend.text     = element_text(size = 7),
      legend.key.size = unit(0.4, "cm")
    )
}

# ── 6.  Panel C: Alluvial / Sankey flow diagram ───────────────────────────────

plot_mapping_sankey <- function(df,
                                 title = "Mapping flow: label type → Jaccard tier → final band") {
  if (!requireNamespace("ggalluvial", quietly = TRUE)) {
    message("'ggalluvial' not installed — skipping Sankey panel. ",
            "Run: install.packages('ggalluvial')")
    return(invisible(NULL))
  }

  df <- coerce_mapping_types(df) %>%
    classify_input_type() %>%
    mutate(
      Jaccard = factor(bands,      levels = c("auto-accept", "grey-zone",
                                              "flag",        "not-accept")),
      Final   = factor(final_band, levels = BAND_FINAL_ORDER)
    )

  alluv <- df %>%
    count(input_type, Jaccard, Final, name = "freq")

  all_col <- c(INPUT_TYPE_COLOURS, BAND_JACCARD_COLOURS, BAND_FINAL_COLOURS)

  ggplot(alluv,
         aes(y = freq, axis1 = input_type, axis2 = Jaccard, axis3 = Final)) +
    ggalluvial::geom_alluvium(
      aes(fill = Final),
      width    = 1/5, alpha = 0.65, knot.pos = 0.4
    ) +
    ggalluvial::geom_stratum(
      fill = "grey25", colour = "white", width = 1/5, linewidth = 0.4
    ) +
    geom_text(
      stat  = ggalluvial::StatStratum,
      aes(label = after_stat(stratum)),
      size  = 2.6, colour = "white", fontface = "bold"
    ) +
    scale_x_discrete(
      limits = c("Input type", "Jaccard tier", "Final band"),
      expand = c(0.08, 0.08)
    ) +
    scale_fill_manual(values = BAND_FINAL_COLOURS, guide = "none") +
    labs(x = NULL, y = "Number of taxa", title = title) +
    theme_minimal(base_size = 9) +
    theme(
      axis.text.x  = element_text(face = "bold", size = 9),
      axis.text.y  = element_blank(),
      panel.grid   = element_blank()
    )
}

# ── 7.  Panel D: DIABLO vs MetaPhlAn comparison ──────────────────────────────

plot_mapping_comparison <- function(comparison_df,
                                     title = "DIABLO name vs MetaPhlAn name: mapping tier") {
  df <- comparison_df %>%
    filter(!is.na(metaphlan_name)) %>%
    mutate(
      diablo_band = factor(diablo_band, levels = BAND_FINAL_ORDER),
      mp_band     = factor(mp_band,     levels = BAND_FINAL_ORDER),
      diablo_int  = as.integer(diablo_band),
      mp_int      = as.integer(coalesce(mp_band, diablo_band)),
      direction   = case_when(
        is.na(mp_band)      ~ "no MetaPhlAn equivalent",
        diablo_int > mp_int ~ "improved",
        diablo_int < mp_int ~ "degraded",
        TRUE                ~ "unchanged"
      ),
      label = if_else(
        name_changed,
        paste0(str_trunc(taxon, 26), "\n→ ", str_trunc(metaphlan_name, 26)),
        str_trunc(taxon, 32)
      ),
      label = forcats::fct_reorder(label, diablo_int)
    )

  df_long <- bind_rows(
    df %>% transmute(label, band = diablo_band, source = "DIABLO name",   direction),
    df %>% transmute(label, band = mp_band,     source = "MetaPhlAn name", direction)
  ) %>%
    filter(!is.na(band))

  seg_df <- df %>%
    filter(band_changed) %>%
    transmute(label, x = diablo_band, xend = mp_band, direction)

  seg_col <- c(improved  = "#1B5E20", degraded = "#B71C1C", unchanged = "grey70",
               "no MetaPhlAn equivalent" = "grey90")

  ggplot() +
    geom_segment(
      data = seg_df,
      aes(x = x, xend = xend, y = label, yend = label, colour = direction),
      linewidth = 0.8, linetype = "dotted"
    ) +
    geom_point(
      data = df_long,
      aes(x = band, y = label, fill = band, shape = source),
      size = 3.2, colour = "white", stroke = 0.35
    ) +
    scale_fill_manual(values  = BAND_FINAL_COLOURS, guide = "none") +
    scale_colour_manual(values = seg_col, name = "Direction of change",
                        guide  = guide_legend(override.aes = list(linewidth = 1.2))) +
    scale_shape_manual(
      values = c("DIABLO name" = 21, "MetaPhlAn name" = 24),
      name   = NULL
    ) +
    scale_x_discrete(
      limits = BAND_FINAL_ORDER, drop = FALSE,
      labels = c("Green", "Yel-Green", "Yellow", "Red", "Black")
    ) +
    labs(x = "Final mapping tier", y = NULL, title = title) +
    theme_bw(base_size = 9) +
    theme(
      axis.text.y     = element_text(size = 6.5, face = "italic"),
      legend.position = "bottom",
      legend.text     = element_text(size = 7),
      legend.key.size = unit(0.35, "cm")
    )
}

# ── 8.  Multi-panel wrapper ───────────────────────────────────────────────────

# Assembles Panels A–D into a single PDF figure.
# Returns the patchwork object invisibly; side-effect is the saved PDF.
save_mapping_panels <- function(final_mapping,
                                 comparison,
                                 output_path,
                                 width  = 16,
                                 height = 14) {
  pA <- plot_mapping_landscape(final_mapping)
  pB <- plot_score_tie_heatmap(final_mapping)
  pC <- plot_mapping_sankey(final_mapping)
  pD <- plot_mapping_comparison(comparison)

  top_row <- pA | pB
  bot_row <- if (!is.null(pC)) pC | pD else pD

  combined <- (top_row / bot_row) +
    patchwork::plot_annotation(
      title    = "MINeBugs taxa-mapping: quality landscape",
      subtitle = paste0(
        nrow(coerce_mapping_types(final_mapping)),
        " input taxa  ·  run date: ", Sys.Date()
      ),
      tag_levels = "A",
      theme = theme(
        plot.title    = element_text(size = 13, face = "bold"),
        plot.subtitle = element_text(size = 9, colour = "grey40"),
        plot.tag      = element_text(size = 11, face = "bold")
      )
    )

  ggsave(output_path, combined,
         width = width, height = height, device = cairo_pdf)
  message("Mapping panels saved to: ", output_path)
  invisible(combined)
}
