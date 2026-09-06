/**
 * UPS Monitor - Modern Dashboard Frontend
 */

let consoChart = null;
let currentRange = '24h';
let currentCurrency = '€';
let currentPricePerKwh = 0.25;
let currentPowerFactor = 0.7;
let isDarkTheme = true;

// --- INITIALIZATION ---
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initSettingsModal();
    initRangeSelector();
    
    // Initial fetch
    fetchConfig();
    fetchUpsMetrics();
    fetchEnergyStats();
    fetchConsoChart(currentRange);
    fetchOutages();

    // Recurring intervals
    setInterval(fetchUpsMetrics, 3000);   // Live data every 3s
    setInterval(fetchEnergyStats, 15000); // Stats every 15s
    setInterval(fetchOutages, 15000);     // Outages every 15s
    setInterval(() => {
        // Auto-refresh chart smoothly every 30s for short ranges
        if (['1h', '6h', '24h'].includes(currentRange)) {
            fetchConsoChart(currentRange, true);
        }
    }, 30000);
});

// --- THEME MANAGEMENT ---
function initTheme() {
    const savedTheme = localStorage.getItem('ups_theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    isDarkTheme = savedTheme ? (savedTheme === 'dark') : prefersDark;

    applyTheme(isDarkTheme);

    const toggleBtn = document.getElementById('theme-toggle');
    toggleBtn.addEventListener('click', () => {
        isDarkTheme = !isDarkTheme;
        applyTheme(isDarkTheme);
        localStorage.setItem('ups_theme', isDarkTheme ? 'dark' : 'light');
        if (consoChart) {
            updateChartTheme();
        }
    });
}

function applyTheme(dark) {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
    const themeIcon = document.getElementById('theme-icon');
    themeIcon.textContent = dark ? '☀️' : '🌙';
}

function getThemeColors() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    return {
        gridColor: isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.06)',
        textColor: isDark ? '#94a3b8' : '#64748b',
        lineColor: isDark ? '#38bdf8' : '#0284c7',
        gradientStart: isDark ? 'rgba(56, 189, 248, 0.35)' : 'rgba(2, 132, 199, 0.25)',
        gradientEnd: 'rgba(56, 189, 248, 0.0)'
    };
}

// --- LIVE UPS METRICS ---
async function fetchUpsMetrics() {
    try {
        const res = await fetch('/api/ups');
        if (!res.ok) return;
        const data = await res.json();

        // Model & Status
        if (data.device_model) {
            document.getElementById('ups-model').textContent = data.device_model;
        }

        const statusPill = document.getElementById('status-pill');
        const statusText = document.getElementById('status-text');
        const batteryAlert = document.getElementById('battery-alert');

        statusPill.className = `status-pill ${data.status_badge || 'online'}`;
        statusText.textContent = data.status_label || 'En ligne';

        // Power Cut Alert Banner
        if (data.is_on_battery) {
            batteryAlert.classList.remove('hidden');
            document.getElementById('alert-runtime-msg').textContent = 
                `L'onduleur fonctionne sur batterie. Autonomie restante estimée : ${data.battery_runtime_str || '--'}.`;
        } else {
            batteryAlert.classList.add('hidden');
        }

        // Real Power & Apparent Power
        document.getElementById('real-watts').textContent = data.real_watts ?? '--';
        document.getElementById('apparent-va').textContent = `${data.apparent_va ?? '--'} VA`;
        if (data.power_factor) {
            currentPowerFactor = data.power_factor;
            document.getElementById('pf-display').textContent = `cos φ ${data.power_factor}`;
        }

        // Load Percentage
        const load = data.ups_load ?? 0;
        document.getElementById('load-pct').textContent = load;
        const loadBar = document.getElementById('load-bar');
        loadBar.style.width = `${Math.min(load, 100)}%`;
        loadBar.className = 'progress-bar' + (load > 80 ? ' danger' : load > 50 ? ' warning' : '');

        if (data.nominal_va) {
            document.getElementById('nominal-va').textContent = `${data.nominal_va} VA`;
        }
        if (data.output_voltage) {
            document.getElementById('output-voltage').textContent = `${data.output_voltage.toFixed(1)} V`;
        }

        // Battery & Runtime
        const batt = data.battery_charge ?? 0;
        document.getElementById('battery-charge').textContent = batt;
        const battBar = document.getElementById('battery-bar');
        battBar.style.width = `${Math.min(batt, 100)}%`;
        battBar.className = 'progress-bar battery' + (batt < 25 ? ' danger' : batt < 50 ? ' warning' : '');

        document.getElementById('battery-runtime').textContent = data.battery_runtime_str ?? '--';
        if (data.output_frequency) {
            document.getElementById('output-freq').textContent = `${data.output_frequency.toFixed(1)} Hz`;
        }

    } catch (err) {
        console.warn('Erreur fetch UPS metrics:', err);
    }
}

// --- ENERGY STATS ---
async function fetchEnergyStats() {
    try {
        const res = await fetch('/api/stats');
        if (!res.ok) return;
        const data = await res.json();

        currentCurrency = data.currency || '€';
        currentPricePerKwh = data.price_per_kwh || 0.25;

        // KPI Card 4
        document.getElementById('cost-24h').textContent = data.cost_24h.toFixed(2);
        document.getElementById('cost-unit').textContent = currentCurrency;
        document.getElementById('kwh-24h').textContent = `${data.kwh_24h} kWh`;
        document.getElementById('cost-month').textContent = `${data.projected_monthly_cost.toFixed(2)} ${currentCurrency}`;

        // Bottom Summary Card
        document.getElementById('stat-min-watts').textContent = `${data.min_watts_24h} W`;
        document.getElementById('stat-avg-watts').textContent = `${data.avg_watts_24h} W`;
        document.getElementById('stat-max-watts').textContent = `${data.max_watts_24h} W`;

        document.getElementById('stat-projected-month').textContent = 
            `${data.projected_monthly_kwh} kWh (~ ${data.projected_monthly_cost.toFixed(2)} ${currentCurrency})`;
        document.getElementById('stat-projected-year').textContent = 
            `${data.projected_yearly_kwh} kWh (~ ${data.projected_yearly_cost.toFixed(2)} ${currentCurrency})`;
        document.getElementById('stat-total-kwh').textContent = 
            `${data.total_kwh} kWh (~ ${data.total_cost.toFixed(2)} ${currentCurrency})`;

        document.getElementById('records-count').textContent = 
            `${data.total_records.toLocaleString('fr-FR')} mesures`;

    } catch (err) {
        console.warn('Erreur stats:', err);
    }
}

// --- CHART.JS CONSUMPTION GRAPH ---
function initRangeSelector() {
    const pills = document.querySelectorAll('.pill-btn');
    pills.forEach(btn => {
        btn.addEventListener('click', () => {
            pills.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentRange = btn.getAttribute('data-range');
            fetchConsoChart(currentRange);
        });
    });
}

async function fetchConsoChart(range, isSilent = false) {
    const summaryLabel = document.getElementById('chart-summary');
    if (!isSilent) {
        summaryLabel.textContent = 'Chargement des données...';
    }

    try {
        const res = await fetch(`/api/conso?range=${range}`);
        if (!res.ok) throw new Error('Erreur API');
        const data = await res.json();

        if (!Array.isArray(data) || data.length === 0) {
            summaryLabel.textContent = 'Aucune donnée sur cette période';
            if (consoChart) {
                consoChart.data.labels = [];
                consoChart.data.datasets[0].data = [];
                consoChart.update();
            }
            return;
        }

        // Format timestamps & values
        const labels = [];
        const values = [];
        let sum = 0;
        let minW = Infinity;
        let maxW = -Infinity;

        data.forEach(item => {
            const date = new Date(item.timestamp);
            labels.push(formatChartDate(date, range));
            const w = item.watts;
            values.push(w);
            sum += w;
            if (w < minW) minW = w;
            if (w > maxW) maxW = w;
        });

        const avgW = Math.round(sum / data.length);
        summaryLabel.textContent = 
            `${data.length} points | Moyenne : ${avgW} W | Min : ${minW} W | Max : ${maxW} W`;

        renderChart(labels, values, range);

    } catch (err) {
        console.warn('Erreur graphe:', err);
        summaryLabel.textContent = 'Erreur lors du chargement des données';
    }
}

function formatChartDate(date, range) {
    if (isNaN(date.getTime())) return '';
    const pad = n => String(n).padStart(2, '0');
    const h = pad(date.getHours());
    const m = pad(date.getMinutes());
    const d = pad(date.getDate());
    const mo = pad(date.getMonth() + 1);

    if (range === '1h' || range === '6h' || range === '24h') {
        return `${h}h${m}`;
    } else if (range === '48h' || range === '7d' || range === '14d') {
        return `${d}/${mo} ${h}h`;
    } else if (range === '30d') {
        return `${d}/${mo} ${h}h`;
    } else {
        return `${d}/${mo}/${date.getFullYear()}`;
    }
}

function renderChart(labels, values, range) {
    const ctx = document.getElementById('consoChart').getContext('2d');
    const colors = getThemeColors();

    const gradient = ctx.createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, colors.gradientStart);
    gradient.addColorStop(1, colors.gradientEnd);

    const showPoints = labels.length < 80;

    if (consoChart) {
        consoChart.data.labels = labels;
        consoChart.data.datasets[0].data = values;
        consoChart.data.datasets[0].borderColor = colors.lineColor;
        consoChart.data.datasets[0].backgroundColor = gradient;
        consoChart.data.datasets[0].pointRadius = showPoints ? 2.5 : 0;
        consoChart.update(range === currentRange ? 'none' : undefined);
        return;
    }

    consoChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Puissance Active (W)',
                data: values,
                borderColor: colors.lineColor,
                backgroundColor: gradient,
                borderWidth: 2,
                fill: true,
                tension: 0.25,
                pointRadius: showPoints ? 2.5 : 0,
                pointHoverRadius: 5,
                pointBackgroundColor: colors.lineColor
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: {
                duration: 600
            },
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    titleFont: { family: 'Inter', size: 12, weight: 600 },
                    bodyFont: { family: 'JetBrains Mono', size: 12 },
                    padding: 10,
                    cornerRadius: 8,
                    displayColors: false,
                    callbacks: {
                        label: function(context) {
                            const watts = context.parsed.y;
                            const costPerHour = (watts / 1000 * currentPricePerKwh).toFixed(4);
                            return [
                                `Puissance : ${watts} W`,
                                `Coût estimé : ~${costPerHour} ${currentCurrency}/h`
                            ];
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: colors.gridColor,
                        drawBorder: false
                    },
                    ticks: {
                        color: colors.textColor,
                        font: { family: 'Inter', size: 11 },
                        maxTicksLimit: 12
                    }
                },
                y: {
                    beginAtZero: true,
                    grid: {
                        color: colors.gridColor,
                        drawBorder: false
                    },
                    ticks: {
                        color: colors.textColor,
                        font: { family: 'JetBrains Mono', size: 11 },
                        callback: function(val) {
                            return val + ' W';
                        }
                    }
                }
            }
        }
    });
}

function updateChartTheme() {
    if (!consoChart) return;
    const colors = getThemeColors();
    const ctx = document.getElementById('consoChart').getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, colors.gradientStart);
    gradient.addColorStop(1, colors.gradientEnd);

    consoChart.data.datasets[0].borderColor = colors.lineColor;
    consoChart.data.datasets[0].backgroundColor = gradient;
    consoChart.options.scales.x.grid.color = colors.gridColor;
    consoChart.options.scales.x.ticks.color = colors.textColor;
    consoChart.options.scales.y.grid.color = colors.gridColor;
    consoChart.options.scales.y.ticks.color = colors.textColor;
    consoChart.update();
}

// --- OUTAGES HISTORY ---
async function fetchOutages() {
    try {
        const res = await fetch('/api/outages');
        if (!res.ok) return;
        const data = await res.json();

        const tbody = document.getElementById('outages-tbody');
        const badge = document.getElementById('outages-count');

        if (!Array.isArray(data) || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="empty-state">Aucune coupure enregistrée récemment.</td></tr>';
            badge.textContent = '0 coupure';
            return;
        }

        badge.textContent = `${data.length} événement${data.length > 1 ? 's' : ''}`;
        tbody.innerHTML = '';

        data.forEach(item => {
            const tr = document.createElement('tr');
            const isOngoing = !item.end;
            const statusBadge = isOngoing 
                ? '<span class="status-pill battery">En cours</span>' 
                : '<span class="status-pill online">Terminée</span>';

            const startStr = formatDateTime(item.start);
            const endStr = item.end ? formatDateTime(item.end) : '--';

            tr.innerHTML = `
                <td>${startStr}</td>
                <td>${endStr}</td>
                <td><strong>${item.duration_formatted}</strong></td>
                <td>${statusBadge}</td>
            `;
            tbody.appendChild(tr);
        });

    } catch (err) {
        console.warn('Erreur outages:', err);
    }
}

function formatDateTime(isoStr) {
    if (!isoStr) return '--';
    const date = new Date(isoStr);
    if (isNaN(date.getTime())) return isoStr;
    const pad = n => String(n).padStart(2, '0');
    return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} à ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

// --- CONFIG & SETTINGS MODAL ---
async function fetchConfig() {
    try {
        const res = await fetch('/api/config');
        if (!res.ok) return;
        const cfg = await res.json();
        currentCurrency = cfg.currency || '€';
        currentPricePerKwh = cfg.price_per_kwh || 0.25;
        currentPowerFactor = cfg.power_factor || 0.7;

        document.getElementById('input-pf').value = currentPowerFactor;
        document.getElementById('input-price').value = currentPricePerKwh;
        document.getElementById('input-currency').value = currentCurrency;
    } catch (err) {
        console.warn('Erreur config:', err);
    }
}

function initSettingsModal() {
    const modal = document.getElementById('settings-modal');
    const btnOpen = document.getElementById('btn-open-settings');
    const btnClose = document.getElementById('btn-close-settings');
    const btnCancel = document.getElementById('btn-cancel-settings');
    const btnSave = document.getElementById('btn-save-settings');

    const openModal = () => modal.classList.remove('hidden');
    const closeModal = () => modal.classList.add('hidden');

    btnOpen.addEventListener('click', openModal);
    btnClose.addEventListener('click', closeModal);
    btnCancel.addEventListener('click', closeModal);

    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModal();
    });

    btnSave.addEventListener('click', async () => {
        const pf = parseFloat(document.getElementById('input-pf').value);
        const price = parseFloat(document.getElementById('input-price').value);
        const curr = document.getElementById('input-currency').value.trim() || '€';

        const payload = {
            power_factor: isNaN(pf) ? 0.7 : pf,
            price_per_kwh: isNaN(price) ? 0.25 : price,
            currency: curr
        };

        try {
            const res = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                closeModal();
                showToast('Paramètres enregistrés avec succès');
                fetchUpsMetrics();
                fetchEnergyStats();
                fetchConsoChart(currentRange, true);
            }
        } catch (err) {
            alert('Erreur lors de la sauvegarde : ' + err);
        }
    });
}

function showToast(msg) {
    const toast = document.getElementById('toast');
    toast.textContent = msg;
    toast.classList.remove('hidden');
    setTimeout(() => {
        toast.classList.add('hidden');
    }, 3000);
}
