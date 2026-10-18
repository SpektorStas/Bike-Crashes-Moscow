# Rscript tests/check_analysis.R [--with-data]
if (dir.exists('.r-library')) .libPaths(c(normalizePath('.r-library'), .libPaths()))
library(data.table)
library(fixest)
library(jsonlite)
source('scripts/spillover_models.R')

# Известное перераспределение: +2 в core, по -1 у двух соседей, суммарно ноль.
stopifnot(identical(spillover_group(c(1, 0, 0, 0, 0), c(3000, 500, 1000, 2000, 2001)),
                  c('core', 'ring_0_500m', 'ring_500_1000m', 'ring_1000_2000m', 'control_gt2000m')))
z <- rbindlist(lapply(1:20, function(i) {
  groups <- c('core', 'near', 'near', 'middle', 'outer', 'control', 'control')
  data.table(hex_id = paste(i, 1:7, sep = '_'), spatial_block = paste0('b', i),
    treated_current = as.integer(groups == 'core'), distance = c(0, 250, 250, 750, 1500, 3000, 3000),
    lon = 37.1 + i * .025 + (1:7) * .001, lat = 55.5 + i * .002,
    delta = 3 + (i %% 5) * .1 + ifelse(groups == 'core', 2, ifelse(groups == 'near', -1, 0)))
}))
z <- add_exposure(z, 'distance')
fit <- fit_ring_fd(z, 2, block_fe = TRUE)
stopifnot(abs(coef(fit)['core'] - 2) < 1e-8, abs(coef(fit)['ring_0_500m'] + 1) < 1e-8)
combined <- neighborhood_contrasts(fit, z, 'fixture', 2)[neighborhood == 'core_plus_500m']
w <- c(core = 20, ring_0_500m = 40)
variance <- drop(t(w) %*% vcov(fit)[names(w), names(w)] %*% w)
stopifnot(abs(combined$estimate) < 1e-7, abs(combined$se^2 - variance) < 1e-8)

cat('PASS: known displacement and full covariance.\n')
if (!'--with-data' %in% commandArgs(trailingOnly = TRUE)) quit(status = 0)

meta <- fromJSON('outputs/metadata.json')
d <- fread('outputs/hex_panel.csv')
p <- d[year %in% c(meta$pre_year, meta$post_year)]
p[, `:=`(treated = treated_current, post = as.integer(year == meta$post_year))]
p[, did := treated * post]
results <- fread('outputs/final/models.csv')
models <- readRDS('outputs/final/models.rds')
wide <- fread('outputs/final/first_differences.csv')
stopifnot(!anyDuplicated(results$id), !anyDuplicated(wide$hex_id),
          all(results$ci_low <= results$estimate), all(results$estimate <= results$ci_high),
          all(is.finite(results$estimate)), all(results$p_value >= 0 & results$p_value <= 1),
          all(p[post == 1, year] == meta$post_year), all(p[post == 0, year] == meta$pre_year))

# Независимая ручная формула и эквивалентность DiD/FD.
means <- p[, .(y = mean(bike_crashes)), by = .(treated, post)]
manual <- means[treated == 1 & post == 1, y] - means[treated == 1 & post == 0, y] -
          means[treated == 0 & post == 1, y] + means[treated == 0 & post == 0, y]
stopifnot(abs(results[id == 'fd_global', estimate] - manual) < 1e-10)
fe <- feols(bike_crashes ~ did | hex_id + year, data = p, notes = FALSE)
stopifnot(abs(coef(fe)['did'] - manual) < 1e-10)
common <- wide[, .(both = uniqueN(treated) == 2), by = spatial_block][both == TRUE, spatial_block]
fe_local <- feols(bike_crashes ~ did | hex_id + spatial_block^year,
                  data = p[spatial_block %in% common], notes = FALSE)
stopifnot(abs(coef(fe_local)['did'] - results[id == 'fd_local', estimate]) < 1e-10)

# Шкала PPML сверяется с ручным отношением отношений, а n_hex — с реально использованными строками.
totals <- p[, .(y = sum(bike_crashes)), by = .(treated, post)]
ratio <- (totals[treated == 1 & post == 1, y] / totals[treated == 1 & post == 0, y]) /
         (totals[treated == 0 & post == 1, y] / totals[treated == 0 & post == 0, y])
stopifnot(abs(results[id == 'ppml_global', estimate] - 100 * (ratio - 1)) < 1e-7)
for (model_id in c('ppml_global', 'ppml_local')) {
  input <- if (model_id == 'ppml_global') p else p[spatial_block %in% common]
  used <- input[obs(models[[model_id]])]
  row <- results[id == model_id]
  stopifnot(row$n_hex == uniqueN(used$hex_id), row$n_obs == nrow(used),
            row$n_hex < row$n_input_hex,
            abs(row$estimate - 100 * expm1(coef(models[[model_id]])['did'])) < 1e-8)
}

# Неполные годы не отображаются как полноценные годовые числа; суммы не теряют нули.
trends <- fread('outputs/final/trends.csv')
valid_years <- d[, .(complete = all(months_observed == length(meta$months))), by = year][complete == TRUE, year]
stopifnot(setequal(trends$year, valid_years))
group_means <- fread('outputs/final/group_means.csv')
stopifnot(sum(group_means[sample == 'all_hex', crashes]) == sum(p$bike_crashes),
          all(group_means[sample == 'all_hex', .(n = sum(n_hex)), by = year]$n == nrow(wide)))

# Реальные пространственные группы непересекающиеся; exported total использует ту же ковариацию.
spatial <- fread('outputs/final/spillover_sample.csv')
stopifnot(!anyDuplicated(spatial$hex_id), setequal(spatial$hex_id, wide$hex_id))
sizes <- table(spatial[in_common_blocks == TRUE, spatial_group])
weights <- setNames(as.numeric(sizes[c('core', 'ring_0_500m')]), c('core', 'ring_0_500m'))
combined <- linear_contrast(models$spillover_local_core, weights)
stopifnot(abs(combined$estimate - results[id == 'spillover_total_500', estimate]) < 1e-8,
          abs(combined$ci_low - results[id == 'spillover_total_500', ci_low]) < 1e-8)
rings <- fread('outputs/final/spillovers.csv')
stopifnot(all(rings$p_holm_within_model >= rings$p_value))
notes <- paste(readLines('outputs/final/analysis_notes.json', encoding = 'UTF-8'), collapse = '\n')
stopifnot(!grepl('<d0>|<d1>', notes), validate(notes))
cat('PASS: endpoint sample, manual DiD, FD/FE equivalence, PPML scale/support, complete years, known displacement, full covariance and UTF-8.\n')
