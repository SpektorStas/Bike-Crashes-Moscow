# Этот файл запускается из analysis.R; использует те же годы, исход и экспорт моделей.
# Непересекающиеся группы исключают двойной счет ДТП.
exposure <- fread('outputs/spillover_exposure.csv')
stopifnot(!anyDuplicated(exposure$hex_id), setequal(exposure$hex_id, wide$hex_id))
check <- merge(unique(p[, .(hex_id, treated_current)]), exposure, by = 'hex_id')
stopifnot(all(check$treated_current.x == check$treated_current.y))

spatial <- merge(wide, exposure[, .(hex_id, distance_hex_edge_m, distance_hex_center_m)], by = 'hex_id')
spatial[, treated_current := treated]
spatial <- add_exposure(spatial, 'distance_hex_edge_m')
blocks_spatial <- spatial[, .(remote = any(spatial_group == 'control_gt2000m'),
  exposed = any(spatial_group != 'control_gt2000m')), by = spatial_block]
local_spatial <- spatial[spatial_block %in% blocks_spatial[remote & exposed, spatial_block]]
stopifnot(uniqueN(local_spatial$spatial_block) >= 10)

# Две модели: весь город и общие блоки с удаленным контролем >2 км.
# core имеет >=10 м велодорожки. Остальные группы определяются расстоянием от края hex.
ring_global <- fit_ring_fd(spatial, cutoff_km = 2)
ring_local <- fit_ring_fd(local_spatial, cutoff_km = 2, block_fe = TRUE)
ring_labels <- c(core = 'Ячейки с велодорожками', ring_0_500m = 'Соседи: 0–500 м',
                 ring_500_1000m = 'Соседи: 500–1000 м', ring_1000_2000m = 'Соседи: 1000–2000 м')
ring_results <- list()
ring_totals <- list()
for (scope in c('global', 'local')) {
  fit <- if (scope == 'global') ring_global else ring_local
  sample_data <- if (scope == 'global') spatial else local_spatial
  sample_name <- if (scope == 'global') 'all_hex_remote_control' else 'common_blocks_remote_control'
  for (term in spillover_terms) {
    id <- paste0('spillover_', scope, '_', term)
    add_model(id, paste0(ring_labels[[term]], if (scope == 'local') ': локально' else ': весь город'),
              fit, sample_data, term, 'crashes_per_hex', sample_name, 'Conley, 2 км',
              'Контроль дальше 2 км. Расстояние от края ячейки, не по дорожному графу.',
              primary = scope == 'local', family = 'spillover')
  }
  estimates <- ring_estimates(fit, 'distance_hex_edge_m', 2)
  for (term in spillover_terms) {
    rows[[paste0('spillover_', scope, '_', term)]][,
      p_holm_within_model := estimates[group == term, p_holm_within_model]]
  }
  estimates[, `:=`(scope = scope, sample = sample_name, n_hex = nrow(sample_data))]
  ring_results[[scope]] <- estimates
  totals <- neighborhood_contrasts(fit, sample_data, 'distance_hex_edge_m', 2)
  totals[, p_holm_across_radii := p.adjust(p_value, method = 'holm')]
  totals[, `:=`(scope = scope, sample = sample_name, n_hex = nrow(sample_data))]
  ring_totals[[scope]] <- totals
}

# Суммарное изменение для дорожки и окружения трёх радиусов.
for (radius in c(500, 1000, 2000)) {
  total <- ring_totals$local[neighborhood == paste0('core_plus_', radius, 'm')]
  id <- paste0('spillover_total_', radius)
  rows[[id]] <- data.table(id, label = paste0('Велодорожки + окружение ', radius, ' м'),
    outcome = 'bike_crashes', scale = 'excess_crashes_total',
    estimate = total$estimate, ci_low = total$ci_low, ci_high = total$ci_high,
    p_value = total$p_value, p_holm_across_radii = total$p_holm_across_radii,
    n_obs = nobs(ring_local), n_hex = nrow(local_spatial),
    n_exposed_hex = total$exposed_cells, n_blocks = uniqueN(local_spatial$spatial_block),
    n_input_hex = nrow(local_spatial), formula = 'sum(N_group * beta_group)',
    sample = 'common_blocks_remote_control', se_method = 'Conley, 2 км; полная ковариация',
    notes = 'Сумма для данной выборки; размер может меняться. n_hex — вся выборка модели, n_exposed_hex — ячейки суммы.',
    family = 'neighborhood', term = total$neighborhood, primary = TRUE,
    raw_estimate = total$estimate, raw_ci_low = total$ci_low, raw_ci_high = total$ci_high)
  models[[id]] <- ring_local
}

# Дополнительная спецификация: расстояние от центра вместо края ячейки.
# Она меняет и группы, и набор общих блоков; не является независимым подтверждением.
center <- add_exposure(spatial, 'distance_hex_center_m')
center_blocks <- center[, .(remote = any(spatial_group == 'control_gt2000m'),
                            exposed = any(spatial_group != 'control_gt2000m')), by = spatial_block]
center <- center[spatial_block %in% center_blocks[remote & exposed, spatial_block]]
ring_center <- fit_ring_fd(center, cutoff_km = 2, block_fe = TRUE)
for (term in spillover_terms) {
  add_model(paste0('spillover_center_', term), paste0(ring_labels[[term]], ': от центра'),
            ring_center, center, term, 'crashes_per_hex', 'common_blocks_center_distance', 'Conley, 2 км',
            'Расстояние от центра; состав колец и общих блоков меняется.',
            primary = FALSE, family = 'spillover')
}
center_estimates <- ring_estimates(ring_center, 'distance_hex_center_m', 2)
for (term in spillover_terms) {
  rows[[paste0('spillover_center_', term)]][,
    p_holm_within_model := center_estimates[group == term, p_holm_within_model]]
}
center_estimates[, `:=`(scope = 'local_center', sample = 'common_blocks_center_distance', n_hex = nrow(center))]
ring_results$local_center <- center_estimates
center_totals <- neighborhood_contrasts(ring_center, center, 'distance_hex_center_m', 2)
center_totals[, p_holm_across_radii := p.adjust(p_value, method = 'holm')]
center_totals[, `:=`(scope = 'local_center', sample = 'common_blocks_center_distance', n_hex = nrow(center))]
ring_totals$local_center <- center_totals

# Сумма эффектов = N_core*beta_core + N_ring*beta_ring. CI использует полную ковариацию.
# Это модельная сумма отклонений от контрфактических изменений, не сырая разность ДТП.
fwrite(rbindlist(ring_results), file.path(OUT, 'spillovers.csv'))
fwrite(rbindlist(ring_totals), file.path(OUT, 'spillover_totals.csv'))
spatial_panel <- merge(p, spatial[, .(hex_id, spatial_group)], by = 'hex_id')
spatial_means <- rbindlist(list(group_summary(spatial_panel, 'all_hex_remote_control', 'spatial_group'),
  group_summary(spatial_panel[hex_id %in% local_spatial$hex_id], 'common_blocks_remote_control', 'spatial_group')))
fwrite(spatial_means, file.path(OUT, 'spillover_group_means.csv'))
fwrite(spatial[, .(hex_id, spatial_group, spatial_block,
                  in_common_blocks = hex_id %in% local_spatial$hex_id)], file.path(OUT, 'spillover_sample.csv'))
