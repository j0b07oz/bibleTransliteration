/**
 * Chapter View - Main JavaScript for Bible chapter display
 * Handles context options, phonetic device detection, literary overlays, and navigation
 */

document.addEventListener('DOMContentLoaded', function() {
    // Configuration from template
    const initialContextOptions = window.CONTEXT_DEFAULTS || {};
    const contextOptions = Object.assign({}, initialContextOptions);
    const fromHeatmap = window.FROM_HEATMAP || false;
    const focusStrong = window.FOCUS_STRONG || null;
    const activeUnits = window.ACTIVE_UNITS || [];
    const heatmapBase = window.HEATMAP_URL || "/heatmap";

    // DOM elements
    const bookInput = document.getElementById('book');
    const chapterInput = document.getElementById('chapter');
    const goButton = document.getElementById('go-button');
    const contextMenuButton = document.getElementById('context-menu-button');
    const contextDropdown = document.getElementById('context-dropdown');
    const contextMenu = document.getElementById('context-menu');

    // State
    const storageKey = 'literaryContextOptions';
    let overlayResizeObserver = null;

    // ===== Utility Functions =====

    function scheduleOverlayRender() {
        window.requestAnimationFrame(renderOverlay);
    }

    function ensureOverlayObserver() {
        if (!window.ResizeObserver || overlayResizeObserver) return;
        const verseList = document.querySelector('.verse-list');
        if (!verseList) return;
        overlayResizeObserver = new ResizeObserver(() => scheduleOverlayRender());
        overlayResizeObserver.observe(verseList);
    }

    // ===== Context Options Management =====

    function loadSavedOptions() {
        try {
            const saved = JSON.parse(localStorage.getItem(storageKey));
            if (saved && typeof saved === 'object') {
                Object.assign(contextOptions, saved);
            }
        } catch (err) {
            console.warn('Unable to read saved context options', err);
        }
        if (fromHeatmap) {
            contextOptions.repeats = false;
            contextOptions.phonetics = false;
            persistOptions();
        }
    }

    function persistOptions() {
        try {
            localStorage.setItem(storageKey, JSON.stringify(contextOptions));
        } catch (err) {
            console.warn('Unable to save context options', err);
        }
    }

    // ===== Book Data and Validation =====

    const bookData = window.BOOK_DATA || [];
    const bookNames = bookData.map(b => b.name);
    const bookChapterMap = {};
    bookData.forEach(b => { bookChapterMap[b.name.toLowerCase()] = { name: b.name, chapters: b.chapters }; });

    const bookValidation = document.getElementById('book-validation');
    const chapterValidation = document.getElementById('chapter-validation');
    const autocompleteList = document.getElementById('book-autocomplete');

    let selectedAutocompleteIndex = -1;
    let currentSuggestions = [];

    /**
     * Calculate Levenshtein distance for fuzzy matching
     */
    function levenshteinDistance(a, b) {
        if (!a || !b) return Math.max((a || '').length, (b || '').length);
        const aLower = a.toLowerCase();
        const bLower = b.toLowerCase();
        const dp = Array.from({ length: bLower.length + 1 }, (_, i) => i);
        for (let i = 1; i <= aLower.length; i++) {
            let prev = dp[0];
            dp[0] = i;
            for (let j = 1; j <= bLower.length; j++) {
                const temp = dp[j];
                dp[j] = Math.min(
                    dp[j] + 1,
                    dp[j - 1] + 1,
                    prev + (aLower[i - 1] === bLower[j - 1] ? 0 : 1)
                );
                prev = temp;
            }
        }
        return dp[bLower.length];
    }

    /**
     * Find matching books with fuzzy search support
     */
    function findMatchingBooks(query) {
        if (!query) return [];
        const q = query.toLowerCase().trim();

        // Exact match (case-insensitive)
        const exactMatch = bookData.find(b => b.name.toLowerCase() === q);
        if (exactMatch) return [exactMatch];

        // Prefix matches (prioritized)
        const prefixMatches = bookData.filter(b => b.name.toLowerCase().startsWith(q));

        // Contains matches
        const containsMatches = bookData.filter(b =>
            !b.name.toLowerCase().startsWith(q) && b.name.toLowerCase().includes(q)
        );

        // Fuzzy matches for spelling mistakes (Levenshtein distance <= 2)
        const fuzzyMatches = bookData.filter(b => {
            const name = b.name.toLowerCase();
            if (name.startsWith(q) || name.includes(q)) return false;
            const distance = levenshteinDistance(q, name);
            // Allow more tolerance for longer input
            const maxDistance = Math.min(2, Math.floor(q.length / 2) + 1);
            return distance <= maxDistance;
        }).sort((a, b) => {
            const distA = levenshteinDistance(q, a.name.toLowerCase());
            const distB = levenshteinDistance(q, b.name.toLowerCase());
            return distA - distB;
        });

        // Combine and limit results
        return [...prefixMatches, ...containsMatches, ...fuzzyMatches].slice(0, 8);
    }

    /**
     * Validate book name and return validation result
     */
    function validateBook(bookName) {
        if (!bookName || !bookName.trim()) {
            return { valid: false, message: '', book: null };
        }
        const normalized = bookName.trim().toLowerCase();
        const bookInfo = bookChapterMap[normalized];
        if (bookInfo) {
            return { valid: true, message: '', book: bookInfo };
        }
        // Check for close matches to suggest
        const suggestions = findMatchingBooks(bookName);
        if (suggestions.length > 0) {
            return {
                valid: false,
                message: `Did you mean "${suggestions[0].name}"?`,
                book: null,
                suggestions
            };
        }
        return { valid: false, message: 'Unknown book name', book: null };
    }

    /**
     * Validate chapter number for a given book
     */
    function validateChapter(bookInfo, chapterStr) {
        if (!bookInfo) {
            return { valid: false, message: '' };
        }
        if (!chapterStr || chapterStr.trim() === '') {
            return { valid: false, message: '' };
        }
        const chapter = parseInt(chapterStr, 10);
        if (isNaN(chapter) || chapter < 1) {
            return { valid: false, message: 'Chapter must be a positive number' };
        }
        if (chapter > bookInfo.chapters) {
            const chapterWord = bookInfo.chapters === 1 ? 'chapter' : 'chapters';
            return { valid: false, message: `${bookInfo.name} only has ${bookInfo.chapters} ${chapterWord}` };
        }
        return { valid: true, message: `Chapter ${chapter} of ${bookInfo.chapters}` };
    }

    /**
     * Update validation display and button state
     */
    function updateValidation() {
        const bookResult = validateBook(bookInput.value);
        const chapterResult = validateChapter(bookResult.book, chapterInput.value);

        // Update book validation display
        if (bookValidation) {
            bookValidation.textContent = bookResult.message;
            bookValidation.classList.toggle('validation-message--error', !bookResult.valid && bookResult.message);
            bookValidation.classList.toggle('validation-message--success', bookResult.valid);
        }

        // Update chapter validation display
        if (chapterValidation) {
            chapterValidation.textContent = chapterResult.message;
            chapterValidation.classList.toggle('validation-message--error', !chapterResult.valid && chapterResult.message);
            chapterValidation.classList.toggle('validation-message--success', chapterResult.valid && chapterResult.message);
        }

        // Enable Go button only when both are valid
        const bothValid = bookResult.valid && chapterResult.valid;
        goButton.disabled = !bothValid;

        return { bookResult, chapterResult, bothValid };
    }

    // ===== Autocomplete Functions =====

    function showAutocomplete(suggestions) {
        if (!autocompleteList) return;
        currentSuggestions = suggestions;
        selectedAutocompleteIndex = -1;

        if (suggestions.length === 0) {
            hideAutocomplete();
            return;
        }

        autocompleteList.innerHTML = '';
        suggestions.forEach((book, index) => {
            const li = document.createElement('li');
            li.className = 'autocomplete-item';
            li.setAttribute('role', 'option');
            li.setAttribute('aria-selected', 'false');
            li.dataset.index = index;

            const nameSpan = document.createElement('span');
            nameSpan.className = 'autocomplete-item__name';
            nameSpan.textContent = book.name;

            const chaptersSpan = document.createElement('span');
            chaptersSpan.className = 'autocomplete-item__chapters';
            chaptersSpan.textContent = `${book.chapters} ch`;

            li.appendChild(nameSpan);
            li.appendChild(chaptersSpan);

            li.addEventListener('mousedown', (e) => {
                e.preventDefault();
                selectAutocompleteItem(index);
            });

            li.addEventListener('mouseenter', () => {
                highlightAutocompleteItem(index);
            });

            autocompleteList.appendChild(li);
        });

        autocompleteList.classList.add('is-visible');
        bookInput.setAttribute('aria-expanded', 'true');
    }

    function hideAutocomplete() {
        if (!autocompleteList) return;
        autocompleteList.classList.remove('is-visible');
        autocompleteList.innerHTML = '';
        bookInput.setAttribute('aria-expanded', 'false');
        currentSuggestions = [];
        selectedAutocompleteIndex = -1;
    }

    function highlightAutocompleteItem(index) {
        const items = autocompleteList.querySelectorAll('.autocomplete-item');
        items.forEach((item, i) => {
            const isSelected = i === index;
            item.classList.toggle('is-highlighted', isSelected);
            item.setAttribute('aria-selected', isSelected ? 'true' : 'false');
        });
        selectedAutocompleteIndex = index;
    }

    function selectAutocompleteItem(index) {
        if (index < 0 || index >= currentSuggestions.length) return;
        const book = currentSuggestions[index];
        bookInput.value = book.name;
        hideAutocomplete();
        updateValidation();
        // Focus chapter input for convenience
        chapterInput.focus();
    }

    function handleAutocompleteKeydown(e) {
        if (!autocompleteList.classList.contains('is-visible')) return;

        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                highlightAutocompleteItem(
                    selectedAutocompleteIndex < currentSuggestions.length - 1
                        ? selectedAutocompleteIndex + 1
                        : 0
                );
                break;
            case 'ArrowUp':
                e.preventDefault();
                highlightAutocompleteItem(
                    selectedAutocompleteIndex > 0
                        ? selectedAutocompleteIndex - 1
                        : currentSuggestions.length - 1
                );
                break;
            case 'Enter':
                if (selectedAutocompleteIndex >= 0) {
                    e.preventDefault();
                    selectAutocompleteItem(selectedAutocompleteIndex);
                }
                break;
            case 'Escape':
                hideAutocomplete();
                break;
            case 'Tab':
                if (selectedAutocompleteIndex >= 0) {
                    selectAutocompleteItem(selectedAutocompleteIndex);
                } else if (currentSuggestions.length > 0) {
                    selectAutocompleteItem(0);
                }
                hideAutocomplete();
                break;
        }
    }

    function updateButtonState() {
        // Delegate to updateValidation for comprehensive check
        updateValidation();
    }

    function updateToggleState() {
        const hasAny = Object.values(contextOptions).some(Boolean);
        contextMenuButton.classList.toggle('nav-button--active', hasAny);
        contextMenuButton.setAttribute('aria-pressed', hasAny);
    }

    function applyOptionClasses() {
        document.body.classList.toggle('hide-bolded', !contextOptions.bolded);
        document.body.classList.toggle('hide-repeats', !contextOptions.repeats);
        document.body.classList.toggle('hide-uncommon', !contextOptions.uncommon);
        document.body.classList.toggle('hide-phonetics', !contextOptions.phonetics);
        document.body.classList.toggle('hide-book-overview', !contextOptions.overview);
        document.body.classList.toggle('hide-literary-units', !contextOptions.units);
        document.body.classList.toggle('hide-names', !contextOptions.names);
    }

    function syncMenuState() {
        const inputs = contextMenu.querySelectorAll('[data-context-option]');
        inputs.forEach((input) => {
            const key = input.dataset.contextOption;
            input.checked = !!contextOptions[key];
            input.parentElement.setAttribute('aria-checked', input.checked);
        });
    }

    // ===== Context Menu =====

    function closeMenu() {
        contextDropdown.classList.remove('is-open');
        contextMenuButton.setAttribute('aria-expanded', 'false');
    }

    function toggleMenu() {
        contextDropdown.classList.toggle('is-open');
        const isOpen = contextDropdown.classList.contains('is-open');
        contextMenuButton.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    }

    // Event listeners for book/chapter inputs with autocomplete
    bookInput.addEventListener('input', () => {
        updateValidation();
        const query = bookInput.value.trim();
        if (query.length >= 1) {
            const suggestions = findMatchingBooks(query);
            // Don't show autocomplete if exact match
            const exactMatch = suggestions.length === 1 && suggestions[0].name.toLowerCase() === query.toLowerCase();
            if (exactMatch) {
                hideAutocomplete();
            } else {
                showAutocomplete(suggestions);
            }
        } else {
            hideAutocomplete();
        }
    });

    bookInput.addEventListener('keydown', handleAutocompleteKeydown);

    bookInput.addEventListener('blur', () => {
        // Delay to allow click on autocomplete item
        setTimeout(hideAutocomplete, 150);
    });

    bookInput.addEventListener('focus', () => {
        const query = bookInput.value.trim();
        if (query.length >= 1) {
            const suggestions = findMatchingBooks(query);
            const exactMatch = suggestions.length === 1 && suggestions[0].name.toLowerCase() === query.toLowerCase();
            if (!exactMatch && suggestions.length > 0) {
                showAutocomplete(suggestions);
            }
        }
    });

    chapterInput.addEventListener('input', updateButtonState);

    contextMenuButton.addEventListener('click', (event) => {
        event.stopPropagation();
        toggleMenu();
    });

    document.addEventListener('click', (event) => {
        if (!contextDropdown.contains(event.target)) {
            closeMenu();
        }
    });

    contextMenu.addEventListener('click', (event) => event.stopPropagation());

    contextMenu.querySelectorAll('[data-context-option]').forEach((input) => {
        const key = input.dataset.contextOption;
        input.addEventListener('change', () => {
            contextOptions[key] = input.checked;
            persistOptions();
            applyOptionClasses();
            updateToggleState();
            syncMenuState();
            renderOverlay();
        });
    });

    // ===== Literary Unit Overlay =====

    function renderOverlay() {
        const overlay = document.getElementById('bar-overlay');
        const shell = document.querySelector('.reading-shell');
        const rows = Array.from(document.querySelectorAll('.verse-row'));
        if (!overlay || !shell || !rows.length || !contextOptions.units) {
            if (overlay) overlay.innerHTML = '';
            // shell is absent on the blank home page; guard so the rest of the
            // DOMContentLoaded initialization isn't killed by a TypeError.
            if (shell) shell.style.setProperty('--bar-offset', '16px');
            return;
        }
        overlay.innerHTML = '';
        const overlayWidth = Math.max(activeUnits.length * 8, 12);
        shell.style.setProperty('--bar-offset', `${overlayWidth}px`);
        overlay.style.width = `${overlayWidth}px`;

        activeUnits.forEach((unit, idx) => {
            const startRow = rows.find(r => Number(r.dataset.verse) === unit.start_verse);
            const endRow = rows.find(r => Number(r.dataset.verse) === unit.end_verse);
            if (!startRow || !endRow) return;

            const top = startRow.offsetTop;
            const bottom = endRow.offsetTop + endRow.offsetHeight;
            const bar = document.createElement('span');
            bar.className = 'bar-overlay-segment';
            bar.style.left = `${idx * 8}px`;
            bar.style.top = `${top}px`;
            bar.style.height = `${bottom - top}px`;
            bar.style.setProperty('--bar-color', unit.color);
            bar.title = unit.label || '';
            overlay.appendChild(bar);
        });
    }

    // ===== Text Normalization Utilities =====

    function stripDiacritics(text) {
        return (text || '').normalize('NFKD').replace(/\p{M}+/gu, '');
    }

    const finalFormMap = {
        '\u05DA': '\u05DB', // final kaf → kaf
        '\u05DD': '\u05DE', // final mem → mem
        '\u05DF': '\u05E0', // final nun → nun
        '\u05E3': '\u05E4', // final pe → pe
        '\u05E5': '\u05E6', // final tsadi → tsadi
    };

    function normalizeRootLetters(text) {
        const stripped = stripDiacritics(text);
        if (!stripped) return '';
        const letters = (stripped.match(/\p{L}+/gu) || []).join('');
        return letters
            .split('')
            .map((ch) => finalFormMap[ch] || ch)
            .join('')
            .toUpperCase();
    }

    const vowelRegex = /[aeiouāēīōūâêîôûáéíóúàèìòùäëïöüăĕĭŏŭȳŷ]+/giu;

    function consonantKey(text) {
        const lettersOnly = (text || '').replace(/[^\p{L}]/gu, '');
        return lettersOnly.replace(vowelRegex, '').toUpperCase();
    }

    // ===== Token Normalization =====

    function normalizeToken(el) {
        const rawXlit = (el.dataset.xliteral || el.textContent || '').trim();
        const normalized = rawXlit.normalize('NFKD');
        const lettersOnly = (normalized.match(/\p{L}+/gu) || []).join('');
        const cleanedWithMarks = lettersOnly.toLowerCase();
        const baseLetters = cleanedWithMarks.replace(/\p{M}+/gu, '');
        const vowels = (cleanedWithMarks.match(vowelRegex) || []).join('-');
        const onsetMatch = baseLetters.match(/^[^aeiouāēīōūâêîôûáéíóúàèìòùäëïöüăĕĭŏŭȳŷ]+/i);
        const onset = onsetMatch ? onsetMatch[0].toUpperCase() : '';
        const strongs = (el.dataset.strongs || '').toUpperCase();
        const strongsPrefix = strongs[0] || '';
        const strongsNumber = Number.parseInt(strongs.slice(1), 10) || null;
        const rootSource = el.dataset.lemma || el.dataset.rootkey || rawXlit || cleanedWithMarks;
        const rootLetters = normalizeRootLetters(rootSource);
        const rootLettersArray = Array.from(rootLetters);
        const rootKey = rootLetters;
        return {
            element: el,
            strongs,
            strongsPrefix,
            strongsNumber,
            xlit: rawXlit,
            cleaned: baseLetters,
            cleanedWithMarks,
            vowels,
            onset,
            rootKey,
            rootLetters,
            rootLettersArray,
            gloss: el.dataset.gloss || '',
            lemma: el.dataset.lemma || '',
            pronounce: el.dataset.pronounce || '',
        };
    }

    function tokenKey(tok) {
        return `${tok.strongs || 'na'}-${tok.cleaned || tok.xlit || tok.element.textContent}`.toLowerCase();
    }

    function uniqueTokens(tokens) {
        const seen = new Set();
        return tokens.filter((tok) => {
            const key = tokenKey(tok);
            if (!key || seen.has(key)) return false;
            seen.add(key);
            return true;
        });
    }

    function groupBy(tokens, fn) {
        return tokens.reduce((acc, token) => {
            const key = fn(token);
            if (!key) return acc;
            acc[key] = acc[key] || [];
            acc[key].push(token);
            return acc;
        }, {});
    }

    // ===== Similarity Algorithms =====

    function levenshtein(a, b) {
        if (!a || !b) return Math.max(a.length, b.length);
        const dp = Array.from({ length: b.length + 1 }, (_, i) => i);
        for (let i = 1; i <= a.length; i++) {
            let prev = dp[0];
            dp[0] = i;
            for (let j = 1; j <= b.length; j++) {
                const temp = dp[j];
                dp[j] = Math.min(
                    dp[j] + 1,
                    dp[j - 1] + 1,
                    prev + (a[i - 1] === b[j - 1] ? 0 : 1),
                );
                prev = temp;
            }
        }
        return dp[b.length];
    }

    function similarityScore(a, b) {
        const maxLen = Math.max(a.length, b.length);
        if (!maxLen) return 0;
        const distance = levenshtein(a, b);
        return 1 - distance / maxLen;
    }

    function longestSharedRun(a, b) {
        const aRoot = a.rootLetters || '';
        const bRoot = b.rootLetters || '';
        if (!aRoot || !bRoot) return '';
        let best = '';
        for (let i = 0; i < aRoot.length; i++) {
            for (let j = 0; j < bRoot.length; j++) {
                let len = 0;
                while (aRoot[i + len] && bRoot[j + len] && aRoot[i + len] === bRoot[j + len]) {
                    len += 1;
                }
                if (len > best.length) {
                    best = aRoot.slice(i, i + len);
                }
            }
        }
        return best.length >= 2 ? best : '';
    }

    function strongsProximityScore(a, b) {
        if (!a.strongsNumber || !b.strongsNumber) return 0;
        if (a.strongsPrefix !== b.strongsPrefix) return 0;
        const diff = Math.abs(a.strongsNumber - b.strongsNumber);
        if (diff === 0) return 1;
        const maxRange = 30;
        return Math.max(0, 1 - diff / maxRange);
    }

    // ===== Phonetic Device Detection =====

    function detectPhoneticDevices(tokens) {
        const matches = [];
        const lexicalKeys = new Set();

        // Lexical repetition (same Strong's number)
        const lexicalGroups = Object.entries(groupBy(tokens, (t) => t.strongs))
            .filter(([, list]) => list.length >= 2)
            .sort((a, b) => b[1].length - a[1].length)
            .slice(0, 3);
        lexicalGroups.forEach(([key, list]) => {
            const unique = uniqueTokens(list);
            unique.forEach((tok) => lexicalKeys.add(tokenKey(tok)));
            matches.push({
                className: 'lexical',
                key,
                tokens: unique,
                displayTokens: list,
                meta: `Strong's ${key}`,
                note: 'Lexical repetition anchors the thought in the original tongue.',
            });
        });

        // Root repetition (same consonantal root)
        const rootGroups = Object.entries(groupBy(tokens, (t) => t.rootKey))
            .filter(([key, list]) => key.length >= 2 && list.length >= 2)
            .sort((a, b) => b[1].length - a[1].length)
            .slice(0, 2);
        rootGroups.forEach(([key, list]) => {
            const filtered = list.filter((tok) => !lexicalKeys.has(tokenKey(tok)));
            const unique = uniqueTokens(filtered);
            if (unique.length < 2) return;
            matches.push({
                className: 'root',
                key,
                tokens: unique,
                displayTokens: filtered,
                meta: `Shared root ${key}`,
                note: 'Related roots weave a semantic thread through the verse.',
            });
        });

        // Root affinity (shared consonantal runs)
        const affinityBuckets = {};
        for (let i = 0; i < tokens.length; i++) {
            for (let j = i + 1; j < tokens.length; j++) {
                const a = tokens[i];
                const b = tokens[j];
                if (!a.rootLetters || !b.rootLetters) continue;
                const sharedRun = longestSharedRun(a, b);
                if (!sharedRun) continue;
                const proximity = strongsProximityScore(a, b);
                const bucketKey = sharedRun || `${a.strongs}-${b.strongs}`;
                if (!affinityBuckets[bucketKey]) {
                    affinityBuckets[bucketKey] = { tokens: [], proximity: 0, shared: sharedRun };
                }
                affinityBuckets[bucketKey].tokens.push(a, b);
                affinityBuckets[bucketKey].proximity = Math.max(affinityBuckets[bucketKey].proximity, proximity);
            }
        }

        Object.entries(affinityBuckets)
            .map(([key, data]) => ({ key, list: uniqueTokens(data.tokens), proximity: data.proximity, shared: data.shared }))
            .filter((entry) => entry.list.length >= 2)
            .sort((a, b) => b.list.length - a.list.length)
            .slice(0, 2)
            .forEach(({ key, list, proximity, shared }) => {
                const filtered = list.filter((tok) => !lexicalKeys.has(tokenKey(tok)));
                if (filtered.length < 2) return;
                const overlapLabel = shared || key;
                const metaBits = [`Root echo ${overlapLabel}`];
                if (proximity >= 0.4) {
                    metaBits.push(`Strong's nearby ${(proximity * 100).toFixed(0)}%`);
                }
                matches.push({
                    className: 'root',
                    key,
                    tokens: filtered,
                    displayTokens: filtered,
                    meta: metaBits.join(' · '),
                    note: 'Close roots or neighboring Strong\'s entries hint at wordplay.',
                });
            });

        // Alliteration (same onset)
        const allitGroups = Object.entries(groupBy(tokens, (t) => t.onset))
            .filter(([key, list]) => key && list.length >= 2)
            .slice(0, 2);
        allitGroups.forEach(([key, list]) => {
            const filtered = list.filter((tok) => !lexicalKeys.has(tokenKey(tok)));
            const unique = uniqueTokens(filtered);
            if (unique.length < 2) return;
            matches.push({
                className: 'alliteration',
                key,
                tokens: unique,
                displayTokens: filtered,
                meta: `Onset ${key}`,
                note: 'Repeated consonants create an aural hook (alliteration).',
            });
        });

        // Assonance (same vowels)
        const assonanceGroups = Object.entries(groupBy(tokens, (t) => t.vowels))
            .filter(([key, list]) => key && list.length >= 2)
            .slice(0, 2);
        assonanceGroups.forEach(([key, list]) => {
            const unique = uniqueTokens(list);
            matches.push({
                className: 'assonance',
                key,
                tokens: unique,
                displayTokens: list,
                meta: `Vowel tone ${key}`,
                note: 'Echoed vowels smooth the cadence (assonance).',
            });
        });

        // Syntactic parallelism (repeated bigrams)
        const bigrams = {};
        for (let i = 0; i < tokens.length - 1; i++) {
            const a = tokens[i];
            const b = tokens[i + 1];
            if (!a.strongs || !b.strongs) continue;
            const key = `${a.strongs}-${b.strongs}`;
            bigrams[key] = bigrams[key] || [];
            bigrams[key].push([a, b]);
        }
        Object.entries(bigrams)
            .filter(([, pairs]) => pairs.length >= 2)
            .slice(0, 2)
            .forEach(([key, pairs]) => {
                const unique = uniqueTokens(pairs.flat());
                matches.push({
                    className: 'parallelism',
                    key,
                    tokens: unique,
                    displayTokens: pairs.flat(),
                    meta: 'Mirrored clause',
                    note: 'Parallel syntax repeats thought with balance.',
                });
            });

        // Climactic repetition (anadiplosis - end-start repetition)
        for (let i = 1; i < tokens.length; i++) {
            if (tokens[i].strongs && tokens[i].strongs === tokens[i - 1].strongs) {
                const unique = uniqueTokens([tokens[i - 1], tokens[i]]);
                matches.push({
                    className: 'climactic',
                    key: tokens[i].strongs,
                    tokens: unique,
                    displayTokens: [tokens[i - 1], tokens[i]],
                    meta: 'Chain echo',
                    note: 'End-start repetition (anadiplosis) amplifies emphasis.',
                });
            }
        }

        // Paronomasia (similar sounds, different meanings)
        const seenPairs = new Set();
        for (let i = 0; i < tokens.length; i++) {
            for (let j = i + 1; j < tokens.length; j++) {
                const a = tokens[i];
                const b = tokens[j];
                if (!a.cleaned || !b.cleaned) continue;
                if (a.strongs && b.strongs && a.strongs === b.strongs) continue;
                const pairKey = `${a.strongs}-${b.strongs}`;
                if (seenPairs.has(pairKey)) continue;
                const score = similarityScore(a.cleaned, b.cleaned);
                if (score >= 0.72) {
                    seenPairs.add(pairKey);
                    const unique = uniqueTokens([a, b]);
                    matches.push({
                        className: 'paronomasia',
                        key: `${a.xlit} / ${b.xlit}`,
                        tokens: unique,
                        displayTokens: [a, b],
                        meta: `Sound overlap ${(score * 100).toFixed(0)}%`,
                        note: 'Similar sounds, different senses (paronomasia).',
                    });
                }
            }
        }

        return matches.slice(0, 8);
    }

    const deviceLabels = {
        lexical: 'Lexical repetition',
        root: 'Root repetition',
        alliteration: 'Alliteration',
        assonance: 'Assonance',
        paronomasia: 'Paronomasia',
        climactic: 'Climactic repetition',
        parallelism: 'Syntactic parallelism',
    };

    function createDeviceCard(match, matchId) {
        const card = document.createElement('div');
        card.className = 'phonetic-card';
        card.dataset.device = match.className;

        const header = document.createElement('div');
        header.className = 'phonetic-card__header';
        const label = document.createElement('span');
        label.className = 'device-label';
        label.textContent = deviceLabels[match.className] || 'Device';
        const meta = document.createElement('span');
        meta.className = 'device-meta';
        meta.textContent = match.meta || '';
        header.append(label, meta);
        card.appendChild(header);

        const wordRow = document.createElement('div');
        wordRow.className = 'phonetic-chip-row';
        const displayTokens = match.displayTokens && match.displayTokens.length
            ? match.displayTokens
            : match.tokens;
        displayTokens.forEach((tok) => {
            const chip = document.createElement('span');
            chip.className = 'phonetic-chip';
            chip.textContent = `${tok.xlit || tok.element.textContent}${tok.gloss ? ` · ${tok.gloss}` : ''}`;
            chip.title = tok.lemma || tok.pronounce || tok.strongs;
            chip.addEventListener('mouseenter', () => tok.element.classList.add('phonetic-focus'));
            chip.addEventListener('mouseleave', () => tok.element.classList.remove('phonetic-focus'));
            chip.addEventListener('click', (event) => {
                event.stopPropagation();
                tok.element.scrollIntoView({ behavior: 'smooth', block: 'center' });
                tok.element.classList.add('phonetic-focus');
                setTimeout(() => tok.element.classList.remove('phonetic-focus'), 650);
            });
            wordRow.appendChild(chip);
        });
        card.appendChild(wordRow);

        if (match.note) {
            const note = document.createElement('p');
            note.className = 'phonetic-note';
            note.textContent = match.note;
            card.appendChild(note);
        }

        return card;
    }

    function renderPhoneticDevices() {
        const verseRows = document.querySelectorAll('.verse-row');
        if (!verseRows.length) return;

        ensureOverlayObserver();

        verseRows.forEach((row) => {
            const verseText = row.querySelector('.verse-text');
            if (!verseText || verseText.querySelector('.phonetic-card-shell')) return;

            const tokens = Array.from(row.querySelectorAll('.strongs-token[data-strongs]'))
                .map(normalizeToken)
                .filter((tok) => tok.strongs);
            if (!tokens.length) return;

            const matches = detectPhoneticDevices(tokens);
            if (!matches.length) return;

            const shell = document.createElement('div');
            shell.className = 'phonetic-card-shell';

            const toggle = document.createElement('button');
            toggle.type = 'button';
            toggle.className = 'phonetic-toggle';
            const verseNum = row.dataset.verse || '';
            const defaultOpen = verseNum === '1';
            const panel = document.createElement('div');
            panel.className = 'phonetic-card-panel';

            function setPanelState(open) {
                panel.classList.toggle('is-collapsed', !open);
                toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
                toggle.textContent = open ? 'Hide phonetic devices' : 'Show phonetic devices';
            }

            matches.forEach((match, idx) => {
                const matchId = `${row.dataset.verse || 'v'}-${idx}`;
                const displayTokens = uniqueTokens(match.tokens);
                displayTokens.forEach((tok) => {
                    tok.element.classList.add('phonetic-hit', `phonetic-hit--${match.className}`);
                    tok.element.dataset.phoneticId = matchId;
                });
                panel.appendChild(createDeviceCard(match, matchId));
            });

            toggle.addEventListener('click', () => {
                const isOpen = !panel.classList.contains('is-collapsed');
                setPanelState(!isOpen);
                scheduleOverlayRender();
            });

            setPanelState(defaultOpen);
            shell.appendChild(toggle);
            shell.appendChild(panel);
            verseText.appendChild(shell);
        });

        scheduleOverlayRender();
    }

    // ===== Heatmap Focus =====

    function applyHeatmapFocus() {
        if (!focusStrong) return;
        // Find all tokens where focusStrong matches either data-strongs or data-alt-strongs
        const allTokens = document.querySelectorAll('.strongs-token[data-strongs]');
        allTokens.forEach((el) => {
            const primaryStrongs = el.dataset.strongs;
            const altStrongs = el.dataset.altStrongs;
            if (primaryStrongs === focusStrong || altStrongs === focusStrong) {
                el.classList.add('heatmap-focus-word');
            }
        });
    }

    // ===== Word Context Menu =====

    const userStrongsSet = window.USER_STRONGS_SET || new Set();
    const wordPopup = document.getElementById('word-popup');
    const toastContainer = document.getElementById('toast-container');
    let currentPopupStrongs = null;
    let currentPopupElement = null;

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

    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function sendDictAction(actions) {
        return fetch('/edit_dict', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify({ actions }),
        })
        .then(response => {
            if (!response.ok) throw new Error('Request failed');
            return response.json();
        })
        .then(data => {
            if (!data?.success) throw new Error(data?.error || 'Unable to save');
            return data;
        })
        .catch(error => {
            showToast(error.message || 'Unable to save changes.', 'error');
            return { success: false };
        });
    }

    function positionPopup(targetEl) {
        if (!wordPopup || !targetEl) return;

        const rect = targetEl.getBoundingClientRect();
        const popupWidth = 320;
        const margin = 12;

        // Temporarily show to get actual height
        wordPopup.style.visibility = 'hidden';
        wordPopup.style.display = 'block';
        const popupHeight = wordPopup.offsetHeight;
        wordPopup.style.display = '';
        wordPopup.style.visibility = '';

        // Calculate position (below and centered on word)
        let left = rect.left + (rect.width / 2) - (popupWidth / 2);
        let top = rect.bottom + margin;

        // Adjust for viewport boundaries
        if (left < margin) left = margin;
        if (left + popupWidth > window.innerWidth - margin) {
            left = window.innerWidth - popupWidth - margin;
        }

        // If below viewport, position above the word
        if (top + popupHeight > window.innerHeight - margin) {
            top = rect.top - popupHeight - margin;
        }

        // Ensure not above viewport
        if (top < margin) top = margin;

        wordPopup.style.left = `${left + window.scrollX}px`;
        wordPopup.style.top = `${top + window.scrollY}px`;
    }

    function populatePopup(tokenData) {
        if (!wordPopup) return;

        const titleEl = wordPopup.querySelector('.word-popup__title');
        const lemmaEl = wordPopup.querySelector('.word-popup__lemma');
        const detailsEl = wordPopup.querySelector('.word-popup__details');
        const inputEl = document.getElementById('word-popup-translation');
        const statusEl = document.getElementById('word-popup-status');
        const addBtn = wordPopup.querySelector('[data-action="add"]');

        // Set Strong's number as title
        if (titleEl) titleEl.textContent = tokenData.strongs || '';

        // Set lemma (Hebrew/Greek)
        if (lemmaEl) lemmaEl.textContent = tokenData.lemma || '';

        // Build details line
        const detailParts = [];
        if (tokenData.xlit) detailParts.push(tokenData.xlit);
        if (tokenData.pronounce) detailParts.push(`(${tokenData.pronounce})`);
        if (tokenData.gloss) detailParts.push(`"${tokenData.gloss}"`);
        if (detailsEl) detailsEl.textContent = detailParts.join(' · ');

        // Proper-name meaning ("that is, ...") when the lexicon glosses one.
        const nameEl = document.getElementById('word-popup-name-meaning');
        if (nameEl) {
            if (tokenData.nameMeaning) {
                nameEl.textContent = `† that is, ${tokenData.nameMeaning}`;
                nameEl.hidden = false;
            } else {
                nameEl.textContent = '';
                nameEl.hidden = true;
            }
        }

        // Pre-fill input with gloss
        if (inputEl) inputEl.value = tokenData.gloss || '';

        // Check if already in user's list
        const isInList = userStrongsSet.has(tokenData.strongs);
        if (statusEl) {
            statusEl.textContent = isInList ? '✓ In Your List' : '';
            statusEl.classList.toggle('word-popup__status--active', isInList);
        }
        if (addBtn) {
            addBtn.textContent = isInList ? 'Update' : 'Add to My List';
        }

        currentPopupStrongs = tokenData.strongs;

        // Load cross-references asynchronously
        loadCrossReferences(tokenData.strongs);
    }

    /**
     * Fetch and display Hebrew-Greek cross-references for a Strong's number.
     * Shows LXX equivalents for Hebrew words and Hebrew sources for Greek words.
     */
    async function loadCrossReferences(strongNumber) {
        const crossrefSection = document.getElementById('word-popup-crossref');
        const crossrefList = document.getElementById('crossref-list');
        const crossrefLabel = document.getElementById('crossref-label');

        if (!crossrefSection || !crossrefList || !crossrefLabel) return;

        // Hide while loading
        crossrefSection.style.display = 'none';
        crossrefList.innerHTML = '';

        try {
            const response = await fetch(`/api/crossref/${strongNumber}`);
            if (!response.ok) return;

            const data = await response.json();
            const allRefs = [...(data.cross_refs?.primary || []), ...(data.cross_refs?.secondary || [])];

            if (allRefs.length === 0) {
                crossrefSection.style.display = 'none';
                return;
            }

            // Set label based on language
            crossrefLabel.textContent = data.language === 'hebrew'
                ? 'LXX typically uses:'
                : 'Hebrew equivalent:';

            // Build list HTML (limit to 4 entries)
            const primaryCount = data.cross_refs?.primary?.length || 0;
            crossrefList.innerHTML = allRefs.slice(0, 4).map((ref, idx) => {
                const isPrimary = idx < primaryCount;
                const lemmaDisplay = ref.lemma || '';
                const xlitDisplay = ref.xlit ? `(${ref.xlit})` : '';

                return `
                    <div class="word-popup__crossref-item ${isPrimary ? 'primary' : 'secondary'}">
                        <a href="${window.HEATMAP_URL}?strong=${ref.strong}&from_crossref=1"
                           class="crossref-link"
                           data-strong="${ref.strong}"
                           title="View heatmap for ${ref.strong}">
                            <span class="crossref-strong">${ref.strong}</span>
                            <span class="crossref-lemma">${lemmaDisplay}</span>
                            <span class="crossref-xlit">${xlitDisplay}</span>
                        </a>
                    </div>
                `;
            }).join('');

            // Show the section
            crossrefSection.style.display = 'block';

        } catch (err) {
            console.error('Failed to load cross-references:', err);
            crossrefSection.style.display = 'none';
        }
    }

    function showWordPopup(event, tokenEl) {
        if (!wordPopup || !tokenEl) return;

        event.preventDefault();
        event.stopPropagation();

        // Extract data from token element
        const tokenData = {
            strongs: (tokenEl.dataset.strongs || '').toUpperCase(),
            lemma: tokenEl.dataset.lemma || '',
            xlit: tokenEl.dataset.xliteral || tokenEl.textContent.trim(),
            pronounce: tokenEl.dataset.pronounce || '',
            gloss: tokenEl.dataset.gloss || tokenEl.dataset.original || '',
            nameMeaning: tokenEl.dataset.nameMeaning || '',
        };

        if (!tokenData.strongs) return;

        currentPopupElement = tokenEl;
        populatePopup(tokenData);
        wordPopup.classList.add('is-visible');
        wordPopup.setAttribute('aria-hidden', 'false');
        positionPopup(tokenEl);

        // Focus the input field
        const inputEl = document.getElementById('word-popup-translation');
        if (inputEl) {
            inputEl.focus();
            inputEl.select();
        }
    }

    function hideWordPopup() {
        if (!wordPopup) return;
        wordPopup.classList.remove('is-visible');
        wordPopup.setAttribute('aria-hidden', 'true');
        currentPopupStrongs = null;
        currentPopupElement = null;
    }

    function handlePopupAction(action) {
        const inputEl = document.getElementById('word-popup-translation');
        const translation = inputEl?.value.trim() || '';

        switch (action) {
            case 'add':
                if (!currentPopupStrongs) return;
                if (!translation) {
                    showToast('Please enter a translation', 'error');
                    if (inputEl) inputEl.focus();
                    return;
                }
                const actionType = userStrongsSet.has(currentPopupStrongs) ? 'update' : 'add';
                sendDictAction([{
                    action: actionType,
                    strong_number: currentPopupStrongs,
                    translations: [translation],
                    color: null
                }]).then(data => {
                    if (data.success) {
                        userStrongsSet.add(currentPopupStrongs);
                        showToast(
                            actionType === 'add'
                                ? `${currentPopupStrongs} added to your list`
                                : `${currentPopupStrongs} updated`,
                            'success'
                        );
                        // Update status indicator
                        const statusEl = document.getElementById('word-popup-status');
                        const addBtn = wordPopup.querySelector('[data-action="add"]');
                        if (statusEl) {
                            statusEl.textContent = '✓ In Your List';
                            statusEl.classList.add('word-popup__status--active');
                        }
                        if (addBtn) addBtn.textContent = 'Update';
                    }
                });
                break;

            case 'heatmap':
                if (!currentPopupStrongs) return;
                window.location.href = `${heatmapBase}?strong=${encodeURIComponent(currentPopupStrongs)}`;
                break;

            case 'occurrences':
                if (!currentPopupStrongs) return;
                window.location.href = `${window.OCCURRENCES_URL || '/occurrences'}?strong=${encodeURIComponent(currentPopupStrongs)}`;
                break;

            case 'copy':
                if (!currentPopupStrongs) return;
                navigator.clipboard.writeText(currentPopupStrongs).then(() => {
                    showToast(`Copied ${currentPopupStrongs}`, 'success');
                }).catch(() => {
                    showToast('Failed to copy', 'error');
                });
                break;
        }
    }

    function bindWordPopup() {
        if (!wordPopup) return;

        // Close button
        const closeBtn = wordPopup.querySelector('.word-popup__close');
        if (closeBtn) {
            closeBtn.addEventListener('click', hideWordPopup);
        }

        // Action buttons
        wordPopup.querySelectorAll('[data-action]').forEach(btn => {
            btn.addEventListener('click', () => {
                handlePopupAction(btn.dataset.action);
            });
        });

        // Click outside to close
        document.addEventListener('click', (event) => {
            if (wordPopup.classList.contains('is-visible') &&
                !wordPopup.contains(event.target) &&
                !event.target.closest('.strongs-token')) {
                hideWordPopup();
            }
        });

        // Escape key to close
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && wordPopup.classList.contains('is-visible')) {
                hideWordPopup();
            }
        });

        // Enter key in input to submit
        const inputEl = document.getElementById('word-popup-translation');
        if (inputEl) {
            inputEl.addEventListener('keydown', (event) => {
                if (event.key === 'Enter') {
                    event.preventDefault();
                    handlePopupAction('add');
                }
            });
        }
    }

    function bindStrongsTokenClicks() {
        document.querySelectorAll('.strongs-token[data-strongs]').forEach(token => {
            if (token.dataset.popupBound) return;
            token.dataset.popupBound = '1';
            token.style.cursor = 'pointer';
            token.addEventListener('click', (event) => {
                showWordPopup(event, token);
            });
        });
    }

    // ===== Name Meanings (inline "that is, ..." notes) =====

    function toggleNameNote(mark) {
        // The note is the hidden span immediately after the dagger.
        const note = mark.nextElementSibling;
        if (!note || !note.classList.contains('name-note')) return;
        note.hidden = !note.hidden;
        mark.classList.toggle('is-open', !note.hidden);
    }

    function bindNameMarks() {
        document.addEventListener('click', (event) => {
            const mark = event.target.closest('.name-mark');
            if (!mark) return;
            event.preventDefault();
            event.stopPropagation();
            toggleNameNote(mark);
        });
        document.addEventListener('keydown', (event) => {
            if (event.key !== 'Enter' && event.key !== ' ') return;
            const mark = event.target.closest?.('.name-mark');
            if (!mark) return;
            event.preventDefault();
            toggleNameNote(mark);
        });
    }

    // ===== Reading History (Continue Reading) =====

    const RECENT_KEY = 'bt_recent_chapters';
    const RECENT_MAX = 5;

    function readRecentChapters() {
        try {
            const raw = localStorage.getItem(RECENT_KEY);
            const list = raw ? JSON.parse(raw) : [];
            return Array.isArray(list) ? list : [];
        } catch (err) {
            return [];
        }
    }

    function recordCurrentChapter() {
        const book = window.CURRENT_BOOK;
        const chapter = window.CURRENT_CHAPTER;
        if (!book || !chapter) return;
        try {
            const list = readRecentChapters().filter(
                (item) => !(item.book === book && item.chapter === chapter)
            );
            list.unshift({ book, chapter, ts: Date.now() });
            localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, RECENT_MAX)));
        } catch (err) {
            /* localStorage unavailable (private mode etc.) — history is a nicety */
        }
    }

    function renderRecentChapters() {
        const container = document.getElementById('recent-reading');
        const chipsEl = document.getElementById('recent-reading-chips');
        if (!container || !chipsEl) return;

        const list = readRecentChapters();
        if (!list.length) return;

        chipsEl.innerHTML = '';
        list.forEach((item, idx) => {
            if (!item.book || !item.chapter) return;
            const chip = document.createElement('a');
            chip.className = idx === 0 ? 'recent-chip recent-chip--latest' : 'recent-chip';
            chip.href = `/?book=${encodeURIComponent(item.book)}&chapter=${encodeURIComponent(item.chapter)}`;
            chip.textContent = `${item.book} ${item.chapter}`;
            if (idx === 0) {
                const arrow = document.createElement('span');
                arrow.className = 'recent-chip__arrow';
                arrow.textContent = '→';
                chip.appendChild(document.createTextNode(' '));
                chip.appendChild(arrow);
            }
            chipsEl.appendChild(chip);
        });
        container.hidden = false;
    }

    // ===== Initialization =====

    loadSavedOptions();
    updateButtonState();
    applyOptionClasses();
    syncMenuState();
    updateToggleState();

    window.addEventListener('resize', renderOverlay);
    renderPhoneticDevices();
    renderOverlay();
    applyHeatmapFocus();
    bindWordPopup();
    bindStrongsTokenClicks();
    bindNameMarks();
    recordCurrentChapter();
    renderRecentChapters();
});
