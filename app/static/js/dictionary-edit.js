/**
 * Dictionary Edit - JavaScript for managing the Strong's transliteration dictionary
 * Handles CRUD operations, filtering, sorting, and bulk actions
 */

// ===== File Upload Handler =====

const uploadInput = document.getElementById('dict-file-input');
const uploadForm = document.getElementById('dict-upload-form');

if (uploadInput && uploadForm) {
    uploadInput.addEventListener('change', () => {
        if (uploadInput.files && uploadInput.files.length) {
            uploadForm.submit();
        }
    });
}

// ===== Toast Notifications =====

const toastContainer = document.getElementById('toast-container');

function showToast(message, type = 'info') {
    if (!toastContainer) return;
    const toast = document.createElement('div');
    toast.className = `toast toast--${type}`;
    toast.textContent = message;
    toastContainer.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('is-visible'));
    setTimeout(() => {
        toast.classList.remove('is-visible');
        setTimeout(() => toast.remove(), 300);
    }, 2500);
}

// ===== API Communication =====

function sendActions(actions) {
    return fetch('/edit_dict', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ actions }),
    })
        .then((response) => {
            if (!response.ok) {
                throw new Error('Request failed. Please try again.');
            }
            return response.json();
        })
        .then((data) => {
            if (!data?.success) {
                throw new Error(data?.error || 'Unable to save changes.');
            }
            return data;
        })
        .catch((error) => {
            console.error('Dictionary action failed', error);
            showToast(error.message || 'Unable to save changes.', 'error');
            return { success: false };
        });
}

// ===== Entry Element Builder =====

function buildEntryElement(strongNumber, translations, color) {
    const entry = document.createElement('div');
    entry.className = 'dict-entry';
    entry.dataset.strong = strongNumber;
    entry.dataset.translations = translations.join(',');
    entry.innerHTML = `
        <label class="entry-select-label">
            <input type="checkbox" class="entry-select" aria-label="Select ${strongNumber}">
        </label>
        <input type="text" value="${strongNumber}" readonly>
        <input type="text" class="translation-input" value="${translations.join(',')}">
        <div class="entry-menu">
            <button type="button" class="action-toggle" aria-expanded="false" aria-haspopup="true" aria-label="Open actions for ${strongNumber}">⋯</button>
            <div class="entry-actions" hidden>
                <div class="entry-actions__row">
                    <label class="sr-only" for="color-${strongNumber}">Color for ${strongNumber}</label>
                    <input id="color-${strongNumber}" type="color" value="${color || '#000000'}" aria-label="Color for ${strongNumber}">
                </div>
                <div class="entry-actions__buttons">
                    <button class="button" data-action="update">Update</button>
                    <button class="button" data-action="reset-color">Reset highlight color</button>
                    <button class="button" data-action="delete">Delete</button>
                </div>
            </div>
        </div>
    `;
    return entry;
}

function getTranslationsFromInput(inputValue) {
    return inputValue
        .split(',')
        .map((value) => value.trim())
        .filter(Boolean);
}

// ===== Main Dictionary Editor =====

(function() {
    const entriesContainer = document.getElementById('dict-entries');
    let entries = Array.from(entriesContainer.querySelectorAll('.dict-entry'));
    const searchBox = document.getElementById('search-box');
    const toggleHebrew = document.getElementById('toggle-hebrew');
    const toggleGreek = document.getElementById('toggle-greek');
    const sortOrderSelect = document.getElementById('sort-order');
    const selectVisibleButton = document.getElementById('select-visible');
    const clearSelectionButton = document.getElementById('clear-selection');
    const bulkDeleteButton = document.getElementById('bulk-delete');
    const bulkResetButton = document.getElementById('bulk-reset');
    const selectionCountLabel = document.getElementById('selection-count');

    let showHebrew = true;
    let showGreek = true;
    let sortOrder = 'asc';
    const selected = new Set();

    // ===== Menu Management =====

    function closeAllMenus(except = null) {
        entriesContainer.querySelectorAll('.entry-actions').forEach((actions) => {
            if (actions === except) return;
            if (!actions.hidden) {
                actions.hidden = true;
                const toggle = actions.closest('.entry-menu')?.querySelector('.action-toggle');
                const parent = actions.closest('.dict-entry');
                if (toggle) toggle.setAttribute('aria-expanded', 'false');
                if (parent) parent.classList.remove('actions-open');
            }
        });
    }

    document.addEventListener('click', (event) => {
        if (!event.target.closest('.entry-menu')) {
            closeAllMenus();
        }
    });

    // ===== Utility Functions =====

    function getStrongNumber(entry) {
        const raw = entry.getAttribute('data-strong') || '';
        const numeric = raw.replace(/^[a-zA-Z]/, '');
        return parseInt(numeric, 10) || 0;
    }

    function matchesSearch(entry) {
        const searchTerm = searchBox.value.toLowerCase();
        if (!searchTerm) return true;
        const strongNumber = entry.getAttribute('data-strong').toLowerCase();
        const translations = (entry.getAttribute('data-translations') || '').toLowerCase();
        return strongNumber.includes(searchTerm) || translations.includes(searchTerm);
    }

    function matchesLanguage(entry) {
        const strongNumber = entry.getAttribute('data-strong') || '';
        const prefix = strongNumber.charAt(0).toUpperCase();
        if (prefix === 'H') return showHebrew;
        if (prefix === 'G') return showGreek;
        return true;
    }

    function updateSelectionUI() {
        const count = selected.size;
        selectionCountLabel.textContent = count ? `${count} selected` : 'No items selected';
        bulkDeleteButton.disabled = count === 0;
        bulkResetButton.disabled = count === 0;
    }

    // ===== Entry Event Handlers =====

    function attachEntryHandlers(entry) {
        const strongNumber = entry.dataset.strong;
        const updateBtn = entry.querySelector('[data-action="update"]');
        const deleteBtn = entry.querySelector('[data-action="delete"]');
        const resetBtn = entry.querySelector('[data-action="reset-color"]');
        const colorInput = entry.querySelector('input[type="color"]');
        const checkbox = entry.querySelector('.entry-select');
        const actionToggle = entry.querySelector('.action-toggle');
        const actionsMenu = entry.querySelector('.entry-actions');
        const translationsInput = entry.querySelector('.translation-input');

        if (actionToggle && actionsMenu) {
            actionToggle.addEventListener('click', (event) => {
                event.stopPropagation();
                const willOpen = actionsMenu.hidden;
                closeAllMenus(willOpen ? actionsMenu : null);
                actionsMenu.hidden = !willOpen;
                actionToggle.setAttribute('aria-expanded', String(willOpen));
                entry.classList.toggle('actions-open', willOpen);
            });
        }

        if (updateBtn) {
            updateBtn.addEventListener('click', () => {
                const translations = getTranslationsFromInput(translationsInput?.value || '');
                const color = colorInput.value;
                sendActions([{ action: 'update', strong_number: strongNumber, translations, color }]).then((data) => {
                    if (data.success) {
                        entry.dataset.translations = translations.join(',');
                        showToast('Entry updated successfully', 'success');
                        renderEntries();
                    }
                });
            });
        }

        if (deleteBtn) {
            deleteBtn.addEventListener('click', () => {
                sendActions([{ action: 'delete', strong_number: strongNumber }]).then((data) => {
                    if (data.success) {
                        entries = entries.filter((node) => node.dataset.strong !== strongNumber);
                        selected.delete(strongNumber);
                        entry.remove();
                        showToast('Entry deleted', 'success');
                        renderEntries();
                    }
                });
            });
        }

        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                sendActions([{ action: 'update', strong_number: strongNumber, color: null }]).then((data) => {
                    if (data.success) {
                        colorInput.value = '#000000';
                        showToast('Highlight color reset', 'success');
                    }
                });
            });
        }

        if (colorInput) {
            colorInput.addEventListener('change', () => {
                sendActions([{ action: 'update', strong_number: strongNumber, color: colorInput.value }]).then((data) => {
                    if (data.success) {
                        showToast('Color updated', 'success');
                    }
                });
            });
        }

        if (checkbox) {
            checkbox.addEventListener('change', (event) => {
                if (event.target.checked) {
                    selected.add(strongNumber);
                } else {
                    selected.delete(strongNumber);
                }
                updateSelectionUI();
            });
        }
    }

    // ===== Rendering =====

    function renderEntries() {
        const sorted = [...entries].sort((a, b) => {
            const aNum = getStrongNumber(a);
            const bNum = getStrongNumber(b);
            return sortOrder === 'asc' ? aNum - bNum : bNum - aNum;
        });

        const fragment = document.createDocumentFragment();

        sorted.forEach((entry) => {
            const strong = entry.dataset.strong;
            const checkbox = entry.querySelector('.entry-select');
            const shouldShow = matchesSearch(entry) && matchesLanguage(entry);
            if (!shouldShow) {
                selected.delete(strong);
            }
            entry.classList.toggle('hidden', !shouldShow);
            if (checkbox) {
                checkbox.checked = selected.has(strong) && shouldShow;
            }
            fragment.appendChild(entry);
        });

        entriesContainer.innerHTML = '';
        entriesContainer.appendChild(fragment);
        updateSelectionUI();
        closeAllMenus();
    }

    function registerEntries() {
        entries.forEach(attachEntryHandlers);
    }

    // ===== Bulk Actions =====

    function handleBulkDelete() {
        const targets = Array.from(selected);
        if (!targets.length) return;
        const actions = targets.map((strong) => ({ action: 'delete', strong_number: strong }));
        sendActions(actions).then((data) => {
            if (data.success) {
                entries = entries.filter((entry) => !selected.has(entry.dataset.strong));
                selected.clear();
                entriesContainer.innerHTML = '';
                entries.forEach((entry) => entriesContainer.appendChild(entry));
                showToast('Selected entries deleted', 'success');
                renderEntries();
            }
        });
    }

    function handleBulkReset() {
        const targets = Array.from(selected);
        if (!targets.length) return;
        const actions = targets.map((strong) => ({ action: 'update', strong_number: strong, color: null }));
        sendActions(actions).then((data) => {
            if (data.success) {
                entries.forEach((entry) => {
                    if (selected.has(entry.dataset.strong)) {
                        const colorInput = entry.querySelector('input[type="color"]');
                        if (colorInput) colorInput.value = '#000000';
                    }
                });
                showToast('Highlight colors reset', 'success');
            }
        });
    }

    function selectVisibleEntries() {
        entries.forEach((entry) => {
            if (!entry.classList.contains('hidden')) {
                selected.add(entry.dataset.strong);
            }
        });
        renderEntries();
    }

    function clearSelection() {
        selected.clear();
        renderEntries();
    }

    // ===== Event Listeners =====

    searchBox.addEventListener('input', renderEntries);

    toggleHebrew.addEventListener('click', () => {
        showHebrew = !showHebrew;
        toggleHebrew.classList.toggle('is-active', showHebrew);
        renderEntries();
    });

    toggleGreek.addEventListener('click', () => {
        showGreek = !showGreek;
        toggleGreek.classList.toggle('is-active', showGreek);
        renderEntries();
    });

    sortOrderSelect.addEventListener('change', (event) => {
        sortOrder = event.target.value;
        renderEntries();
    });

    selectVisibleButton.addEventListener('click', selectVisibleEntries);
    clearSelectionButton.addEventListener('click', clearSelection);
    bulkDeleteButton.addEventListener('click', handleBulkDelete);
    bulkResetButton.addEventListener('click', handleBulkReset);

    // ===== Add New Entry Form =====

    document.getElementById('add-form').addEventListener('submit', function(e) {
        e.preventDefault();
        const strongNumber = document.getElementById('new-strong-number').value.trim();
        const translationsValue = document.getElementById('new-translations').value;
        const translations = getTranslationsFromInput(translationsValue);
        const color = document.getElementById('new-color').value;

        if (!strongNumber) {
            showToast("Strong's number is required", 'error');
            return;
        }

        sendActions([{ action: 'add', strong_number: strongNumber, translations, color }]).then((data) => {
            if (data.success) {
                const entry = buildEntryElement(strongNumber, translations, color);
                entries.push(entry);
                attachEntryHandlers(entry);
                renderEntries();
                showToast('New entry added', 'success');
                document.getElementById('add-form').reset();
                document.getElementById('new-color').value = '#000000';
            }
        });
    });

    // ===== Initialization =====

    registerEntries();
    renderEntries();
})();
