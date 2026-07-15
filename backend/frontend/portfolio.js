const portfolioState = {
    tables: [],
    table: null,
    columns: [],
    results: [],
    filters: {},
    drafts: new Map(),
};

const $p = (selector) => document.querySelector(selector);
const portfolioTextTypes = new Set(['text', 'character varying', 'varchar', 'character', 'char']);

const ui = {
    intro: $p('#portfolio-intro'),
    workspace: $p('#portfolio-workspace'),
    tables: $p('#portfolio-tables'),
    tableFilter: $p('#portfolio-table-filter'),
    tableCount: $p('#portfolio-table-count'),
    tableName: $p('#portfolio-table-name'),
    tableHeading: $p('#portfolio-table-heading'),
    searchForm: $p('#portfolio-search-form'),
    search: $p('#portfolio-search'),
    fuzzy: $p('#portfolio-fuzzy'),
    refresh: $p('#portfolio-refresh'),
    filterBar: $p('#portfolio-filter-bar'),
    filters: $p('#portfolio-filters'),
    clearFilters: $p('#portfolio-clear-filters'),
    resultCount: $p('#portfolio-result-count'),
    columnCount: $p('#portfolio-column-count'),
    description: $p('#portfolio-results-description'),
    table: $p('#portfolio-results-table'),
    loading: $p('#portfolio-loading'),
    empty: $p('#portfolio-empty'),
    error: $p('#portfolio-error'),
    errorMessage: $p('#portfolio-error-message'),
    draftBadge: $p('#draft-badge'),
    toastRegion: $p('#portfolio-toasts'),
};

function pIcon(name) { return `<i data-lucide="${name}"></i>`; }
function pIcons() { if (window.lucide) lucide.createIcons(); }
function pEscape(value) {
    return String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;');
}

async function portfolioApi(path, options = {}) {
    const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } });
    let data = {};
    try { data = await response.json(); } catch (_) { /* error below */ }
    if (!response.ok) throw new Error(data.detail || `Query failed (${response.status})`);
    return data;
}

function pToast(message) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `${pIcon('sparkles')}<span>${pEscape(message)}</span>`;
    ui.toastRegion.appendChild(toast);
    pIcons();
    setTimeout(() => toast.remove(), 3200);
}

function setPortfolioView(mode, message = '') {
    ui.loading.hidden = mode !== 'loading';
    ui.empty.hidden = mode !== 'empty';
    ui.error.hidden = mode !== 'error';
    ui.table.hidden = mode !== 'ready';
    if (message) ui.errorMessage.textContent = message;
}

function renderPortfolioTables() {
    const order = ['sam_lore', 'projects', 'skills', 'opinions', 'favorites'];
    const needle = ui.tableFilter.value.trim().toLowerCase();
    const tables = [...portfolioState.tables].sort((a, b) => order.indexOf(a) - order.indexOf(b)).filter((table) => table.includes(needle));
    ui.tableCount.textContent = portfolioState.tables.length;
    ui.tables.innerHTML = tables.map((table) => `
        <button type="button" class="tables-btn ${table === portfolioState.table ? 'active' : ''}" data-portfolio-table="${pEscape(table)}">
            ${pIcon('table-2')}<span>${pEscape(table)}</span><i class="table-chevron" data-lucide="chevron-right"></i>
        </button>`).join('');
    pIcons();
}

function renderPortfolioFilters() {
    const filterable = portfolioState.columns.filter((column) => Array.isArray(column.options) && column.options.some((value) => value !== null));
    ui.filterBar.hidden = !filterable.length;
    ui.filters.innerHTML = filterable.map((column) => {
        const current = portfolioState.filters[column.name]?.[0] || '';
        const options = column.options.filter((value) => value !== null).map((value) => `<option value="${pEscape(value)}" ${String(value) === current ? 'selected' : ''}>${pEscape(value)}</option>`).join('');
        return `<label class="filter-select ${current ? 'active' : ''}"><select data-portfolio-filter="${pEscape(column.name)}" aria-label="Filter by ${pEscape(column.name)}"><option value="">${pEscape(column.name)} · all</option>${options}</select>${pIcon('chevron-down')}</label>`;
    }).join('');
    ui.clearFilters.hidden = !Object.keys(portfolioState.filters).length;
    pIcons();
}

function draftKey(row, column) { return `${portfolioState.table}:${row.id}:${column}`; }
function applyDrafts(row) {
    const copy = { ...row };
    portfolioState.columns.forEach((column) => {
        const key = draftKey(row, column.name);
        if (portfolioState.drafts.has(key)) copy[column.name] = portfolioState.drafts.get(key);
    });
    return copy;
}

function pValue(value) {
    if (value === null || value === undefined) return '<span class="cell-null">null</span>';
    if (typeof value === 'boolean') return `<span class="cell-boolean ${value}">${value}</span>`;
    if (typeof value === 'object') return pEscape(JSON.stringify(value));
    return pEscape(value);
}

function updateDraftBadge() {
    const count = portfolioState.drafts.size;
    ui.draftBadge.hidden = count === 0;
    ui.draftBadge.querySelector('b').textContent = count;
}

function renderPortfolioResults() {
    const rows = portfolioState.results.map(applyDrafts);
    ui.resultCount.textContent = rows.length;
    ui.columnCount.textContent = portfolioState.columns.length;
    ui.description.textContent = `${rows.length} canonical record${rows.length === 1 ? '' : 's'}${portfolioState.drafts.size ? ' · local drafts applied' : ''}`;
    if (!rows.length) { ui.table.innerHTML = ''; setPortfolioView('empty'); return; }

    const names = portfolioState.columns.map((column) => column.name);
    ui.table.innerHTML = `<thead><tr><th class="row-index">#</th>${names.map((name) => `<th>${pEscape(name)}</th>`).join('')}</tr></thead><tbody>${rows.map((row, rowIndex) => `
        <tr><td class="row-index">${String(rowIndex + 1).padStart(2, '0')}</td>${names.map((name) => {
            const column = portfolioState.columns.find((item) => item.name === name);
            const editable = column && portfolioTextTypes.has(column.type) && name !== 'id';
            const drafted = portfolioState.drafts.has(draftKey(portfolioState.results[rowIndex], name));
            return `<td class="${drafted ? 'local-draft' : ''}"><div class="cell"><span class="cell-value" title="${pEscape(row[name] ?? 'null')}">${pValue(row[name])}</span>${editable ? `<button type="button" class="edit-cell-btn" data-p-edit-row="${rowIndex}" data-p-edit-column="${pEscape(name)}" aria-label="Edit ${pEscape(name)} locally">${pIcon('pencil')}</button>` : ''}</div></td>`;
        }).join('')}</tr>`).join('')}</tbody>`;
    setPortfolioView('ready');
    updateDraftBadge();
    pIcons();
}

async function runPortfolioQuery() {
    if (!portfolioState.table) return;
    setPortfolioView('loading');
    try {
        const data = await portfolioApi('/api/portfolio/search', {
            method: 'POST',
            body: JSON.stringify({ table_name: portfolioState.table, query: ui.search.value.trim(), fuzzy: ui.fuzzy.checked, filters: portfolioState.filters }),
        });
        portfolioState.results = data.results || [];
        renderPortfolioResults();
    } catch (error) {
        setPortfolioView('error', error.message);
    }
}

async function selectPortfolioTable(table) {
    if (!table || (table === portfolioState.table && portfolioState.columns.length)) return;
    portfolioState.table = table;
    portfolioState.filters = {};
    portfolioState.columns = [];
    ui.search.value = '';
    ui.fuzzy.checked = false;
    ui.tableName.textContent = table;
    ui.tableHeading.textContent = table;
    renderPortfolioTables();
    renderPortfolioFilters();
    setPortfolioView('loading');
    try {
        const data = await portfolioApi(`/api/portfolio/tables/${encodeURIComponent(table)}/columns`);
        portfolioState.columns = data.columns || [];
        renderPortfolioFilters();
        await runPortfolioQuery();
    } catch (error) {
        setPortfolioView('error', error.message);
    }
}

function beginPortfolioEdit(button) {
    const rowIndex = Number(button.dataset.pEditRow);
    const column = button.dataset.pEditColumn;
    const canonical = portfolioState.results[rowIndex];
    const current = applyDrafts(canonical)[column] ?? '';
    const cell = button.closest('.cell');
    cell.innerHTML = `<div class="cell-editor"><input type="text" value="${pEscape(current)}"><button type="button" class="save-edit" aria-label="Keep local draft">${pIcon('check')}</button><button type="button" class="cancel-edit" aria-label="Cancel">${pIcon('x')}</button></div>`;
    const input = cell.querySelector('input');
    input.focus(); input.select(); pIcons();
    const cancel = () => renderPortfolioResults();
    const save = () => {
        portfolioState.drafts.set(draftKey(canonical, column), input.value);
        renderPortfolioResults();
        pToast('Local draft applied. Canonical Sam remains untouched.');
    };
    cell.querySelector('.save-edit').addEventListener('click', save);
    cell.querySelector('.cancel-edit').addEventListener('click', cancel);
    input.addEventListener('keydown', (event) => { if (event.key === 'Enter') save(); if (event.key === 'Escape') cancel(); });
}

async function enterPortfolio() {
    ui.intro.hidden = true;
    ui.workspace.hidden = false;
    setPortfolioView('loading');
    try {
        const data = await portfolioApi('/api/portfolio/tables');
        portfolioState.tables = data.tables || [];
        renderPortfolioTables();
        await selectPortfolioTable(portfolioState.tables.includes('sam_lore') ? 'sam_lore' : portfolioState.tables[0]);
    } catch (error) {
        setPortfolioView('error', error.message);
    }
}

$p('#enter-portfolio').addEventListener('click', enterPortfolio);
$p('#portfolio-home').addEventListener('click', () => { ui.workspace.hidden = true; ui.intro.hidden = false; });
ui.tableFilter.addEventListener('input', renderPortfolioTables);
ui.tables.addEventListener('click', (event) => selectPortfolioTable(event.target.closest('[data-portfolio-table]')?.dataset.portfolioTable));
ui.searchForm.addEventListener('submit', (event) => { event.preventDefault(); runPortfolioQuery(); });
ui.fuzzy.addEventListener('change', runPortfolioQuery);
ui.refresh.addEventListener('click', runPortfolioQuery);
ui.filters.addEventListener('change', (event) => {
    const select = event.target.closest('[data-portfolio-filter]');
    if (!select) return;
    if (select.value) portfolioState.filters[select.dataset.portfolioFilter] = [select.value];
    else delete portfolioState.filters[select.dataset.portfolioFilter];
    renderPortfolioFilters(); runPortfolioQuery();
});
ui.clearFilters.addEventListener('click', () => { portfolioState.filters = {}; renderPortfolioFilters(); runPortfolioQuery(); });
ui.table.addEventListener('click', (event) => { const button = event.target.closest('[data-p-edit-row]'); if (button) beginPortfolioEdit(button); });
$p('#reset-drafts').addEventListener('click', () => { portfolioState.drafts.clear(); renderPortfolioResults(); pToast('All local drafts cleared. Back to canonical Sam.'); });

document.addEventListener('keydown', (event) => {
    if (event.key === '/' && !ui.workspace.hidden && !/input|textarea|select/i.test(document.activeElement.tagName)) { event.preventDefault(); ui.tableFilter.focus(); }
});

pIcons();
