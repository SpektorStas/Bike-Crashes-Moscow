# Запуск из корня проекта: Rscript analysis.R
# Пакеты устанавливаются отдельно: install.packages(c('data.table', 'fixest', 'jsonlite'))
# Сравниваем 2015 и 2025 по текущим велодорожкам. Даты их открытия неизвестны.
options(stringsAsFactors = FALSE)
if (!l10n_info()[['UTF-8']]) invisible(Sys.setlocale('LC_CTYPE', 'en_US.UTF-8'))
if (dir.exists('.r-library')) .libPaths(c(normalizePath('.r-library'), .libPaths()))
library(data.table)
library(fixest)
library(jsonlite)
source('scripts/spillover_models.R', encoding = 'UTF-8')

OUT <- 'outputs/final'
dir.create(OUT, recursive = TRUE, showWarnings = FALSE)
meta <- fromJSON('outputs/metadata.json')
d <- fread('outputs/hex_panel.csv')
pre_year <- as.integer(meta$pre_year)
post_year <- as.integer(meta$post_year)
stopifnot(!anyDuplicated(d[, .(hex_id, year)]), !anyNA(d$bike_crashes),
          all(d$bike_crashes >= 0), all(d$treated_current %in% 0:1))

# Два полных года; post = 1 для конечного года.
d[, treated := treated_current]
p <- d[year %in% c(pre_year, post_year)]
p[, `:=`(post = as.integer(year == post_year), any_crash = as.integer(bike_crashes > 0))]
p[, did := treated * post]
stopifnot(all(p$months_observed == length(meta$months)),
          all(p[, .N, by = hex_id]$N == 2L), setequal(p$treated, 0:1))

# Одна строка на гексагон. FD и двухпериодный DiD с FE ячейки дают один beta.
wide <- dcast(p, hex_id + treated + lon + lat + spatial_block ~ year,
              value.var = c('bike_crashes', 'any_crash'))
wide[, delta := get(paste0('bike_crashes_', post_year)) - get(paste0('bike_crashes_', pre_year))]
wide[, delta_any := get(paste0('any_crash_', post_year)) - get(paste0('any_crash_', pre_year))]
blocks <- wide[, .(has_bike = any(treated == 1), has_control = any(treated == 0)), by = spatial_block]
common_blocks <- blocks[has_bike & has_control, spatial_block]
local <- wide[spatial_block %in% common_blocks]
p_local <- p[spatial_block %in% common_blocks]
spatial_se <- vcov_conley(lat = 'lat', lon = 'lon', cutoff = 2, distance = 'spherical')

# Экспорт оценок, интервалов и фактического состава выборки.
models <- list()
rows <- list()
coefficients <- list()
add_model <- function(id, label, model, data, term, scale, sample, se_method,
                      notes = '', primary = TRUE, family = 'main', outcome = 'bike_crashes') {
  tab <- coeftable(model)
  ci <- confint(model)
  used <- data[obs(model)]
  transform <- switch(scale, percent_change = function(x) 100 * expm1(x),
                      percentage_points = function(x) 100 * x, function(x) x)
  rows[[id]] <<- data.table(id, label, outcome, scale,
    estimate = transform(tab[term, 1]), ci_low = transform(ci[term, 1]),
    ci_high = transform(ci[term, 2]), p_value = tab[term, 4],
    n_obs = nobs(model), n_hex = uniqueN(used$hex_id),
    n_blocks = uniqueN(used$spatial_block), n_input_hex = uniqueN(data$hex_id),
    formula = paste(deparse(formula(model)), collapse = ' '), sample, se_method, notes,
    family, term, primary, raw_estimate = tab[term, 1], raw_ci_low = ci[term, 1],
    raw_ci_high = ci[term, 2])
  models[[id]] <<- model
  coefficients[[id]] <<- data.table(id, term = rownames(tab), estimate = tab[, 1],
    std_error = tab[, 2], ci_low = ci[, 1], ci_high = ci[, 2], p_value = tab[, 4])
  invisible(model)
}

# 1. Городское сравнение: сохраняет все нулевые ячейки, но центр и окраины несопоставимы.
fd_global <- feols(delta ~ treated, data = wide, vcov = spatial_se)
add_model('fd_global', 'DiD: весь город', fd_global, wide, 'treated', 'crashes_per_hex',
          'all_hex', 'Conley, 2 км', 'Разность абсолютных изменений; география групп различается.')

# 2. Основной локальный вариант: только блоки 5 км с обеими группами.
# FE блока в первых разностях = отдельное изменение во времени для каждого блока.
fd_local <- feols(delta ~ treated | spatial_block, data = local, vcov = spatial_se)
add_model('fd_local', 'DiD: внутри общих блоков', fd_local, local, 'treated', 'crashes_per_hex',
          'common_blocks', 'Conley, 2 км', 'Сопоставление внутри 5-км блоков; не устраняет весь отбор.')

# Меняем только радиус пространственной зависимости ошибок, не состав данных.
for (km in c(1, 5)) {
  fit <- summary(fd_local, vcov = vcov_conley(lat = 'lat', lon = 'lon', cutoff = km,
                                             distance = 'spherical'))
  add_model(paste0('fd_local_conley', km), paste0('Локальный DiD: SE ', km, ' км'),
            fit, local, 'treated', 'crashes_per_hex', 'common_blocks', paste0('Conley, ', km, ' км'),
            'Чувствительность интервала к радиусу пространственной корреляции.', primary = FALSE)
}

# 3. PPML: относительное изменение числа ДТП.
# Ячейки с нулями в обоих годах не информативны для PPML с FE и исключаются.
# Пространственная кластеризация сохраняет также зависимость двух лет одной ячейки.
ppml_global <- fepois(bike_crashes ~ did | hex_id + year, data = p, vcov = ~spatial_block)
add_model('ppml_global', 'PPML: весь город', ppml_global, p, 'did', 'percent_change',
          'all_hex_ppml_support', 'Кластеры 5 км',
          '100 × (exp(beta) − 1); выборка после удаления нулевых FE.')
ppml_local <- fepois(bike_crashes ~ did | hex_id + spatial_block^year,
                    data = p_local, vcov = ~spatial_block)
add_model('ppml_local', 'PPML: внутри общих блоков', ppml_local, p_local, 'did', 'percent_change',
          'common_blocks_ppml_support', 'Кластеры 5 км',
          'FE ячейки и блока × год; выборка после удаления нулевых FE.')

# 4. Другой исход: возникло ли хотя бы одно велосипедное ДТП за год.
# Коэффициент LPM выражен в процентных пунктах.
any_local <- feols(delta_any ~ treated | spatial_block, data = local, vcov = spatial_se)
add_model('any_local', 'Хотя бы одно ДТП: локальный DiD', any_local, local, 'treated',
          'percentage_points', 'common_blocks', 'Conley, 2 км',
          'Изменение доли ячеек с ДТП; не вероятность ДТП для велосипедиста.', outcome = 'any_bike_crash')

# Календарные траектории не являются event study: даты открытия неизвестны.
group_summary <- function(data, sample_name, group_column = 'treated') {
  z <- data[, .(n_hex = uniqueN(hex_id), crashes = sum(bike_crashes),
                mean_crashes = mean(bike_crashes), share_any = mean(bike_crashes > 0)),
            by = c(group_column, 'year')]
  setnames(z, group_column, 'group')
  z[, `:=`(group = as.character(group), sample = sample_name)]
  z[]
}
group_means <- rbindlist(list(group_summary(p, 'all_hex'), group_summary(p_local, 'common_blocks')))
complete_years <- d[, .(complete = all(months_observed == length(meta$months))), by = year][complete == TRUE, year]
trends <- rbindlist(list(group_summary(d[year %in% complete_years], 'all_hex'),
  group_summary(d[year %in% complete_years & spatial_block %in% common_blocks], 'common_blocks')))
fwrite(group_means, file.path(OUT, 'group_means.csv'))
fwrite(trends[order(sample, group, year)], file.path(OUT, 'trends.csv'))
fwrite(wide, file.path(OUT, 'first_differences.csv'))

# Изменение ДТП в соседних зонах и суммы для дорожек вместе с окружением.
source('spillover_analysis.R', encoding = 'UTF-8')

results <- rbindlist(rows, use.names = TRUE, fill = TRUE)
fwrite(results, file.path(OUT, 'models.csv'))
fwrite(rbindlist(coefficients), file.path(OUT, 'model_coefficients.csv'))
saveRDS(models, file.path(OUT, 'models.rds'))
notes <- list(
  years = c(pre_year, post_year), months = meta$months, n_hex = nrow(wide),
  n_treated = sum(wide$treated), n_control = sum(1L - wide$treated),
  common_blocks = length(common_blocks), common_block_hex = nrow(local),
  complete_trend_years = sort(complete_years),
  excluded_trend_years = sort(setdiff(unique(d$year), complete_years)),
  historical_treatment_verified = FALSE,
  interpretation = sprintf('Сравнение %s–%s по текущему слою велодорожек; причинный эффект строительства не установлен.', pre_year, post_year),
  limitations = c(
    'Нет проверенных дат открытия и состояний велодорожек в 2015 и 2025 годах; текущий слой может включать более поздние дорожки.',
    'Параллельные контрфактические тренды не проверены; промежуточные годы нельзя считать гарантированно до воздействия.',
    '2016, 2017 и 2026 имеют неполное покрытие и исключены из годовых траекторий.',
    'Без числа поездок или велопробега оцениваются количества ДТП, а не риск на поездку.',
    'Текущая дорожная сеть определяет отбор гексагонов; это не историческая дорожная сеть.',
    'Пространственные кольца евклидовы и не устанавливают связность улиц или перемещение велосипедистов.',
    'Небольшое число ДТП в удаленном контроле ограничивает spillover-сравнения.',
    'Результаты чувствительны к шкале исхода и составу контроля; интервалы 95% индивидуальные, кроме указанных Holm p-values.'))
write_json(notes, file.path(OUT, 'analysis_notes.json'), pretty = TRUE, auto_unbox = TRUE)
capture.output(sessionInfo(), file = file.path(OUT, 'R_sessionInfo.txt'))
print(results[primary == TRUE, .(id, estimate, ci_low, ci_high, p_value, n_hex, scale)])
cat('\nРезультаты сохранены в ', OUT, '\n', sep = '')
