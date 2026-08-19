const state = {
    user: null,
    databaseLabel: null,
    databases: [],
    activeDatabaseId: null,
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
    signedOutPanel: $('#signed-out-panel'),
    signedInPanel: $('#signed-in-panel'),
    connectionTabs: $$('[data-connection-tab]'),
    discordConnectionPanel: $('#discord-connection-panel'),
    authError: $('#auth-error'),
    guestDatabaseForm: $('#guest-database-form'),
    guestDatabaseUrl: $('#guest-database-url'),
    guestConnectError: $('#guest-connect-error'),
    accountAvatar: $('#account-avatar'),
    accountName: $('#account-name'),
    accountId: $('#account-id'),
    logoutBtn: $('#logout-btn'),
    connectError: $('#connect-error'),
    assignmentStatus: $('#assignment-status'),
    databaseConnectForm: $('#database-connect-form'),
    databaseUrl: $('#database-url'),
    runtimeConnectForm: $('#runtime-connect-form'),
    runtimeUrl: $('#runtime-url'),
    runtimePairing: $('#runtime-pairing'),
    runtimeCode: $('#runtime-code'),
    runtimePairingStatus: $('#runtime-pairing-status'),
    connectionDivider: $('#connection-divider'),
    databaseSelect: $('#database-select'),
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
    sessionUser: $('#session-user'),
    sessionDatabase: $('#session-database'),
    connectionLabel: $('#connection-label'),
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
    if (!response.ok || data.error) {
        const error = new Error(data.detail || data.error || `Request failed (${response.status})`);
        error.status = response.status;
        throw error;
    }
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

function showWorkspace() {
    elements.connectView.hidden = true;
    elements.workspaceView.hidden = false;
}

function showAssignmentView() {
    Object.assign(state, { tables: [], activeTable: null, columns: [], results: [], query: '', fuzzy: false, filters: {} });
    elements.tableFilter.value = '';
    elements.searchInput.value = '';
    elements.connectError.textContent = '';
    elements.workspaceView.hidden = true;
    elements.connectView.hidden = false;
}

function renderAccount(user, database = {}) {
    state.user = user;
    state.databaseLabel = database.label || null;
    elements.signedOutPanel.hidden = true;
    elements.signedInPanel.hidden = false;
    elements.accountName.textContent = user.display_name || user.username;
    elements.accountId.textContent = user.is_guest ? 'Standalone encrypted session' : `Discord ${user.discord_id}`;
    elements.accountAvatar.innerHTML = user.avatar_url
        ? `<img src="${escapeHtml(user.avatar_url)}" alt="">`
        : icon('user');
    elements.sessionUser.firstChild.textContent = `${user.display_name || user.username}\n`;
    elements.sessionDatabase.textContent = database.label || 'Awaiting assignment';
    elements.connectionLabel.textContent = database.label || 'PostgreSQL';
    elements.assignmentStatus.textContent = database.connected
        ? `${database.label || 'Your database'} is ready.`
        : 'No database is connected yet. Paste its PostgreSQL URL below.';
    elements.databaseConnectForm.hidden = database.connected;
    elements.runtimeConnectForm.hidden = database.connected;
    elements.connectionDivider.hidden = database.connected;
    refreshIcons();
}

function setConnectionMethod(method) {
    const showDatabase = method === 'database';
    elements.discordConnectionPanel.hidden = showDatabase;
    elements.guestDatabaseForm.hidden = !showDatabase;
    elements.connectionTabs.forEach((tab) => {
        const selected = tab.dataset.connectionTab === method;
        tab.classList.toggle('active', selected);
        tab.setAttribute('aria-selected', String(selected));
        tab.tabIndex = selected ? 0 : -1;
    });
    if (showDatabase) requestAnimationFrame(() => elements.guestDatabaseUrl.focus());
    refreshIcons();
}

function showCallbackError() {
    const url = new URL(window.location.href);
    const errorCode = url.searchParams.get('auth_error');
    const messages = {
        discord_login: "Discord couldn't finish that login. Please try again.",
        discord_login_failed: "Discord rejected the login exchange. Please try again.",
        discord_invalid_client: "Discord rejected Recallibrate's application credentials. Check the OAuth2 client secret.",
        discord_invalid_grant: 'That Discord authorization expired or was already used. Please start again.',
        discord_request_blocked: 'Discord blocked the server request before processing the login. Please try again after this deployment refreshes.',
        discord_not_invited: 'This Discord account is not currently allowed to use Recallibrate.',
        discord_unavailable: 'Discord could not be reached. Please try again in a moment.',
        discord_not_configured: 'Discord login is not completely configured on this deployment.',
    };
    if (!messages[errorCode]) return;
    elements.authError.querySelector('span').textContent = messages[errorCode];
    elements.authError.hidden = false;
    url.searchParams.delete('auth_error');
    window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
    refreshIcons();
}

function renderDatabaseChoices() {
    elements.databaseSelect.innerHTML = state.databases.map((database) =>
        `<option value="${escapeHtml(database.id)}" ${database.id === state.activeDatabaseId ? 'selected' : ''}>${escapeHtml(database.label)}</option>`
    ).join('');
    elements.databaseSelect.closest('label').hidden = state.databases.length < 2;
}

async function logout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    window.location.assign('/');
}

async function connectDatabase(event) {
    event.preventDefault();
    const button = elements.databaseConnectForm.querySelector('button[type="submit"]');
    button.disabled = true;
    elements.connectError.textContent = '';
    try {
        await api('/api/account/database', {
            method: 'PUT',
            body: JSON.stringify({ db_url: elements.databaseUrl.value.trim() }),
        });
        elements.databaseUrl.value = '';
        await bootstrap();
    } catch (error) {
        elements.connectError.textContent = friendlyError(error);
    } finally {
        button.disabled = false;
    }
}

async function connectGuestDatabase(event) {
    event.preventDefault();
    const button = elements.guestDatabaseForm.querySelector('button[type="submit"]');
    button.disabled = true;
    elements.guestConnectError.textContent = '';
    try {
        await api('/api/auth/database', {
            method: 'POST',
            body: JSON.stringify({ db_url: elements.guestDatabaseUrl.value.trim() }),
        });
        elements.guestDatabaseUrl.value = '';
        await bootstrap();
    } catch (error) {
        elements.guestConnectError.textContent = friendlyError(error);
    } finally {
        button.disabled = false;
    }
}

async function connectRuntime(event) {
    event.preventDefault();
    const button = elements.runtimeConnectForm.querySelector('button[type="submit"]');
    button.disabled = true;
    elements.connectError.textContent = '';
    try {
        const pairing = await api('/api/runtime/pair/start', {
            method: 'POST',
            body: JSON.stringify({ endpoint: elements.runtimeUrl.value.trim() }),
        });
        elements.runtimeCode.textContent = pairing.code;
        elements.runtimePairing.hidden = false;
        elements.runtimePairingStatus.textContent = 'Waiting for Sage…';
        refreshIcons();
        await waitForRuntimePairing(pairing.id);
    } catch (error) {
        elements.connectError.textContent = friendlyError(error);
    } finally {
        button.disabled = false;
    }
}

async function waitForRuntimePairing(pairingId) {
    const deadline = Date.now() + 10 * 60 * 1000;
    while (Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        const pairing = await api(`/api/runtime/pair/status?id=${encodeURIComponent(pairingId)}`);
        if (pairing.status === 'connected') {
            elements.runtimePairingStatus.textContent = 'Connected securely.';
            await bootstrap();
            return;
        }
        if (pairing.status === 'failed') {
            throw new Error(pairing.error || 'Sage could not complete the pairing.');
        }
        elements.runtimePairingStatus.textContent = pairing.status === 'claiming' ? 'Verifying Sage and its database…' : 'Waiting for Sage…';
    }
    throw new Error('That pairing code expired. Generate a new one and try again.');
}

async function openSavedDatabase(databaseId = state.activeDatabaseId) {
    const selected = state.databases.find((database) => database.id === databaseId) || state.databases[0];
    if (!selected) return showAssignmentView();
    state.activeDatabaseId = selected.id;
    state.databaseLabel = selected.label;
    elements.sessionDatabase.textContent = selected.label;
    elements.connectionLabel.textContent = selected.label;
    renderDatabaseChoices();
    const data = await api('/api/database/tables', {
        method: 'POST',
        body: JSON.stringify({ database_id: selected.id }),
    });
    state.tables = (data.tables || []).sort((a, b) => a.localeCompare(b));
    showWorkspace();
    renderTables();
    if (state.tables.length) await selectTable(state.tables[0]);
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
        const bodyFields = [];
        const optionFields = [];
        columns.filter((columnName) => columnName !== 'id').forEach((columnName) => {
            const column = state.columns.find((item) => item.name === columnName);
            const currentValue = row[columnName];
            const canSelect = hasId && columnName !== 'id' && column && selectableTypes.has(column.type) && Array.isArray(column.options) && column.options.length > 0;
            const canWriteText = hasId && columnName !== 'id' && column && textTypes.has(column.type);

            if (canSelect) {
                const current = String(currentValue ?? '');
                const values = column.options.filter((value) => value !== null).map(String);
                if (current && !values.includes(current)) values.unshift(current);
                const options = values.map((value) => `<option value="${escapeHtml(value)}" ${value === current ? 'selected' : ''}>${escapeHtml(value)}</option>`).join('');
                optionFields.push(`<label class="record-option">
                    <span class="record-label">${escapeHtml(columnName)}</span>
                    <select data-select-row="${rowIndex}" data-select-column="${escapeHtml(columnName)}">${options}</select>
                </label>`);
                return;
            }

            bodyFields.push(`<div class="record-text-field">
                <span class="record-label">${escapeHtml(columnName)}</span>
                <div class="record-field-value"><span class="cell-value" title="${escapeHtml(currentValue ?? 'null')}">${formattedValue(currentValue)}</span>${canWriteText ? `<button type="button" class="edit-cell-btn" data-edit-row="${rowIndex}" data-edit-column="${escapeHtml(columnName)}" aria-label="Edit ${escapeHtml(columnName)}">${icon('pencil')}</button>` : ''}</div>
            </div>`);
        });
        const identifier = row.id === undefined ? `record ${rowIndex + 1}` : `record #${escapeHtml(row.id)}`;
        return `<article class="record-card">
            <header class="record-card-header"><span>${identifier}</span>${hasId ? `<button type="button" class="delete-row-btn" data-delete-row="${rowIndex}" aria-label="Delete record">${icon('trash-2')}</button>` : ''}</header>
            ${bodyFields.length ? `<div class="record-body">${bodyFields.join('')}</div>` : ''}
            ${bodyFields.length && optionFields.length ? '<div class="record-divider" aria-hidden="true"></div>' : ''}
            ${optionFields.length ? `<div class="record-options">${optionFields.join('')}</div>` : ''}
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
                table_name: state.activeTable,
                database_id: state.activeDatabaseId,
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
            body: JSON.stringify({ table_name: table, database_id: state.activeDatabaseId }),
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
            body: JSON.stringify({ database_id: state.activeDatabaseId, table_name: state.activeTable, record_id: String(row.id), column_name: column, new_text: newText }),
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
            body: JSON.stringify({ database_id: state.activeDatabaseId, table_name: state.activeTable, record_id: String(row.id) }),
        });
        state.results.splice(rowIndex, 1);
        renderResults();
        showToast('Record deleted');
    } catch (error) {
        showToast(friendlyError(error), 'error');
    }
}

$$('[data-theme-btn]').forEach((button) => button.addEventListener('click', () => setTheme(button.dataset.themeBtn)));
elements.connectionTabs.forEach((tab) => tab.addEventListener('click', () => setConnectionMethod(tab.dataset.connectionTab)));
elements.tables.addEventListener('click', (event) => selectTable(event.target.closest('[data-table]')?.dataset.table));
elements.tableFilter.addEventListener('input', renderTables);
elements.databaseSelect.addEventListener('change', async () => {
    Object.assign(state, { tables: [], activeTable: null, columns: [], results: [], query: '', fuzzy: false, filters: {} });
    elements.searchInput.value = '';
    await openSavedDatabase(elements.databaseSelect.value);
});
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
elements.logoutBtn.addEventListener('click', logout);
elements.databaseConnectForm.addEventListener('submit', connectDatabase);
elements.guestDatabaseForm.addEventListener('submit', connectGuestDatabase);
elements.runtimeConnectForm.addEventListener('submit', connectRuntime);
$('#disconnect-btn').addEventListener('click', logout);
$('#home-btn').addEventListener('click', () => window.location.assign('/'));

document.addEventListener('keydown', (event) => {
    if (event.key === '/' && !elements.workspaceView.hidden && !/input|textarea|select/i.test(document.activeElement.tagName)) {
        event.preventDefault();
        elements.tableFilter.focus();
    }
});

setTheme(localStorage.getItem('recallibrate-theme') || 'system');
setConnectionMethod('discord');
showCallbackError();
refreshIcons();

async function bootstrap() {
    try {
        const data = await api('/api/auth/me');
        state.databases = data.databases || [];
        state.activeDatabaseId = state.databases[0]?.id || null;
        renderAccount(data.user, data.database);
        if (data.database?.connected) await openSavedDatabase();
        else showAssignmentView();
    } catch (error) {
        if (error.status === 401) {
            elements.signedOutPanel.hidden = false;
            elements.signedInPanel.hidden = true;
            return;
        }
        elements.signedOutPanel.hidden = true;
        elements.signedInPanel.hidden = false;
        elements.connectError.textContent = friendlyError(error);
    }
}

bootstrap();
