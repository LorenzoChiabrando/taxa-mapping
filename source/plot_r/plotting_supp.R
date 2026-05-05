
library(tidyr)
library(dplyr)
library(ggplot2)
library(patchwork)
library(scales)
library(tidyverse)

if (!exists("PLOTTING_SUPP_INPUT_DIR")) {
  PLOTTING_SUPP_INPUT_DIR <- file.path(getwd(), "inputs")
}
if (!exists("PLOTTING_SUPP_REF_DIR")) {
  PLOTTING_SUPP_REF_DIR <- file.path(getwd(), "refs")
}
if (!exists("PLOTTING_SUPP_FIGURE_DIR")) {
  PLOTTING_SUPP_FIGURE_DIR <- file.path(getwd(), "figures")
}

list_csv   <- file.path(PLOTTING_SUPP_INPUT_DIR, "taxa_input.csv")
map_csv    <- file.path(PLOTTING_SUPP_INPUT_DIR, "jaccard_mapping.csv")
subset_csv <- file.path(PLOTTING_SUPP_INPUT_DIR, "jaccard_subset_for_validation.csv")
rescue_csv <- file.path(PLOTTING_SUPP_INPUT_DIR, "ncbi_rescue_suggestions.csv")
models_csv <- file.path(PLOTTING_SUPP_REF_DIR,   "mat_files_list.csv")
fig_dir    <- PLOTTING_SUPP_FIGURE_DIR

agora_models <- readr::read_csv(models_csv, show_col_types = FALSE)

dir.create(fig_dir, recursive = TRUE, showWarnings = FALSE)

user_taxa = readr::read_csv(
  file.path(list_csv), 
  show_col_types = FALSE)  %>%
  mutate(taxon = taxa_name %>%
           stringr::str_replace("^\\[([^\\]]+)\\]", "\\1") %>%
           stringr::str_replace_all("(?<=\\b[A-Za-z]{1,4})-([0-9]+)\\b", " \\1") %>%
           stringr::str_replace_all("[,;]+", "") %>%
           stringr::str_squish()) %>%
  select(taxon)

res_jaccard = readr::read_csv(file.path(map_csv), show_col_types = FALSE)

ncbi_rescue = readr::read_csv(
  file.path(rescue_csv),
  show_col_types = FALSE) %>%
  mutate(
    top_score = as.numeric(top_score),
    n_top_ties = as.integer(n_top_ties),
    final_color = factor(
      final_color, 
      levels = c("black", "red", "yellow", "yellow_green",  "green"))
  )

# ncbi_rescue %>% count(final_color) %>%
#   mutate(pct = scales::percent(n / sum(n))) %>%
#   arrange(match(final_color, levels(ncbi_rescue$final_color))) %>%
#   print()

links_list <- list()

phase1 <- res_jaccard %>%
  count(bands, name = "value") %>%
  mutate(
    source = "All Taxa",
    target = bands
  ) %>%
  select(source, target, value)

links_list[[1]] <- phase1

auto_accept_flow <- data.frame(
  source = "auto-accept",
  target = "green",
  value = sum(res_jaccard$bands == "auto-accept")
)
links_list[[2]] <- auto_accept_flow

non_auto_flow <- res_jaccard %>%
  filter(bands != "auto-accept") %>%
  inner_join(ncbi_rescue %>% select(taxon, final_color), by = "taxon") %>%
  count(bands, final_color, name = "value") %>%
  mutate(
    source = bands,
    target = as.character(final_color)
  ) %>%
  select(source, target, value)

links_list[[3]] <- non_auto_flow

links <- bind_rows(links_list)

nodes <- data.frame(
  name = c(
    "All Taxa",
    "auto-accept", "grey-zone", "flag", "not-accept",
    "green", "yellow_green", "yellow", "red", "black"
  ),
  group = c(
    "input",
    "auto-accept", "grey-zone", "flag", "not-accept",
    "green", "yellow_green", "yellow", "red", "black"
  )
)

# Drop zero-value links (e.g. auto-accept→green when no taxa are auto-accepted)
# and trim nodes to only those that appear in actual flows.
links <- links %>% filter(!is.na(source), !is.na(target), value > 0)

used_nodes <- unique(c(links$source, links$target))
nodes      <- nodes %>% filter(name %in% used_nodes)

links$IDsource <- match(links$source, nodes$name) - 1
links$IDtarget <- match(links$target, nodes$name) - 1
links <- links %>% filter(!is.na(IDsource) & !is.na(IDtarget))

color_scale <- 'd3.scaleOrdinal()
  .domain(["input", "auto-accept", "grey-zone", "flag", "not-accept",
           "green", "yellow_green", "yellow", "red", "black"])
  .range(["#17a2b8", "#28a745", "#6c757d", "#ffc107", "#DC143C",
          "#28a745", "#9ACD32", "#ffc107", "#DC143C", "black"]);'

sankey <- networkD3::sankeyNetwork(
  Links = links,
  Nodes = nodes,
  Source = "IDsource",
  Target = "IDtarget",
  Value = "value",
  NodeID = "name",
  NodeGroup = "group",
  fontSize = 13,
  nodeWidth = 10,
  nodePadding = 36,
  sinksRight = TRUE,
  iterations = 0,
  colourScale = networkD3::JS(color_scale),
  height = 350,
  width = 750
)

htmlwidgets::saveWidget(sankey, file.path(fig_dir, "sankey_mapping.html"), selfcontained = TRUE)

webshot2::webshot(file.path(fig_dir, "sankey_mapping.html"), 
                  file.path(fig_dir, "sankey_mapping.pdf"), 
                  vwidth = 1200, vheight = 800)

band_colors <- c(
  "auto-accept" = "#28a745",
  "grey-zone" = "#6c757d",
  "flag" = "#ffc107",
  "not-accept" = "#DC143C"
)

# Prepare data with binned n_candidates
res_plot <- res_jaccard %>%
  mutate(
    bands = factor(bands, levels = names(band_colors)),
    n_candidates_bin = cut(
      n_candidates,
      breaks = c(0, 1, 2, 5, 10, 50, 100, 500, 1000, Inf),
      labels = c("1", "2", "3-5", "6-10", "11-50", "51-100", "101-500", "501-1000", ">1000"),
      right = TRUE
    )
  ) %>%
  filter(!is.na(j_score), !is.na(n_candidates_bin))

# Main scatter plot with jittered y-axis for discrete bins
p_scatter <- ggplot(res_plot, aes(x = j_score, y = n_candidates_bin, color = bands)) +
  geom_jitter(alpha = 0.7, size = 0.75, height = 0.25, width = 0) +
  scale_color_manual(values = band_colors) +
  labs(
    x = "Jaccard similarity (J*)",
    y = "Candidate multiplicity",
    color = "Assignment band",
    title = "Mapping quality landscape",
    subtitle = paste0("Similarity scores", " (n = ", length(res_jaccard$taxa_name), ")")
  ) +
  theme_minimal(base_size = 11) +
  theme(
    plot.title = element_text(face = "bold", size = 13),
    plot.subtitle = element_text(color = "grey40", size = 10),
    legend.position = "none",
    panel.grid.minor = element_blank(),
    panel.grid.major.y = element_line(linetype = "dotted", color = "grey80"),
    axis.text.y = element_text(face = "bold")
  )

# Marginal density for j_score (top)
p_j_margin <- ggplot(res_plot, aes(x = j_score, fill = bands)) +
  geom_density(alpha = 0.6, color = NA) +
  scale_fill_manual(values = band_colors) +
  theme_void() +
  theme(legend.position = "none")

# Marginal bar chart for n_candidates_bin (right) with x-axis
p_n_margin <- ggplot(res_plot, aes(y = n_candidates_bin, fill = bands)) +
  geom_bar(alpha = 0.7, color = "white", linewidth = 0.2, position = "stack") +
  scale_fill_manual(values = band_colors) +
  scale_x_continuous(
    expand = expansion(mult = c(0, 0.05)),
    position = "bottom"
  ) +
  labs(x = "Count") +
  theme_minimal(base_size = 9) +
  theme(
    legend.position = "none",
    axis.title.y = element_blank(),
    axis.text.y = element_blank(),
    axis.ticks.y = element_blank(),
    panel.grid = element_blank(),
    plot.margin = margin(0, 5, 0, 2, "pt")
  )

# Combine with patchwork
panel_a <- p_j_margin + plot_spacer() + p_scatter + p_n_margin +
  plot_layout(
    ncol = 2, nrow = 2,
    widths = c(4, 1),
    heights = c(1, 4)
  )

ggsave(
  filename = file.path(fig_dir, "panel_A_jaccard_dist.pdf"),
  plot = panel_a,
  width = 5.5,
  height = 4,
  units = "in",
  device = cairo_pdf
)

color_palette <- c(
  "green"        = "#28a745",
  "yellow_green" = "#9ACD32",
  "yellow"       = "#ffc107",
  "red"          = "#DC143C",
  "black"        = "#1a1a1a"
)

# Factor ordering (confidence descending: green → yellow_green → yellow → red → black)
ncbi_rescue <- ncbi_rescue %>%
  mutate(
    final_color = factor(final_color, 
                         levels = c("green", "yellow_green", "yellow", "red", "black")),
    top_score = factor(top_score, levels = c(100, 75, 70, 60, 20, 0))
  )

# Compute sample sizes per tier
tier_counts <- ncbi_rescue %>%
  count(final_color, name = "tier_n")

# Create binned data with tier labels
heatmap_data <- ncbi_rescue %>%
  mutate(
    ties_bin = case_when(
      is.na(n_top_ties)        ~ NA_character_, # true missing
      n_top_ties == 0L         ~ "0",
      TRUE ~ as.character(cut(
        n_top_ties,
        breaks = c(0, 1, 2, 5, 10, 50, 100, 500, 1000, Inf),
        labels = c("1", "2", "3-5", "6-10", "11-50",
                   "51-100", "101-500", "501-1000", ">1000"),
        right = TRUE
      ))
    ),
    ties_bin = factor(
      ties_bin,
      levels = c("0", "1", "2", "3-5", "6-10", "11-50",
                 "51-100", "101-500", "501-1000", ">1000")
    )
  ) %>%
  left_join(tier_counts, by = "final_color") %>%
  mutate(
    tier_label = paste0(final_color, "\n(n = ", tier_n, ")"),
    tier_label = forcats::fct_reorder(tier_label, as.numeric(final_color))
  ) %>%
  count(final_color, tier_label, top_score, ties_bin) %>%
  complete(nesting(final_color, tier_label), top_score, ties_bin, fill = list(n = 0))

heatmap_data <- heatmap_data %>%
  group_by(final_color) %>%
  mutate(
    n_max = max(n),
    intensity = ifelse(n_max > 0, n / n_max, 0)
  ) %>%
  ungroup()

p <- heatmap_data %>%
  ggplot(aes(x = top_score, y = ties_bin)) +
  geom_tile(aes(fill = final_color, alpha = intensity), color = "white", linewidth = 0.3) +
  geom_text(aes(label = ifelse(n > 0, n, ""), 
                color = ifelse(final_color == "black" & intensity > 0.5, "white", "black")), 
            size = 1.25, show.legend = FALSE) +
  scale_fill_manual(values = color_palette, guide = "none") +
  scale_color_identity() +
  scale_alpha_continuous(range = c(0.1, 1), guide = "none") +
  facet_wrap(~ tier_label, nrow = 1) +
  labs(
    title = "Score × Tie-Bin Frequency by Tier",
    x = "Rescue Score",
    y = expression(n[top_ties] ~ "(binned)")
  ) +
  theme_minimal(base_size = 9) +
  theme(
    axis.text.x = element_text(angle = 45, hjust = 1, size = 5),
    panel.grid = element_blank(),
    strip.text = element_text(face = "bold", size = 5),
    strip.background = element_rect(fill = "grey95", color = NA)
  )

# Define palette (aligned with your tier colors)
rank_colors <- c(
  "strain" = "#2BB673",   # Green (high precision)
  "species" = "#F4B400",  # Yellow
  "genus" = "#FF9800",    # Orange
  "family" = "#DB4437"    # Red (low precision)
)

ggsave(
  filename = file.path(fig_dir, "panel_B_NCBI_dist.pdf"),
  plot = p,
  width = 4.5,
  height = 4,
  units = "in",
  device = cairo_pdf
)
