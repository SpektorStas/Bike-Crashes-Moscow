# Пространственные группы и линейные комбинации оценок.
spillover_group <- function(treated, distance_m) {
  if (anyNA(treated) || anyNA(distance_m) || any(distance_m < 0) ||
      any(!is.finite(distance_m)) || any(!treated %in% c(0L, 1L))) stop('Invalid exposure')
  group <- rep('control_gt2000m', length(treated))
  group[treated == 0L & distance_m <= 2000] <- 'ring_1000_2000m'
  group[treated == 0L & distance_m <= 1000] <- 'ring_500_1000m'
  group[treated == 0L & distance_m <= 500] <- 'ring_0_500m'
  group[treated == 1L] <- 'core'
  group
}

spillover_terms <- c('core', 'ring_0_500m', 'ring_500_1000m', 'ring_1000_2000m')

add_exposure <- function(data, distance_column) {
  z <- data.table::copy(data)
  z[, spatial_group := spillover_group(treated_current, get(distance_column))]
  if (!any(z$spatial_group == 'control_gt2000m')) stop('No remote controls beyond 2000 m')
  for (g in spillover_terms) z[, (g) := as.integer(spatial_group == g)]
  z
}

linear_contrast <- function(model, weights) {
  beta <- stats::coef(model)
  if (!all(names(weights) %in% names(beta))) stop('Contrast requires missing coefficient')
  v <- stats::vcov(model)[names(weights), names(weights), drop = FALSE]
  estimate <- sum(weights * beta[names(weights)])
  se <- sqrt(max(0, drop(t(weights) %*% v %*% weights)))
  df <- fixest::degrees_freedom(model, type = 't')
  critical <- stats::qt(.975, df = df)
  p <- if (se > 0) 2 * stats::pt(-abs(estimate / se), df = df) else NA_real_
  data.table::data.table(estimate = estimate, se = se,
                        ci_low = estimate - critical * se,
                        ci_high = estimate + critical * se, p_value = p)
}

fit_ring_fd <- function(wide, cutoff_km = 2, block_fe = FALSE) {
  present <- spillover_terms[vapply(spillover_terms, function(g) any(wide[[g]] == 1), logical(1))]
  if (!length(present)) stop('No exposed group')
  fml <- stats::reformulate(present, response = 'delta')
  if (block_fe) fml <- stats::as.formula(paste(paste(deparse(fml), collapse = ' '), '| spatial_block'))
  fixest::feols(fml, data = wide,
                vcov = fixest::vcov_conley(lat = 'lat', lon = 'lon', cutoff = cutoff_km,
                                           distance = 'spherical'))
}

ring_estimates <- function(model, distance_definition, cutoff_km) {
  terms <- intersect(spillover_terms, names(stats::coef(model)))
  r <- data.table::rbindlist(lapply(terms, function(g) {
    z <- linear_contrast(model, stats::setNames(1, g))
    z[, `:=`(group = g, distance_definition = distance_definition,
             conley_cutoff_km = cutoff_km, scale = 'crashes/hexagon', n = stats::nobs(model))]
    z
  }))
  r[, p_holm_within_model := stats::p.adjust(p_value, method = 'holm')]
  r
}

neighborhood_contrasts <- function(model, wide, distance_definition, cutoff_km) {
  # Disjoint hexagons, no repeated crash counts or overlapping buffers.
  sets <- list(core_plus_500m = spillover_terms[1:2],
               core_plus_1000m = spillover_terms[1:3],
               core_plus_2000m = spillover_terms)
  sizes <- table(wide$spatial_group)
  data.table::rbindlist(lapply(names(sets), function(name) {
    groups <- intersect(sets[[name]], names(stats::coef(model)))
    if (!length(groups)) return(NULL)
    w <- stats::setNames(as.numeric(sizes[groups]), groups)
    total <- linear_contrast(model, w)
    total[, `:=`(neighborhood = name, exposed_cells = sum(w),
                 distance_definition = distance_definition, conley_cutoff_km = cutoff_km,
                 scale = 'sum of excess crashes across exposed hexagons')]
    total[, `:=`(per_cell = estimate / sum(w), per_cell_ci_low = ci_low / sum(w),
                 per_cell_ci_high = ci_high / sum(w))]
    total
  }))
}
