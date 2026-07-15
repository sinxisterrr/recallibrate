const state = {
    dbUrl: '',
    tables: [],
    activeTable: null,
    columns: [],
    results: [],
    query: '',
    fuzzy: false,
    filters: {},
    pendingDeleteIndex: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const elements = {
    connectView: $('#connect-view'),
    workspaceView: $('#workspace-view'),
    connectForm: $('#connect-form'),
    connectBtn: $('#connect-btn'),
    connectError: $('#connect-error'),
    dbUrl: $('#db-url'),
    revealUrl: $('#reveal-url'),
    tableFilter: $('#table-filter'),
    tables: $('#tables'),
    tableCount: $('#table-count'),
    tableName: $('#table-name'),
    tableHeading: $('#table-heading'),
    emptyWorkspace: $('#empty-workspace'),
    tableWorkspace: $('#table-workspace'),
    searchForm: $('#search-form'),
    searchInput: $('#search-input'),
    fuzzyToggle: $('#fuzzy-toggle'),
    refreshBtn: $('#refresh-btn'),
    filterBar: $('#filter-bar'),
    filters: $('#filters'),
    clearFilters: $('#clear-filters'),
    resultCount: $('#result-count'),
    columnCount: $('#column-count'),
    resultsDescription: $('#results-description'),
    resultsTable: $('#results-table'),
    loadingState: $('#loading-state'),
    resultsEmpty: $('#results-empty'),
    resultsError: $('#results-error'),
    resultsErrorMessage: $('#results-error-message'),
    toastRegion: $('#toast-region'),
    deleteDialog: $('#delete-dialog'),
    deleteTableName: $('#delete-table-name'),
};

const textTypes = new Set(['text', 'character varying', 'varchar', 'character', 'char']);
const selectableTypes = new Set([
    ...textTypes,
    'boolean', 'smallint', 'integer', 'bigint', 'numeric', 'decimal',
    'real', 'double precision', 'date', 'timestamp without time zone',
    'timestamp with time zone', 'uuid', 'USER-DEFINED',
]);

function icon(name) {
    return `<i data-lucide="${name}"></i>`;
}

function refreshIcons() {
    if (window.lucide) lucide.createIcons();
}

function escapeHtml(value) {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

function friendlyError(error) {
    const raw = error?.message || 'Something went wrong.';
    if (/fetch|network/i.test(raw)) return 'Recallibrate did not respond. Try again in a moment.';
    if (/password authentication|authentication failed/i.test(raw)) return 'The database rejected those credentials.';
    if (/could not translate host|name or service/i.test(raw)) return 'That database host could not be found.';
    return raw;
}

async function api(path, options = {}) {
    const response = await fetch(path, {
        ...options,
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    });
    let data = {};
    try { data = await response.json(); } catch (_) { /* handled below */ }
    if (!response.ok || data.error) throw new Error(data.detail || data.error || `Request failed (${response.status})`);
    return data;
}

function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('recallibrate-theme', theme);
    const themes = ['light', 'system', 'dark'];
    const index = themes.indexOf(theme);
    $$('.theme-toggle').forEach((toggle) => {
        toggle.querySelectorAll('[data-theme-btn]').forEach((button) => {
            button.setAttribute('aria-pressed', String(button.dataset.themeBtn === theme));
        });
        toggle.querySelector('.theme-pill').style.transform = `translateX(${Math.max(0, index) * 36}px)`;
    });
}

function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `${icon(type === 'error' ? 'circle-alert' : 'circle-check')}<span>${escapeHtml(message)}</span>`;
    elements.toastRegion.appendChild(toast);
    refreshIcons();
    setTimeout(() => toast.remove(), 3600);
}

function setConnectLoading(loading) {
    elements.connectBtn.disabled = loading;
    elements.connectBtn.querySelector('span').textContent = loading ? 'Opening…' : 'Open database';
}

function showWorkspace() {
    elements.connectView.hidden = true;
    elements.workspaceView.hidden = false;
}

function disconnect() {
    Object.assign(state, { dbUrl: '', tables: [], activeTable: null, columns: [], results: [], query: '', fuzzy: false, filters: {} });
    elements.dbUrl.value = '';
    elements.tableFilter.value = '';
    elements.searchInput.value = '';
    elements.connectError.textContent = '';
    elements.workspaceView.hidden = true;
    elements.connectView.hidden = false;
    elements.dbUrl.focus();
}

function renderTables() {
    const needle = elements.tableFilter.value.trim().toLowerCase();
    const visible = state.tables.filter((table) => table.toLowerCase().includes(needle));
    elements.tableCount.textContent = state.tables.length;
    elements.tables.innerHTML = visible.length
        ? visible.map((table) => `
            <button type="button" class="tables-btn ${table === state.activeTable ? 'active' : ''}" data-table="${escapeHtml(table)}">
                ${icon('table-2')}<span>${escapeHtml(table)}</span>${icon('chevron-right').replace('<i ', '<i class="table-chevron" ')}
            </button>`).join('')
        : '<div class="results-empty" style="min-height:120px"><p>No tables found.</p></div>';
    refreshIcons();
}

function setResultsState(mode, message = '') {
    elements.loadingState.hidden = mode !== 'loading';
    elements.resultsEmpty.hidden = mode !== 'empty';
    elements.resultsError.hidden = mode !== 'error';
    elements.resultsTable.hidden = mode !== 'ready';
    if (message) elements.resultsErrorMessage.textContent = message;
}

function renderFilters() {
    elements.filterBar.hidden = true;
    elements.filters.innerHTML = '';
}

function formattedValue(value) {
    if (value === null || value === undefined) return '<span class="cell-null">null</span>';
    if (typeof value === 'boolean') return `<span class="cell-boolean ${value}">${value}</span>`;
    if (typeof value === 'object') return escapeHtml(JSON.stringify(value));
    return escapeHtml(value);
}

function renderResults() {
    elements.resultCount.textContent = state.results.length.toLocaleString();
    elements.columnCount.textContent = state.columns.length.toLocaleString();
    const hasSearch = Boolean(state.query || Object.keys(state.filters).length);
    elements.resultsDescription.textContent = hasSearch
        ? `${state.results.length.toLocaleString()} matching record${state.results.length === 1 ? '' : 's'}`
        : `Showing ${state.results.length.toLocaleString()} current record${state.results.length === 1 ? '' : 's'}`;

    if (!state.results.length) {
        elements.resultsTable.innerHTML = '';
        setResultsState('empty');
        return;
    }

    const columns = state.columns.length ? state.columns.map((column) => column.name) : Object.keys(state.results[0]);
    const hasId = columns.includes('id');
    elements.resultsTable.innerHTML = state.results.map((row, rowIndex) => {
        const fields = columns.map((columnName) => {
            const column = state.columns.find((item) => item.name === columnName);
            const currentValue = row[columnName];
            const canSelect = hasId && columnName !== 'id' && column && selectableTypes.has(column.type) && Array.isArray(column.options) && column.options.length > 0;
            const canWriteText = hasId && columnName !== 'id' && column && textTypes.has(column.type);

            if (canSelect) {
                const current = String(currentValue ?? '');
                const values = column.options.filter((value) => value !== null).map(String);
                if (current && !values.includes(current)) values.unshift(current);
                const options = values.map((value) => `<option value="${escapeHtml(value)}" ${value === current ? 'selected' : ''}>${escapeHtml(value)}</option>`).join('');
                return `<label class="record-field record-field-select">
                    <span class="record-label">${escapeHtml(columnName)}</span>
                    <select data-select-row="${rowIndex}" data-select-column="${escapeHtml(columnName)}">${options}</select>
                </label>`;
            }

            return `<div class="record-field">
                <span class="record-label">${escapeHtml(columnName)}</span>
                <div class="record-field-value"><span class="cell-value" title="${escapeHtml(currentValue ?? 'null')}">${formattedValue(currentValue)}</span>${canWriteText ? `<button type="button" class="edit-cell-btn" data-edit-row="${rowIndex}" data-edit-column="${escapeHtml(columnName)}" aria-label="Edit ${escapeHtml(columnName)}">${icon('pencil')}</button>` : ''}</div>
            </div>`;
        }).join('');
        const identifier = row.id === undefined ? `record ${rowIndex + 1}` : `record #${escapeHtml(row.id)}`;
        return `<article class="record-card">
            <header class="record-card-header"><span>${identifier}</span>${hasId ? `<button type="button" class="delete-row-btn" data-delete-row="${rowIndex}" aria-label="Delete record">${icon('trash-2')}</button>` : ''}</header>
            <div class="record-fields">${fields}</div>
        </article>`;
    }).join('');
    setResultsState('ready');
    refreshIcons();
}

async function searchTable() {
    if (!state.activeTable) return;
    state.query = elements.searchInput.value.trim();
    state.fuzzy = elements.fuzzyToggle.checked;
    setResultsState('loading');
    try {
        const data = await api('/api/database/search', {
            method: 'POST',
            body: JSON.stringify({
                db_url: state.dbUrl,
                table_name: state.activeTable,
                query: state.query,
                filters: state.filters,
                fuzzy: state.fuzzy,
            }),
        });
        state.results = data.results || [];
        renderResults();
    } catch (error) {
        setResultsState('error', friendlyError(error));
    }
}

async function selectTable(table) {
    if (!table || table === state.activeTable) return;
    state.activeTable = table;
    state.columns = [];
    state.results = [];
    state.filters = {};
    elements.searchInput.value = '';
    elements.fuzzyToggle.checked = false;
    elements.tableName.textContent = table;
    elements.tableHeading.textContent = table;
    elements.emptyWorkspace.hidden = true;
    elements.tableWorkspace.hidden = false;
    elements.columnCount.textContent = '—';
    elements.resultCount.textContent = '—';
    renderTables();
    renderFilters();
    setResultsState('loading');

    try {
        const data = await api('/api/database/columns', {
            method: 'POST',
            body: JSON.stringify({ db_url: state.dbUrl, table_name: table }),
        });
        state.columns = data.columns || [];
        renderFilters();
        await searchTable();
    } catch (error) {
        setResultsState('error', friendlyError(error));
    }
}

function beginEdit(button) {
    const rowIndex = Number(button.dataset.editRow);
    const column = button.dataset.editColumn;
    const row = state.results[rowIndex];
    const cell = button.closest('.record-field-value');
    const original = row[column] ?? '';
    cell.innerHTML = `<div class="cell-editor"><input type="text" value="${escapeHtml(original)}" aria-label="New value for ${escapeHtml(column)}"><button type="button" class="save-edit" aria-label="Save">${icon('check')}</button><button type="button" class="cancel-edit" aria-label="Cancel">${icon('x')}</button></div>`;
    const input = cell.querySelector('input');
    input.focus();
    input.select();
    refreshIcons();

    const cancel = () => renderResults();
    cell.querySelector('.cancel-edit').addEventListener('click', cancel);
    cell.querySelector('.save-edit').addEventListener('click', () => saveEdit(rowIndex, column, input.value));
    input.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') saveEdit(rowIndex, column, input.value);
        if (event.key === 'Escape') cancel();
    });
}

async function saveEdit(rowIndex, column, newText) {
    const row = state.results[rowIndex];
    if (!row || row.id === undefined) return;
    try {
        await api('/api/database/record', {
            method: 'PUT',
            body: JSON.stringify({ db_url: state.dbUrl, table_name: state.activeTable, record_id: String(row.id), column_name: column, new_text: newText }),
        });
        row[column] = newText;
        renderResults();
        showToast(`${column} updated`);
    } catch (error) {
        renderResults();
        showToast(friendlyError(error), 'error');
    }
}

function requestDelete(rowIndex) {
    state.pendingDeleteIndex = rowIndex;
    elements.deleteTableName.textContent = state.activeTable;
    elements.deleteDialog.showModal();
}

async function confirmDelete() {
    const rowIndex = state.pendingDeleteIndex;
    const row = state.results[rowIndex];
    state.pendingDeleteIndex = null;
    if (!row || row.id === undefined) return;
    try {
        await api('/api/database/record', {
            method: 'DELETE',
            body: JSON.stringify({ db_url: state.dbUrl, table_name: state.activeTable, record_id: String(row.id) }),
        });
        state.results.splice(rowIndex, 1);
        renderResults();
        showToast('Record deleted');
    } catch (error) {
        showToast(friendlyError(error), 'error');
    }
}

elements.connectForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const dbUrl = elements.dbUrl.value.trim();
    elements.connectError.textContent = '';
    if (!dbUrl) {
        elements.connectError.textContent = 'Enter a PostgreSQL connection URL to continue.';
        elements.dbUrl.focus();
        return;
    }
    setConnectLoading(true);
    try {
        const data = await api('/api/database/tables', {
            method: 'POST',
            body: JSON.stringify({ db_url: dbUrl }),
        });
        state.dbUrl = dbUrl;
        state.tables = (data.tables || []).sort((a, b) => a.localeCompare(b));
        showWorkspace();
        renderTables();
        if (state.tables.length) await selectTable(state.tables[0]);
    } catch (error) {
        elements.connectError.textContent = friendlyError(error);
    } finally {
        setConnectLoading(false);
    }
});

elements.revealUrl.addEventListener('click', () => {
    const reveal = elements.dbUrl.type === 'password';
    elements.dbUrl.type = reveal ? 'text' : 'password';
    elements.revealUrl.setAttribute('aria-pressed', String(reveal));
    elements.revealUrl.innerHTML = icon(reveal ? 'eye-off' : 'eye');
    refreshIcons();
});

$$('[data-theme-btn]').forEach((button) => button.addEventListener('click', () => setTheme(button.dataset.themeBtn)));
elements.tables.addEventListener('click', (event) => selectTable(event.target.closest('[data-table]')?.dataset.table));
elements.tableFilter.addEventListener('input', renderTables);
elements.searchForm.addEventListener('submit', (event) => { event.preventDefault(); searchTable(); });
elements.fuzzyToggle.addEventListener('change', searchTable);
elements.refreshBtn.addEventListener('click', searchTable);
elements.filters.addEventListener('change', (event) => {
    const select = event.target.closest('[data-filter-column]');
    if (!select) return;
    if (select.value) state.filters[select.dataset.filterColumn] = [select.value];
    else delete state.filters[select.dataset.filterColumn];
    renderFilters();
    searchTable();
});
elements.clearFilters.addEventListener('click', () => { state.filters = {}; renderFilters(); searchTable(); });
elements.resultsTable.addEventListener('click', (event) => {
    const edit = event.target.closest('[data-edit-row]');
    const remove = event.target.closest('[data-delete-row]');
    if (edit) beginEdit(edit);
    if (remove) requestDelete(Number(remove.dataset.deleteRow));
});
elements.resultsTable.addEventListener('change', (event) => {
    const select = event.target.closest('[data-select-row]');
    if (select) saveEdit(Number(select.dataset.selectRow), select.dataset.selectColumn, select.value);
});
elements.deleteDialog.addEventListener('close', () => {
    if (elements.deleteDialog.returnValue === 'confirm') confirmDelete();
    else state.pendingDeleteIndex = null;
});
$('#disconnect-btn').addEventListener('click', disconnect);
$('#home-btn').addEventListener('click', disconnect);

document.addEventListener('keydown', (event) => {
    if (event.key === '/' && !elements.workspaceView.hidden && !/input|textarea|select/i.test(document.activeElement.tagName)) {
        event.preventDefault();
        elements.tableFilter.focus();
    }
});

setTheme(localStorage.getItem('recallibrate-theme') || 'system');
refreshIcons();
