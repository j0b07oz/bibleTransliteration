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

    function updateButtonState() {
        goButton.disabled = !bookInput.value || !chapterInput.value;
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

    // Event listeners for context menu
    bookInput.addEventListener('input', updateButtonState);
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
            shell.style.setProperty('--bar-offset', '16px');
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
        const targets = document.querySelectorAll(`.strongs-token[data-strongs="${focusStrong}"]`);
        targets.forEach((el) => {
            el.classList.add('heatmap-focus-word');
        });
    }

    // ===== Uncommon Word Links =====

    function bindUncommonWordLinks() {
        const nodes = document.querySelectorAll('.uncommon-word[data-strongs]');
        nodes.forEach((node) => {
            if (node.dataset.uncommonBound) return;
            node.dataset.uncommonBound = '1';
            node.addEventListener('click', (event) => {
                event.stopPropagation();
                const strong = node.dataset.strongs;
                if (!strong) return;
                const targetUrl = `${heatmapBase}?strong=${encodeURIComponent(strong)}`;
                window.location.href = targetUrl;
            });
        });
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
    bindUncommonWordLinks();
});
