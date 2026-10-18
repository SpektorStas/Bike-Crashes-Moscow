'use strict';
const report = JSON.parse(document.getElementById('report-data').textContent);
const meta = report.meta;
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
} [c]));
const fmt = (n, d = 0) => Number.isFinite(Number(n)) && n !== null ? Number(n).toLocaleString(
    'ru-RU', {
        minimumFractionDigits: d,
        maximumFractionDigits: d
    }) : '—';
const num = n => n !== null && n !== undefined && Number.isFinite(Number(n));
const signed = (n, d = 2) => num(n) ? (Number(n) > 0 ? '+' : '') + fmt(n, d) : '—';
const pvalue = n => !num(n) ? '—' : Number(n) < .001 ? '< 0,001' : fmt(n, 3);
const years = meta.years;
const incomplete = new Set(meta.incomplete_years);
const pre = meta.pre_year;
const post = meta.post_year;
const scaleAlias = {
    crashes_per_hex: 'count',
    percent_change: 'percent',
    percentage_points: 'probability',
    excess_crashes_total: 'total'
};
const scaleInfo = {
    count: {
        label: 'Число ДТП',
        unit: 'ДТП на гексагон',
        note: 'Изменение числа ДТП на гексагон относительно контрольной группы.',
        digits: 3
    },
    percent: {
        label: 'Относительное изменение',
        unit: '%',
        note: 'Относительное изменение ожидаемого числа ДТП, %; преобразование 100 × (exp(β) − 1).',
        digits: 1
    },
    probability: {
        label: 'Ячейки с ДТП',
        unit: 'п. п.',
        note: 'Изменение доли гексагонов хотя бы с одним ДТП за год, в процентных пунктах.',
        digits: 2
    },
    total: {
        label: 'Сумма по территории',
        unit: 'ДТП',
        note: 'Суммарное избыточное изменение по ядру и указанному окружению относительно контроля.',
        digits: 1
    }
};
const models = report.models.map(m => ({
    ...m,
    source_scale: m.scale,
    unit: (scaleInfo[scaleAlias[m.scale] || m.scale] || {}).unit,
    scale: scaleAlias[m.scale] || m.scale,
    n_obs: m.n_obs,
    n_hex: m.n_hex
}));
const sampleLabel = model => model.sample_label;
const isSpill = model => model.category === 'spillover';
const mainModels = models.filter(m => !isSpill(m)),
    spillModels = models.filter(isSpill);
const trends = report.trends;
$('study-period').textContent = `${pre} → ${post}`;
if (meta.summary) $('hero-summary').textContent = meta.summary;
const metrics = [{
    v: meta.n_hex,
    l: 'гексагонов с дорогами',
    s: `радиус ${fmt(meta.radius_m||500)} м`
}, {
    v: meta.n_treated,
    l: 'с текущими велодорожками',
    s: 'группа по современному слою'
}, {
    v: meta.bike_crashes_pre,
    l: `ДТП с велосипедистами · ${pre}`,
    s: 'в исследуемых гексагонах'
}, {
    v: meta.bike_crashes_post,
    l: `ДТП с велосипедистами · ${post}`,
    s: 'в исследуемых гексагонах'
}];
$('metrics').innerHTML = metrics.map(m =>
    `<div class="metric"><div class="metric-value">${fmt(m.v)}</div><div class="metric-label">${esc(m.l)}</div><div class="metric-sub">${esc(m.s)}</div></div>`
).join('');
$('report-meta').textContent = `Отчёт${meta.generated_at?' · '+meta.generated_at:''} · расчёты в R`;

function makeTrend() {
    const compact = window.innerWidth < 760,
        w = compact ? Math.max(260, $('trend-chart').clientWidth) : 720,
        h = compact ? 245 : 310,
        p = {
            l: compact ? 37 : 51,
            r: compact ? 10 : 20,
            t: 18,
            b: 39
        },
        items = trends.filter(t => num(t.mean_outcome)),
        ymax = Math.max(...items.map(t => Number(t.mean_outcome)), .1) * 1.16,
        x = y => p.l + (y - years[0]) / (years[years.length - 1] - years[0] || 1) * (w - p.l - p.r),
        y = v => h - p.b - v / ymax * (h - p.t - p.b);
    let out =
        `<svg class="svg-chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="Динамика среднего числа ДТП по группам. Неполные годы не соединены линиями.">`;
    for (let i = 0; i <= 4; i++) {
        let val = ymax * i / 4,
            yy = y(val);
        out +=
            `<line x1="${p.l}" y1="${yy}" x2="${w-p.r}" y2="${yy}" stroke="#e8e8e8"/><text x="${p.l-10}" y="${yy+4}" text-anchor="end" font-size="11" fill="#747474">${fmt(val,2)}</text>`
    }
    for (const yr of years) {
        if (!compact || yr === years[0] || yr === years[years.length - 1] || (yr - years[0]) % 2 ===
            0) out +=
            `<text x="${x(yr)}" y="${h-13}" text-anchor="middle" font-size="11" fill="#747474">${yr}</text>`;
        if (incomplete.has(yr)) out +=
            `<rect x="${x(yr)-((w-p.l-p.r)/(years.length-1))/2}" y="${p.t}" width="${(w-p.l-p.r)/(years.length-1)}" height="${h-p.b-p.t}" fill="#ebebeb" opacity=".6"/>`
    }
    for (const group of [0, 1]) {
        const rows = items.filter(t => Number(t.treated) === group).sort((a, b) => a.year - b.year),
            color = group ? '#2d647f' : '#ac5b43';
        let prior = null;
        for (const row of rows) {
            const xx = x(row.year),
                yy = y(row.mean_outcome);
            if (row.complete && prior && prior.complete && row.year === prior.year + 1) out +=
                `<line x1="${x(prior.year)}" y1="${y(prior.mean_outcome)}" x2="${xx}" y2="${yy}" stroke="${color}" stroke-width="2.4"${group?'':' stroke-dasharray="6 4"'}/>`;
            out +=
                `<circle cx="${xx}" cy="${yy}" r="${row.complete?4:3.5}" fill="${row.complete?color:'#ffffff'}" stroke="${color}" stroke-width="1.8"><title>${row.year}: ${fmt(row.mean_outcome,3)} ДТП на гексагон${row.complete?'':' · неполный год'}</title></circle>`;
            prior = row
        }
    }
    out += '</svg>';
    $('trend-chart').innerHTML = out;
    const a = items.find(t => t.year === pre && Number(t.treated) === 1),
        b = items.find(t => t.year === post && Number(t.treated) === 1),
        c = items.find(t => t.year === pre && Number(t.treated) === 0),
        d = items.find(t => t.year === post && Number(t.treated) === 0);
    if (a && b && c && d) {
        $('comparison-text').textContent =
            `В группе с нынешними велодорожками было ${fmt(a.total??a.mean_outcome*a.cells)} ДТП в ${pre} году и ${fmt(b.total??b.mean_outcome*b.cells)} в ${post}. В группе без них — ${fmt(c.total??c.mean_outcome*c.cells)} и ${fmt(d.total??d.mean_outcome*d.cells)}. Исходные уровни и размеры групп различаются.`;
        $('growth-comparison').innerHTML = [{
            v: b.mean_outcome / a.mean_outcome,
            l: 'рост в группе с велодорожками'
        }, {
            v: d.mean_outcome / c.mean_outcome,
            l: 'рост в группе без велодорожек'
        }].map(t => `<div><strong>${fmt(t.v,2)}×</strong><span>${t.l}</span></div>`).join('')
    } else {
        $('comparison-text').textContent =
            'Линейные модели сравнивают абсолютные изменения числа ДТП, а пуассоновские — относительные изменения. Чтобы оценить безопасность поездки, нужны данные о велопотоке и датах открытия дорожек.'
    }
}
makeTrend();

function coefficientPlot(rows, container, scale) {
    const info = scaleInfo[scale] || scaleInfo.count;
    const valid = rows.filter(m => num(m.estimate) && num(m.ci_low) && num(m.ci_high));
    if (!valid.length) {
        $(container).innerHTML = '<div class="empty">Для этой шкалы нет оценённых моделей.</div>';
        return;
    }
    const compact = window.innerWidth < 760;
    const w = compact ? Math.max(260, $(container).clientWidth) : 1020;
    const p = compact ? {
        l: 12,
        r: 12,
        t: 0,
        b: 34
    } : {
        l: 390,
        r: 180,
        t: 35,
        b: 35
    };
    const rowH = compact ? 115 : 52;
    const h = p.t + p.b + rowH * valid.length;
    let lo = Math.min(0, ...valid.map(m => Number(m.ci_low)));
    let hi = Math.max(0, ...valid.map(m => Number(m.ci_high)));
    const span = hi - lo || 1;
    lo -= span * .08;
    hi += span * .08;
    const x = value => p.l + (value - lo) / (hi - lo) * (w - p.l - p.r);
    let out =
        `<svg class="coefficient-chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="Оценки моделей и 95-процентные доверительные интервалы. Шкала: ${esc(info.unit)}">`;
    for (let i = 0; i < 5; i++) {
        const value = lo + (hi - lo) * i / 4;
        out +=
            `<line x1="${x(value)}" x2="${x(value)}" y1="${compact ? 48 : p.t-15}" y2="${h-p.b+3}" stroke="#eaeaea"/><text x="${x(value)}" y="${h-8}" text-anchor="middle" font-size="${compact ? 10 : 11}" fill="#747474">${fmt(value, scale === 'count' ? 2 : 1)}</text>`;
    }
    out +=
        `<line x1="${x(0)}" x2="${x(0)}" y1="${compact ? 48 : p.t-15}" y2="${h-p.b+3}" stroke="#8d8d8d" stroke-dasharray="4 4"/>`;
    if (!compact) out +=
        `<text x="${w-p.r+20}" y="15" font-size="10" fill="#747474">Оценка [95% ДИ]</text>`;
    valid.forEach((m, i) => {
        const color = m.category === 'robustness' ? '#8a8a8a' : '#2d647f';
        const label = m.short_label || m.label || m.id;
        const note = m.short_note ||
            `${fmt(m.n_hex)} ячеек · ${m.se_method || sampleLabel(m)}`;
        const yy = compact ? i * rowH + 68 : p.t + i * rowH + rowH / 2 - 7;
        if (compact) {
            // On narrow screens the label sits above the estimate, at readable size.
            const words = label.split(' '),
                lines = [''];
            const maxLetters = Math.floor(w / 6.6);
            words.forEach(word => {
                if ((lines[lines.length - 1] + ' ' + word).trim().length >
                    maxLetters) lines.push(word);
                else lines[lines.length - 1] = (lines[lines.length - 1] + ' ' +
                    word).trim();
            });
            out += `<rect x="0" y="${i*rowH}" width="${w}" height="51" fill="white"/>`;
            lines.slice(0, 2).forEach((line, j) => {
                out +=
                    `<text x="0" y="${i*rowH + 14 + j*16}" font-size="12" fill="#2e2e2e">${esc(line)}</text>`;
            });
            out +=
                `<text x="0" y="${i*rowH+47}" font-size="10" fill="#747474">${esc(note.slice(0, Math.floor(w/5.5)))}</text>`;
            out +=
                `<rect x="0" y="${i*rowH+81}" width="${w}" height="30" fill="white"/><text x="0" y="${i*rowH+98}" font-size="11" fill="#2e2e2e">${signed(m.estimate, info.digits)} [${fmt(m.ci_low, info.digits)}; ${fmt(m.ci_high, info.digits)}] ${esc(info.unit)}</text>`;
            out +=
                `<line x1="0" x2="${w}" y1="${(i+1)*rowH-3}" y2="${(i+1)*rowH-3}" stroke="#efefef"/>`;
        } else {
            out +=
                `<line x1="0" x2="${w}" y1="${yy+27}" y2="${yy+27}" stroke="#f1f1f1"/><text x="0" y="${yy-2}" font-size="13" fill="#2e2e2e">${esc(label.length>53 ? label.slice(0,52)+'…' : label)}<title>${esc(label)}</title></text><text x="0" y="${yy+15}" font-size="10" fill="#747474">${esc(note.slice(0,66))}</text><text x="${w-p.r+20}" y="${yy-2}" font-size="12" fill="#2e2e2e">${signed(m.estimate,info.digits)}</text><text x="${w-p.r+20}" y="${yy+15}" font-size="10" fill="#747474">[${fmt(m.ci_low,info.digits)}; ${fmt(m.ci_high,info.digits)}]</text>`;
        }
        out +=
            `<line x1="${x(m.ci_low)}" x2="${x(m.ci_high)}" y1="${yy}" y2="${yy}" stroke="${color}" stroke-width="2.2"/><line x1="${x(m.ci_low)}" x2="${x(m.ci_low)}" y1="${yy-4}" y2="${yy+4}" stroke="${color}"/><line x1="${x(m.ci_high)}" x2="${x(m.ci_high)}" y1="${yy-4}" y2="${yy+4}" stroke="${color}"/><circle cx="${x(m.estimate)}" cy="${yy}" r="5" fill="${color}"><title>${esc(label)}: ${signed(m.estimate,info.digits)} [${signed(m.ci_low,info.digits)}; ${signed(m.ci_high,info.digits)}], p ${pvalue(m.p_value)}</title></circle>`;
    });
    $(container).innerHTML = out + '</svg>';
}
let activeMain = 'count',
    activeSpill = 'count';

function makeTabs(id, rows, active, callback) {
    const available = Object.keys(scaleInfo).filter(s => rows.some(m => m.scale === s));
    if (!available.includes(active)) active = available[0] || 'count';
    $(id).innerHTML = available.map(s =>
            `<button data-scale="${s}" aria-pressed="${s===active}">${scaleInfo[s].label}</button>`)
        .join('');
    $(id).querySelectorAll('button').forEach(b => b.addEventListener('click', () => callback(b
        .dataset.scale)));
    return active
}

function updateMain(scale = activeMain) {
    activeMain = makeTabs('main-scales', mainModels, scale, updateMain);
    const rows = mainModels.filter(m => m.scale === activeMain && ($('show-sensitivity').checked ||
        m.primary !== false && m.category !== 'robustness'));
    $('main-scale-note').textContent = (scaleInfo[activeMain] || scaleInfo.count).note;
    coefficientPlot(rows, 'main-model-chart', activeMain)
}

function updateSpill(scale = activeSpill) {
    activeSpill = makeTabs('spill-scales', spillModels, scale, updateSpill);
    const rows = spillModels.filter(m => m.scale === activeSpill && (m.primary !== false || !
        spillModels.some(q => q.scale === activeSpill && q.primary !== false)));
    $('spill-scale-note').textContent = (scaleInfo[activeSpill] || scaleInfo.count).note;
    coefficientPlot(rows, 'spill-model-chart', activeSpill)
}
$('show-sensitivity').addEventListener('change', () => updateMain());
updateMain();
updateSpill();
$('model-table').querySelector('tbody').innerHTML = models.map(m => {
    const sc = scaleInfo[m.scale] || {
        unit: m.scale,
        digits: 3
    };
    return `<tr><td class="model-cell">${esc(m.label||m.id)}<small>${esc(sampleLabel(m))}${m.notes?'<br>'+esc(m.notes):''}</small></td><td>${esc(sc.unit)}</td><td class="numeric">${signed(m.estimate,sc.digits)}<br><small>[${fmt(m.ci_low,sc.digits)}; ${fmt(m.ci_high,sc.digits)}]</small></td><td class="numeric">${pvalue(m.p_value)}<small>${num(m.p_holm_within_model??m.p_holm_across_radii)?"Holm: "+pvalue(m.p_holm_within_model??m.p_holm_across_radii):""}</small></td><td class="numeric">${fmt(m.n_obs)} / ${fmt(m.n_hex)}</td><td><span class="formula">${esc(m.formula)}</span><small>${esc(m.se_method)}</small></td></tr>`
}).join('');
$('download-csv').addEventListener('click', () => {
    const cols = ['id', 'label', 'category', 'family', 'primary', 'outcome', 'scale',
            'source_scale', 'unit', 'estimate', 'ci_low', 'ci_high', 'p_value',
            'p_holm_within_model', 'p_holm_across_radii', 'n_obs', 'n_hex', 'n_exposed_hex',
            'n_input_hex', 'n_blocks', 'formula', 'sample', 'se_method', 'notes'
        ],
        quote = v => '"' + String(v ?? '').replace(/"/g, '""') + '"',
        csv = '\ufeff' + [cols.join(','), ...models.map(m => cols.map(k => quote(m[k]))
            .join(','))].join('\r\n'),
        url = URL.createObjectURL(new Blob([csv], {
            type: 'text/csv;charset=utf-8'
        })),
        a = document.createElement('a');
    a.href = url;
    a.download = 'moscow_bike_models.csv';
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000)
});
$('conclusions').innerHTML = (report.conclusions || []).map((c, i) =>
    `<article class="conclusion"><div class="conclusion-index">0${i+1}</div><h3>${esc(c.title)}</h3><p>${esc(c.text)}</p></article>`
).join('');
$('findings-title').textContent = meta.findings_title || 'Основные результаты';
const historyRows = report.history_rows || [];
if (historyRows.length) {
    $('download-history').hidden = false;
    $('download-history').addEventListener('click', () => {
        const cols = Object.keys(historyRows[0]),
            quote = v => '"' + String(v ?? '').replace(/"/g, '""') + '"',
            csv = '\ufeff' + [cols.join(','), ...historyRows.map(row => cols.map(k => quote(
                row[k])).join(','))].join('\r\n'),
            url = URL.createObjectURL(new Blob([csv], {
                type: 'text/csv;charset=utf-8'
            })),
            a = document.createElement('a');
        a.href = url;
        a.download = 'moscow_bike_lane_history.csv';
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000)
    })
}
const hist = report.history_summary || {};
if (hist.title) $('history-title').textContent = hist.title;
$('history-summary').textContent = hist.summary ||
    'История ввода велодорожек не подтверждена для всего современного слоя.';
$('history-items').innerHTML = (hist.items || []).map(t =>
    `<div class="history-item"><span class="label">${esc(t.label)}</span><span class="value">${esc(t.value)}</span>${t.detail?'<span class="detail">'+esc(t.detail)+'</span>':''}</div>`
).join('');
$('history-limitation').textContent = hist.limitation || '';

function sourceLinks(items) {
    return items.filter(s => /^https?:\/\//i.test(s.url || '')).map(s =>
        `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.label||s.url)} ↗</a>`
    ).join('')
}
$('history-sources').innerHTML = sourceLinks(hist.sources || []);
if (!(hist.sources || []).length) $('history-sources').hidden = true;
$('limitations').innerHTML = (report.limitations || []).map(t => `<li>${esc(t)}</li>`).join('');
$('method-sources').innerHTML = '<strong>Данные и метод</strong><br>' + esc(meta.data_note ||
    'ДТП с участием велосипедистов; текущий слой велодорожек; дорожная сеть OpenStreetMap. Расчёты выполнены в R.'
) + sourceLinks(report.sources || []);
// Геометрия хранится в метрах; одинаковая цветовая шкала используется во все годы.
const mapData = report.map || {},
    hexes = (mapData.hexagons || []).filter(h => h.points && h.points.length > 2),
    bikePaths = mapData.bike_paths || [],
    boundary = mapData.boundary || [],
    canvas = $('map'),
    ctx = canvas.getContext('2d');
const countColors = ['#edf0f1', '#cbdde5', '#91b8ca', '#4e88a4', '#24546d'];
const groupNames = {
    core: 'С велодорожкой',
    ring_0_500m: 'Соседи: до 500 м',
    ring_500_1000m: 'Соседи: 500–1 000 м',
    ring_1000_2000m: 'Соседи: 1 000–2 000 м',
    remote: 'Контроль: дальше 2 км'
};
const groupColors = {
    core: '#2d647f',
    ring_0_500m: '#91b8ca',
    ring_500_1000m: '#cbdde5',
    ring_1000_2000m: '#e1eaf0',
    remote: '#edf0f1'
};
let mode = 'crashes',
    yearIndex = 0,
    zoom = 1,
    panX = 0,
    panY = 0,
    cw = 1,
    ch = 1,
    baseScale = 1,
    cx = 0,
    cy = 0,
    selected = null,
    playing = false,
    timer = null,
    drag = null;
const bbox = mapData.initial_bbox;
cx = (bbox[0] + bbox[2]) / 2;
cy = (bbox[1] + bbox[3]) / 2;
const paths = hexes.map(h => {
    const p = new Path2D();
    h.points.forEach((q, i) => i ? p.lineTo(q[0], -q[1]) : p.moveTo(q[0], -q[1]));
    p.closePath();
    return p
});
const linePath = coords => {
    const p = new Path2D();
    coords.forEach((q, i) => i ? p.lineTo(q[0], -q[1]) : p.moveTo(q[0], -q[1]));
    return p
};
const bikeDrawing = new Path2D();
bikePaths.forEach(p => bikeDrawing.addPath(linePath(p)));
const boundaryDrawing = new Path2D();
boundary.forEach(p => boundaryDrawing.addPath(linePath(p)));
const mkadDrawing = new Path2D();
mapData.mkad_paths.forEach(p => mkadDrawing.addPath(linePath(p)));
const getGroup = h => h.group || ((Number(h.treated) === 1) ? 'core' : 'remote');

function resizeMap() {
    const rect = canvas.getBoundingClientRect(),
        ratio = Math.min(window.devicePixelRatio || 1, 2);
    cw = rect.width;
    ch = rect.height;
    canvas.width = Math.round(cw * ratio);
    canvas.height = Math.round(ch * ratio);
    baseScale = Math.min((cw - 65) / (bbox[2] - bbox[0] || 1), (ch - 70) / (bbox[3] - bbox[1] ||
        1));
    drawMap()
}

function drawMap() {
    const ratio = canvas.width / cw,
        s = baseScale * zoom;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, cw, ch);
    ctx.save();
    ctx.translate(cw / 2 + panX, ch / 2 + panY);
    ctx.scale(s, s);
    ctx.translate(-cx, cy);
    for (let i = 0; i < hexes.length; i++) {
        const h = hexes[i],
            n = Number(h.counts?.[yearIndex] || 0);
        ctx.fillStyle = mode === 'exposure' ? (groupColors[getGroup(h)] || groupColors.remote) :
            countColors[Math.min(n, 4)];
        ctx.fill(paths[i]);
        ctx.strokeStyle = '#ffffff70';
        ctx.lineWidth = .45 / s;
        ctx.stroke(paths[i])
    }
    ctx.strokeStyle = '#a6a6a6';
    ctx.lineWidth = .9 / s;
    ctx.stroke(boundaryDrawing);
    ctx.strokeStyle = '#666666';
    ctx.lineWidth = 1.1 / s;
    ctx.stroke(mkadDrawing);
    if ($('show-bike').checked) {
        ctx.strokeStyle = '#ac5b43';
        ctx.globalAlpha = .85;
        ctx.lineWidth = Math.max(.9 / s, 12);
        ctx.stroke(bikeDrawing);
        ctx.globalAlpha = 1
    }
    if (selected !== null) {
        ctx.strokeStyle = '#2e2e2e';
        ctx.lineWidth = 2 / s;
        ctx.stroke(paths[selected])
    }
    ctx.restore();
    const target = 90 / s,
        scaleMeters = [100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000].reduce((a, b) => Math
            .abs(b - target) < Math.abs(a - target) ? b : a);
    $('scale-line').style.width = `${scaleMeters*s}px`;
    $('scale-label').textContent = scaleMeters >= 1000 ? `${fmt(scaleMeters/1000)} км` :
        `${scaleMeters} м`
}

function updateCell() {
    if (selected === null) {
        $('cell-info').innerHTML =
            '<strong>Выберите место на карте</strong><span>Нажмите на гексагон, чтобы увидеть его группу и число ДТП.</span>';
        return
    }
    const h = hexes[selected],
        n = h.counts?.[yearIndex] ?? 0;
    $('cell-info').innerHTML =
        `<strong>Ячейка ${esc(h.id)} · ${years[yearIndex]}</strong><span>${esc(groupNames[getGroup(h)]||getGroup(h))}<br>${fmt(n)} ДТП с велосипедистами${incomplete.has(years[yearIndex])?' · неполный год':''}</span>`
}

function setYear(i) {
    yearIndex = Math.max(0, Math.min(years.length - 1, i));
    $('year-slider').value = yearIndex;
    $('year-slider').setAttribute('aria-valuetext',
        `${years[yearIndex]} год${incomplete.has(years[yearIndex])?', неполные данные':''}`);
    $('map-year').textContent = years[yearIndex];
    $('map-total').textContent =
        `${fmt(hexes.reduce((sum,h)=>sum+Number(h.counts?.[yearIndex]||0),0))} ДТП · вся выборка`;
    $('partial-warning').style.display = incomplete.has(years[yearIndex]) ? 'block' : 'none';
    drawMap();
    updateCell()
}

function stop() {
    playing = false;
    clearTimeout(timer);
    $('play').textContent = '▶';
    $('play').setAttribute('aria-label', 'Запустить анимацию по годам');
    $('play').setAttribute('aria-pressed', 'false')
}

function tick() {
    if (!playing) return;
    let next = yearIndex + 1;
    while (next < years.length && incomplete.has(years[next])) next++;
    if (next >= years.length) {
        stop();
        return
    }
    setYear(next);
    timer = setTimeout(tick, 1450)
}
$('play').addEventListener('click', () => {
    if (playing) {
        stop();
        return
    }
    if (yearIndex >= years.length - 1) setYear(0);
    playing = true;
    $('play').textContent = 'Ⅱ';
    $('play').setAttribute('aria-label', 'Остановить анимацию');
    $('play').setAttribute('aria-pressed', 'true');
    timer = setTimeout(tick, 1100)
});
$('year-slider').max = years.length - 1;
$('year-labels').innerHTML = years.map(y => `<span>${y}</span>`).join('');
$('year-slider').addEventListener('input', e => {
    stop();
    setYear(Number(e.target.value))
});

function zoomBy(factor) {
    zoom = Math.max(.25, Math.min(zoom * factor, 12));
    drawMap()
}
$('zoom-in').addEventListener('click', () => zoomBy(1.4));
$('zoom-out').addEventListener('click', () => zoomBy(1 / 1.4));
$('zoom-reset').addEventListener('click', () => {
    zoom = 1;
    panX = panY = 0;
    drawMap()
});
$('show-bike').addEventListener('change', drawMap);

function legend() {
    if (mode === 'crashes') {
        $('legend-title').textContent = 'ДТП / ячейку / год';
        $('map-legend').innerHTML = countColors.map((c, i) =>
            `<div class="legend-row"><i class="swatch" style="background:${c}"></i>${i===4?'4 и более':i}</div>`
        ).join('');
        $('legend-note').textContent =
            'Одинаковая шкала для всех лет. Нулевая ячейка означает отсутствие зарегистрированных ДТП.'
    } else {
        $('legend-title').textContent = 'Зоны воздействия';
        $('map-legend').innerHTML = Object.entries(groupNames).map(([g, label]) =>
            `<div class="legend-row"><i class="swatch" style="background:${groupColors[g]}"></i>${label}</div>`
        ).join('');
        $('legend-note').textContent =
            'Расстояние от края ячейки до текущей велодорожки. Эти зоны одинаковы во все годы.'
    }
}
$('map-modes').querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    mode = b.dataset.mode;
    $('map-modes').querySelectorAll('button').forEach(q => q.setAttribute(
        'aria-pressed', String(q === b)));
    legend();
    drawMap()
}));
canvas.addEventListener('pointerdown', e => {
    drag = {
        x: e.clientX,
        y: e.clientY,
        px: panX,
        py: panY,
        moved: false
    };
    canvas.setPointerCapture(e.pointerId)
});
canvas.addEventListener('pointermove', e => {
    if (!drag) return;
    const dx = e.clientX - drag.x,
        dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 5) drag.moved = true;
    if (drag.moved) {
        panX = drag.px + dx;
        panY = drag.py + dy;
        drawMap()
    }
});
canvas.addEventListener('pointerup', e => {
    if (drag && !drag.moved) {
        const rect = canvas.getBoundingClientRect(),
            s = baseScale * zoom,
            px = (e.clientX - rect.left - cw / 2 - panX) / s + cx,
            py = (e.clientY - rect.top - ch / 2 - panY) / s - cy;
        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        selected = paths.findIndex(p => ctx.isPointInPath(p, px, py));
        if (selected < 0) selected = null;
        ctx.restore();
        updateCell();
        drawMap()
    }
    drag = null
});
canvas.addEventListener('pointercancel', () => {
    drag = null
});
canvas.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
        e.preventDefault();
        const s = baseScale * zoom,
            px = cx - panX / s,
            py = -cy - panY / s;
        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        selected = paths.findIndex(p => ctx.isPointInPath(p, px, py));
        if (selected < 0) selected = null;
        ctx.restore();
        updateCell();
        drawMap()
    }
    if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', '+', '=', '-', 'Home'].includes(
            e.key)) {
        e.preventDefault();
        if (e.key === 'ArrowUp') panY += 45;
        if (e.key === 'ArrowDown') panY -= 45;
        if (e.key === 'ArrowLeft') panX += 45;
        if (e.key === 'ArrowRight') panX -= 45;
        if (e.key === '+' || e.key === '=') zoom = Math.min(zoom * 1.3, 12);
        if (e.key === '-') zoom = Math.max(zoom / 1.3, .25);
        if (e.key === 'Home') {
            zoom = 1;
            panX = panY = 0
        }
        drawMap()
    }
});
document.addEventListener('visibilitychange', () => {
    if (document.hidden) stop()
});
legend();
new ResizeObserver(resizeMap).observe(canvas);
setYear(0);
let chartResize;
window.addEventListener('resize', () => {
    clearTimeout(chartResize);
    chartResize = setTimeout(() => {
        makeTrend();
        updateMain();
        updateSpill()
    }, 150)
});

const readingLinks = [...$('reading-links').querySelectorAll('a')];
const readingSections = readingLinks.map(link => document.querySelector(link.getAttribute('href')));
const sectionAnchors = [...document.querySelectorAll('.section-anchor')];
// Длинный раздел сначала прокручивается до конца, затем его накрывает следующий.
function updateSectionStack() {
    const header = document.querySelector('.masthead').offsetHeight;
    const available = window.innerHeight - header;
    readingSections.forEach((section, index) => {
        section.style.setProperty('--stack-top',
            `${header - Math.max(0, section.offsetHeight - available)}px`);
        section.style.zIndex = index + 1;
    });
}
new ResizeObserver(updateSectionStack).observe($('main'));
window.addEventListener('resize', updateSectionStack);
updateSectionStack();
let readingFrame = null;

function updateReadingProgress() {
    const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
    const progress = maxScroll > 0 ? Math.min(1, Math.max(0, window.scrollY / maxScroll)) : 1;
    const percent = Math.round(progress * 100);
    $('reading-fill').style.transform = `scaleX(${progress})`;
    $('reading-percent').textContent = `${percent}%`;
    const track = $('reading-progress');
    const bike = $('reading-bike');
    // Reserve the bicycle, car and edge padding; SVG margins overlap at contact.
    const travel = track.clientWidth - 124;
    bike.style.transform = `translateX(${Math.max(0, travel) * progress}px)`;
    track.style.setProperty('--wheel-angle', `${progress * 3600}deg`);
    track.classList.toggle('is-complete', progress >= .9999);
    track.setAttribute('aria-valuenow', percent);
    let current = 0;
    sectionAnchors.forEach((anchor, index) => {
        if (anchor.getBoundingClientRect().top <= Math.min(220, window.innerHeight * .3))
            current = index;
    });
    if (progress >= .995) current = readingSections.length - 1;
    readingLinks.forEach((link, index) => {
        if (index === current) {
            const changed = !link.hasAttribute('aria-current');
            link.setAttribute('aria-current', 'location');
            const list = $('reading-links');
            if (changed && list.scrollWidth > list.clientWidth) list.scrollLeft = link
                .offsetLeft - list.clientWidth / 2 + link.offsetWidth / 2;
        } else link.removeAttribute('aria-current');
    });
    readingFrame = null;
}

function queueReadingUpdate() {
    if (readingFrame === null) readingFrame = requestAnimationFrame(updateReadingProgress);
}
[...readingLinks, document.querySelector('.hero-link')].forEach(link => {
    link.addEventListener('click', event => {
        const anchor = sectionAnchors.find(item => item.dataset.section === link
            .hash.slice(1));
        if (!anchor) return;
        event.preventDefault();
        const top = window.scrollY + anchor.getBoundingClientRect().top - document
            .querySelector('.masthead').offsetHeight;
        window.scrollTo({
            top,
            behavior: matchMedia('(prefers-reduced-motion: reduce)')
                .matches ? 'instant' : 'smooth'
        });
        history.replaceState(null, '', link.hash);
    });
});
window.addEventListener('scroll', queueReadingUpdate, {
    passive: true
});
window.addEventListener('resize', queueReadingUpdate);
new ResizeObserver(queueReadingUpdate).observe(document.body);
updateReadingProgress();
