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
const portfolioSelectFields = new Set(['category', 'energy', 'status', 'stack', 'confidence', 'intensity', 'negotiable', 'kind', 'current']);

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
    ui.filterBar.hidden = true;
    ui.filters.innerHTML = '';
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
    ui.table.innerHTML = rows.map((row, rowIndex) => {
        const canonical = portfolioState.results[rowIndex];
        const bodyFields = [];
        const optionFields = [];
        names.filter((name) => name !== 'id').forEach((name) => {
            const column = portfolioState.columns.find((item) => item.name === name);
            const drafted = portfolioState.drafts.has(draftKey(canonical, name));
            const canSelect = portfolioSelectFields.has(name) && column && Array.isArray(column.options) && column.options.length > 0;
            const canEditText = name !== 'id' && column && portfolioTextTypes.has(column.type);

            if (canSelect) {
                const current = String(row[name] ?? '');
                const values = column.options.filter((value) => value !== null).map(String);
                if (current && !values.includes(current)) values.unshift(current);
                const options = values.map((value) => `<option value="${pEscape(value)}" ${value === current ? 'selected' : ''}>${pEscape(value)}</option>`).join('');
                optionFields.push(`<label class="record-option ${drafted ? 'local-draft' : ''}"><span class="record-label">${pEscape(name)}</span><select data-p-select-row="${rowIndex}" data-p-select-column="${pEscape(name)}">${options}</select></label>`);
                return;
            }

            bodyFields.push(`<div class="record-text-field ${drafted ? 'local-draft' : ''}"><span class="record-label">${pEscape(name)}</span><div class="record-field-value"><span class="cell-value" title="${pEscape(row[name] ?? 'null')}">${pValue(row[name])}</span>${canEditText ? `<button type="button" class="edit-cell-btn" data-p-edit-row="${rowIndex}" data-p-edit-column="${pEscape(name)}" aria-label="Edit ${pEscape(name)} locally">${pIcon('pencil')}</button>` : ''}</div></div>`);
        });
        return `<article class="record-card">
            <header class="record-card-header"><span>record #${pEscape(row.id ?? rowIndex + 1)}</span></header>
            ${bodyFields.length ? `<div class="record-body">${bodyFields.join('')}</div>` : ''}
            ${bodyFields.length && optionFields.length ? '<div class="record-divider" aria-hidden="true"></div>' : ''}
            ${optionFields.length ? `<div class="record-options">${optionFields.join('')}</div>` : ''}
        </article>`;
    }).join('');
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
    const cell = button.closest('.record-field-value');
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
ui.table.addEventListener('change', (event) => {
    const select = event.target.closest('[data-p-select-row]');
    if (!select) return;
    const rowIndex = Number(select.dataset.pSelectRow);
    const column = select.dataset.pSelectColumn;
    portfolioState.drafts.set(draftKey(portfolioState.results[rowIndex], column), select.value);
    renderPortfolioResults();
    pToast('Local draft applied. Canonical Sam remains untouched.');
});
$p('#reset-drafts').addEventListener('click', () => { portfolioState.drafts.clear(); renderPortfolioResults(); pToast('All local drafts cleared. Back to canonical Sam.'); });

document.addEventListener('keydown', (event) => {
    if (event.key === '/' && !ui.workspace.hidden && !/input|textarea|select/i.test(document.activeElement.tagName)) { event.preventDefault(); ui.tableFilter.focus(); }
});

pIcons();
