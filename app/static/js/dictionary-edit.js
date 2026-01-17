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
                    <label for="color-${strongNumber}">Highlight color:</label>
                    <input id="color-${strongNumber}" type="color" value="${color || '#000000'}" aria-label="Color for ${strongNumber}">
                </div>
                <div class="entry-actions__buttons">
                    <button class="button" data-action="update">Save</button>
                    <button class="button" data-action="reset-color">Reset Color</button>
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
    if (!entriesContainer) return;

    let entries = Array.from(entriesContainer.querySelectorAll('.dict-entry'));
    const searchBox = document.getElementById('search-box');
    const toggleHebrew = document.getElementById('toggle-hebrew');
    const toggleGreek = document.getElementById('toggle-greek');
    const sortOrderSelect = document.getElementById('sort-order');
    const selectAllButton = document.getElementById('select-all');
    const clearSelectionButton = document.getElementById('clear-selection');
    const bulkDeleteButton = document.getElementById('bulk-delete');
    const bulkResetButton = document.getElementById('bulk-reset');
    const selectionCountLabel = document.getElementById('selection-count');
    const filterStatus = document.getElementById('filter-status');
    const visibleCountEl = document.getElementById('visible-count');
    const totalCountEl = document.getElementById('total-count');
    const emptyState = document.getElementById('dict-empty');

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
        if (!searchBox) return true;
        const searchTerm = searchBox.value.toLowerCase().trim();
        if (!searchTerm) return true;
        const strongNumber = (entry.getAttribute('data-strong') || '').toLowerCase();
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
        if (selectionCountLabel) {
            selectionCountLabel.textContent = `${count} selected`;
        }
        if (bulkDeleteButton) bulkDeleteButton.disabled = count === 0;
        if (bulkResetButton) bulkResetButton.disabled = count === 0;

        // Update visual selection state on entries
        entries.forEach((entry) => {
            const isSelected = selected.has(entry.dataset.strong);
            entry.classList.toggle('is-selected', isSelected);
        });
    }

    function updateFilterStatus(visibleCount, totalCount) {
        if (!filterStatus || !visibleCountEl || !totalCountEl) return;

        const hasFilters = searchBox.value.trim() || !showHebrew || !showGreek;

        if (hasFilters && visibleCount !== totalCount) {
            filterStatus.style.display = 'block';
            visibleCountEl.textContent = visibleCount;
            totalCountEl.textContent = totalCount;
        } else {
            filterStatus.style.display = 'none';
        }

        // Show empty state if no visible entries
        if (emptyState) {
            emptyState.style.display = visibleCount === 0 && totalCount > 0 ? 'block' : 'none';
        }
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
                        showToast('Entry saved', 'success');
                        closeAllMenus();
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
                        showToast('Color reset', 'success');
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
        let visibleCount = 0;

        sorted.forEach((entry) => {
            const strong = entry.dataset.strong;
            const checkbox = entry.querySelector('.entry-select');
            const shouldShow = matchesSearch(entry) && matchesLanguage(entry);

            if (shouldShow) {
                visibleCount++;
            } else {
                selected.delete(strong);
            }

            entry.classList.toggle('hidden', !shouldShow);
            entry.classList.toggle('is-selected', selected.has(strong) && shouldShow);

            if (checkbox) {
                checkbox.checked = selected.has(strong) && shouldShow;
            }
            fragment.appendChild(entry);
        });

        entriesContainer.innerHTML = '';
        entriesContainer.appendChild(fragment);
        updateSelectionUI();
        updateFilterStatus(visibleCount, entries.length);
        closeAllMenus();
    }

    function registerEntries() {
        entries.forEach(attachEntryHandlers);
    }

    // ===== Bulk Actions =====

    function handleBulkDelete() {
        const targets = Array.from(selected);
        if (!targets.length) return;

        if (!confirm(`Delete ${targets.length} selected entries?`)) return;

        const actions = targets.map((strong) => ({ action: 'delete', strong_number: strong }));
        sendActions(actions).then((data) => {
            if (data.success) {
                entries = entries.filter((entry) => !selected.has(entry.dataset.strong));
                selected.clear();
                showToast(`${targets.length} entries deleted`, 'success');
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
                showToast(`${targets.length} colors reset`, 'success');
            }
        });
    }

    function selectAllEntries() {
        // Select all visible entries
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

    if (searchBox) {
        searchBox.addEventListener('input', renderEntries);
    }

    if (toggleHebrew) {
        toggleHebrew.addEventListener('click', () => {
            showHebrew = !showHebrew;
            toggleHebrew.classList.toggle('is-active', showHebrew);
            toggleHebrew.setAttribute('aria-pressed', String(showHebrew));
            renderEntries();
        });
    }

    if (toggleGreek) {
        toggleGreek.addEventListener('click', () => {
            showGreek = !showGreek;
            toggleGreek.classList.toggle('is-active', showGreek);
            toggleGreek.setAttribute('aria-pressed', String(showGreek));
            renderEntries();
        });
    }

    if (sortOrderSelect) {
        sortOrderSelect.addEventListener('change', (event) => {
            sortOrder = event.target.value;
            renderEntries();
        });
    }

    if (selectAllButton) {
        selectAllButton.addEventListener('click', selectAllEntries);
    }
    if (clearSelectionButton) {
        clearSelectionButton.addEventListener('click', clearSelection);
    }
    if (bulkDeleteButton) {
        bulkDeleteButton.addEventListener('click', handleBulkDelete);
    }
    if (bulkResetButton) {
        bulkResetButton.addEventListener('click', handleBulkReset);
    }

    // ===== Add New Entry Form =====

    const addForm = document.getElementById('add-form');
    if (addForm) {
        addForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const strongNumberInput = document.getElementById('new-strong-number');
            const translationsInput = document.getElementById('new-translations');
            const colorInput = document.getElementById('new-color');

            const strongNumber = strongNumberInput.value.trim().toUpperCase();
            const translations = getTranslationsFromInput(translationsInput.value);
            const color = colorInput.value;

            if (!strongNumber) {
                showToast("Strong's number is required", 'error');
                return;
            }

            // Validate Strong's number format
            if (!/^[HG]\d+$/i.test(strongNumber)) {
                showToast("Invalid format. Use H#### or G#### (e.g., H1234)", 'error');
                return;
            }

            if (!translations.length) {
                showToast("At least one translation is required", 'error');
                return;
            }

            // Check for duplicate
            const exists = entries.some((e) => e.dataset.strong.toUpperCase() === strongNumber);
            if (exists) {
                showToast(`${strongNumber} already exists`, 'error');
                return;
            }

            sendActions([{ action: 'add', strong_number: strongNumber, translations, color }]).then((data) => {
                if (data.success) {
                    const entry = buildEntryElement(strongNumber, translations, color);
                    entries.push(entry);
                    attachEntryHandlers(entry);
                    renderEntries();
                    showToast(`${strongNumber} added`, 'success');
                    addForm.reset();
                    colorInput.value = '#000000';
                }
            });
        });
    }

    // ===== Initialization =====

    registerEntries();
    renderEntries();
})();
