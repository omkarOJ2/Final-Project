// ── Theme ─────────────────────────────────────────────────────────────────────
function initTheme() {
    const t = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', t);
    updateThemeIcon(t);
}
function toggleTheme() {
    const t = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('theme', t);
    updateThemeIcon(t);
}
function updateThemeIcon(t) {
    const btn = document.getElementById('themeToggle');
    if (btn) btn.innerHTML = t === 'dark' ? '<i class="fas fa-sun"></i>' : '<i class="fas fa-moon"></i>';
}

document.addEventListener('DOMContentLoaded', function () {
    initTheme();
    // Inject theme toggle into navbar if not already present
    if (!document.getElementById('themeToggle')) {
        const nav = document.querySelector('.navbar-nav');
        if (nav) {
            const li  = document.createElement('li');
            li.className = 'nav-item d-flex align-items-center';
            const btn = document.createElement('button');
            btn.id = 'themeToggle';
            btn.className = 'theme-toggle';
            btn.onclick = toggleTheme;
            btn.setAttribute('aria-label', 'Toggle theme');
            li.appendChild(btn);
            nav.appendChild(li);
            updateThemeIcon(document.documentElement.getAttribute('data-theme'));
        }
    }
    // Stat counters (index page)
    document.querySelectorAll('.stat-number').forEach(el => {
        const target = parseInt(el.dataset.target || '0', 10);
        let current = 0;
        const step  = target / 80;
        const timer = setInterval(() => {
            current += step;
            if (current >= target) { current = target; clearInterval(timer); }
            el.textContent = Math.floor(current).toLocaleString();
        }, 20);
    });
    // Auto-load trending news
    if (document.getElementById('newsContainer')) loadTrendingNews();
    // Pre-fill generator topic from URL param
    const params = new URLSearchParams(window.location.search);
    const topicEl = document.getElementById('topic');
    if (topicEl && params.get('topic')) {
        topicEl.value = decodeURIComponent(params.get('topic'));
    }
    // Char counters
    ['newsText', 'articleText'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        const counter = document.createElement('div');
        counter.className = 'form-text mt-1';
        counter.id = id + 'Counter';
        el.parentNode.appendChild(counter);
        const update = () => {
            const n = el.value.length;
            counter.textContent = `${n.toLocaleString()} / 10,000 characters`;
            counter.style.color = n > 9000 ? 'var(--red)' : 'var(--txt2)';
        };
        el.addEventListener('input', update);
        update();
    });
});

// ── Loading states ────────────────────────────────────────────────────────────
const loadingMessages = {
    generator: ['🔍 Searching live news sources...', '📰 Fetching Google News context...', '🧠 LLaMA 3.3 composing article...', '✍️ Applying AP Style...', '✅ Almost done...'],
    detector:  ['🔍 Running 3 targeted searches...', '📊 Cross-referencing claims...', '🧠 Analysing credibility...', '🛡️ Building fact-check report...'],
    checker:   ['📖 Reading article structure...', '🧠 Evaluating against AP Style...', '📊 Scoring each element...', '✅ Finalising review...'],
    trending:  ['🌍 Fetching live headlines...', '📡 Connecting to NewsAPI...', '📰 Curating top stories...'],
};

function showAILoading(elementId, type = 'generator') {
    const el   = document.getElementById(elementId);
    if (!el) return;
    const msgs  = loadingMessages[type] || loadingMessages.generator;
    let idx = 0;
    el.innerHTML = `
        <div class="ai-loading">
            <div class="loading-dots"><span></span><span></span><span></span></div>
            <div class="loading-msg" id="${elementId}Msg">${msgs[0]}</div>
        </div>`;
    const msgEl = document.getElementById(elementId + 'Msg');
    const timer = setInterval(() => {
        idx = (idx + 1) % msgs.length;
        if (msgEl) { msgEl.style.opacity = '0'; setTimeout(() => { msgEl.textContent = msgs[idx]; msgEl.style.opacity = '1'; }, 200); }
    }, 2000);
    el._loadingTimer = timer;
}

function clearLoading(elementId) {
    const el = document.getElementById(elementId);
    if (el && el._loadingTimer) clearInterval(el._loadingTimer);
}

function showError(elementId, message) {
    const el = document.getElementById(elementId);
    if (el) el.innerHTML = `<div class="alert alert-danger"><i class="fas fa-exclamation-triangle"></i> ${message}</div>`;
}

// ── Article Generator ─────────────────────────────────────────────────────────
async function generateArticle() {
    const topic     = document.getElementById('topic')?.value?.trim();
    const wordLimit = document.getElementById('wordLimit')?.value;
    const nature    = document.getElementById('nature')?.value;
    const btn       = document.getElementById('generateBtn');

    if (!topic) { showError('result', 'Please enter a topic.'); return; }
    if (topic.length < 3) { showError('result', 'Topic must be at least 3 characters.'); return; }

    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating...'; }
    showAILoading('result', 'generator');

    try {
        const res  = await fetch('/api/generate-article', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ topic, word_limit: parseInt(wordLimit), nature })
        });
        const data = await res.json();
        clearLoading('result');

        if (data.success) {
            window._articleRaw = data.raw_text || '';
            const wordBadge = data.word_count
                ? `<span class="word-count-badge">📝 ${data.word_count} words</span>` : '';
            const sourcesHtml = data.sources?.length
                ? `<div class="sources-box"><div class="sources-title"><i class="fas fa-link"></i> Sources Referenced</div>
                   <div class="sources-list">${data.sources.map(s =>
                     `<a href="${s.url}" target="_blank" rel="noopener" class="source-chip">
                        <i class="fas fa-external-link-alt"></i> ${s.source}</a>`
                   ).join('')}</div></div>` : '';

            document.getElementById('result').innerHTML = `
                <div class="result-box">
                    <div class="result-actions">
                        <h4 style="margin:0;flex:1"><i class="fas fa-newspaper"></i> Generated Article</h4>
                        ${wordBadge}
                        <button class="copy-btn" onclick="copyArticle()" id="copyBtn">
                            <i class="fas fa-copy"></i> Copy</button>
                        <button class="btn-secondary btn-sm" onclick="exportToPDF('generated-article')">
                            <i class="fas fa-download"></i> PDF</button>
                    </div>
                    <div id="generated-article" class="result-content">${data.article}</div>
                </div>${sourcesHtml}`;
        } else {
            showError('result', data.error || 'Failed to generate article.');
        }
    } catch {
        clearLoading('result');
        showError('result', 'Network error. Please check your connection.');
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-magic"></i> Generate Article'; }
    }
}

function copyArticle() {
    const text = window._articleRaw || document.getElementById('generated-article')?.innerText || '';
    navigator.clipboard.writeText(text).then(() => {
        const btn = document.getElementById('copyBtn');
        if (!btn) return;
        btn.innerHTML = '<i class="fas fa-check"></i> Copied!';
        btn.classList.add('copied');
        setTimeout(() => { btn.innerHTML = '<i class="fas fa-copy"></i> Copy'; btn.classList.remove('copied'); }, 2000);
    });
}

// ── Fake News Detector ────────────────────────────────────────────────────────
async function detectFakeNews() {
    const newsText = document.getElementById('newsText')?.value?.trim();
    const btn      = document.getElementById('detectBtn');

    if (!newsText) { showError('detectionResult', 'Please enter news text.'); return; }
    if (newsText.length < 20) { showError('detectionResult', 'Text must be at least 20 characters.'); return; }

    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Analysing...'; }
    showAILoading('detectionResult', 'detector');

    try {
        const res  = await fetch('/api/detect-fake-news', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ news_text: newsText })
        });
        const data = await res.json();
        clearLoading('detectionResult');

        if (data.success) {
            const score   = data.confidence || 50;
            const verdict = data.verdict    || 'Unverifiable';
            const vl = verdict.toLowerCase();
            let color = '#f59e0b', cls = 'verdict-neutral';
            if (vl.includes('accurate') && !vl.includes('in') && !vl.includes('partial')) { color = '#10b981'; cls = 'verdict-good'; }
            else if (vl.includes('mostly'))   { color = '#3b82f6'; cls = 'verdict-mostly'; }
            else if (vl.includes('inaccurate')){ color = '#ef4444'; cls = 'verdict-bad'; }
            else if (vl.includes('partial'))  { color = '#f97316'; cls = 'verdict-partial'; }

            document.getElementById('detectionResult').innerHTML = `
                <div class="credibility-meter">
                    <div class="meter-header">
                        <div class="meter-verdict ${cls}"><i class="fas fa-shield-alt"></i> ${verdict}</div>
                        <div class="meter-score">${score}%</div>
                    </div>
                    <div class="meter-bar-track">
                        <div class="meter-bar-fill" id="meterBar" style="background:${color}"></div>
                    </div>
                    <div class="meter-labels"><span>Inaccurate</span><span>Confidence</span><span>Accurate</span></div>
                </div>
                <div class="result-box"><div class="result-content">${data.analysis}</div></div>`;
            requestAnimationFrame(() => setTimeout(() => {
                const bar = document.getElementById('meterBar');
                if (bar) bar.style.width = score + '%';
            }, 50));
        } else {
            showError('detectionResult', data.error || 'Failed to analyse.');
        }
    } catch {
        clearLoading('detectionResult');
        showError('detectionResult', 'Network error.');
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-search"></i> Analyse & Fact-Check'; }
    }
}

// ── Format Checker ────────────────────────────────────────────────────────────
async function checkFormat() {
    const articleText = document.getElementById('articleText')?.value?.trim();
    const btn         = document.getElementById('checkBtn');

    if (!articleText) { showError('feedbackResult', 'Please enter article text.'); return; }
    if (articleText.length < 20) { showError('feedbackResult', 'Text must be at least 20 characters.'); return; }

    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Reviewing...'; }
    showAILoading('feedbackResult', 'checker');

    try {
        const res  = await fetch('/api/check-format', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ article_text: articleText })
        });
        const data = await res.json();
        clearLoading('feedbackResult');

        if (data.success) {
            const raw   = data.raw || '';
            const score = data.score;

            // ── Score Ring ──────────────────────────────────────────────────
            let scoreHtml = '';
            if (score !== null && score !== undefined) {
                const label = score >= 9 ? 'Publication Ready' : score >= 7 ? 'Minor Edits Needed' : score >= 5 ? 'Needs Revision' : 'Major Rewrite';
                const clr   = score >= 8 ? '#10b981' : score >= 6 ? '#f59e0b' : '#ef4444';
                const offset = 251 - (251 * score / 10);
                scoreHtml = `
                <div class="score-display">
                    <div class="score-ring">
                        <svg viewBox="0 0 100 100">
                            <circle cx="50" cy="50" r="40" class="score-track"/>
                            <circle cx="50" cy="50" r="40" class="score-progress"
                                style="stroke:${clr};stroke-dashoffset:${offset}"/>
                        </svg>
                        <div class="score-text">
                            <span class="score-num">${score}</span>
                            <span class="score-denom">/10</span>
                        </div>
                    </div>
                    <div class="score-info">
                        <div class="score-label">${label}</div>
                        <div class="score-sub">AP Style Editorial Score</div>
                    </div>
                </div>`;
            }

            // ── Parse Publishability ────────────────────────────────────────
            const pubMatch = raw.match(/^PUBLISHABILITY:\s*(.+)/m);
            const pub = pubMatch ? pubMatch[1].trim() : '';
            const pubColor = pub.includes('Ready') ? '#10b981' : pub.includes('Minor') ? '#3b82f6' : pub.includes('Revision') ? '#f59e0b' : '#ef4444';
            const pubHtml = pub ? `<div class="checker-pub-badge" style="background:${pubColor}20;border:1px solid ${pubColor}40;color:${pubColor};padding:8px 16px;border-radius:8px;font-weight:600;display:inline-block;margin-bottom:16px;font-size:.9rem"><i class="fas fa-bookmark"></i> ${pub}</div>` : '';

            // ── Parse Structure Scores ──────────────────────────────────────
            const elements = ['HEADLINE','DATELINE','LEAD','BODY','ATTRIBUTION','CONCLUSION'];
            const elementLabels = {'HEADLINE':'Headline','DATELINE':'Dateline','LEAD':'Lead Paragraph','BODY':'Body Structure','ATTRIBUTION':'Attribution','CONCLUSION':'Conclusion'};
            const tableRows = elements.map(el => {
                const m = raw.match(new RegExp(`^${el}:\\s*(\\d+)/10\\s*\\|\\s*(.+)`, 'm'));
                if (!m) return '';
                const s = parseInt(m[1]), comment = m[2].trim();
                const c = s >= 8 ? '#10b981' : s >= 6 ? '#f59e0b' : '#ef4444';
                return `<tr>
                    <td>${elementLabels[el]}</td>
                    <td><span style="color:${c};font-weight:700;font-size:1rem">${s}/10</span></td>
                    <td>${comment}</td>
                </tr>`;
            }).join('');

            const tableHtml = tableRows ? `
            <div class="checker-section">
                <div class="checker-section-title"><i class="fas fa-table"></i> Structure Breakdown</div>
                <table class="checker-table">
                    <thead><tr><th>Element</th><th>Score</th><th>Assessment</th></tr></thead>
                    <tbody>${tableRows}</tbody>
                </table>
            </div>` : '';

            // ── Parse Strengths ─────────────────────────────────────────────
            const strengthsMatch = raw.match(/^STRENGTHS:\n([\s\S]*?)(?=\nIMPROVEMENTS:|$)/m);
            const strengthLines  = strengthsMatch ? strengthsMatch[1].match(/^-\s+(.+)/gm) || [] : [];
            const strengthHtml   = strengthLines.length ? `
            <div class="checker-section checker-strengths">
                <div class="checker-section-title"><i class="fas fa-check-circle" style="color:#10b981"></i> Strengths</div>
                <ul>${strengthLines.map(l => `<li>${l.replace(/^-\s+/, '')}</li>`).join('')}</ul>
            </div>` : '';

            // ── Parse Improvements ──────────────────────────────────────────
            const imprMatch = raw.match(/^IMPROVEMENTS:\n([\s\S]*?)(?=\nAP_CHECK:|$)/m);
            const imprLines = imprMatch ? imprMatch[1].match(/^-\s+(.+)/gm) || [] : [];
            const imprHtml  = imprLines.length ? `
            <div class="checker-section checker-improvements">
                <div class="checker-section-title"><i class="fas fa-exclamation-circle" style="color:#f59e0b"></i> Improvements</div>
                <ol>${imprLines.map(l => `<li>${l.replace(/^-\s+/, '')}</li>`).join('')}</ol>
            </div>` : '';

            // ── Parse AP Checklist ──────────────────────────────────────────
            const apMatch = raw.match(/^AP_CHECK:\n([\s\S]*?)$/m);
            const apLines = apMatch ? apMatch[1].trim().split('\n') : [];
            const apHtml  = apLines.length ? `
            <div class="checker-section">
                <div class="checker-section-title"><i class="fas fa-list-check"></i> AP Style Checklist</div>
                <div class="checker-ap-grid">
                ${apLines.map(line => {
                    const parts = line.split(':'); if (parts.length < 2) return '';
                    const key = parts[0].trim(), val = parts.slice(1).join(':').trim();
                    const pass = val.includes('PASS');
                    return `<div class="checker-ap-item ${pass ? 'ap-pass' : 'ap-fail'}">
                        <i class="fas ${pass ? 'fa-check' : 'fa-times'}"></i> ${key}
                    </div>`;
                }).join('')}
                </div>
            </div>` : '';

            // ── Parse Detailed Notes ────────────────────────────────────────
            const notesMatch = raw.match(/^DETAILED_NOTES:\s*(.+)/m);
            const notesText  = notesMatch ? notesMatch[1].trim() : '';
            const notesHtml  = notesText ? `
            <div class="checker-section" style="background:rgba(59,130,246,.06);border:1px solid rgba(59,130,246,.2);border-radius:10px;padding:14px 16px;margin-top:4px">
                <div class="checker-section-title"><i class="fas fa-edit" style="color:var(--acc)"></i> Editor's Note</div>
                <p style="color:var(--txt2);font-size:.88rem;line-height:1.6;margin:0">${notesText}</p>
            </div>` : '';

            document.getElementById('feedbackResult').innerHTML =
                scoreHtml + `<div class="result-box" style="padding:24px">` +
                pubHtml + tableHtml + strengthHtml + imprHtml + apHtml + notesHtml + `</div>`;

        } else {
            showError('feedbackResult', data.error || 'Failed to check format.');
        }
    } catch(err) {
        clearLoading('feedbackResult');
        showError('feedbackResult', 'Network error. ' + err.message);
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-check-circle"></i> Check Format'; }
    }
}

// ── Trending News ─────────────────────────────────────────────────────────────
async function loadTrendingNews() {
    const region   = document.getElementById('region')?.value   || 'Worldwide';
    const category = document.getElementById('category')?.value || 'All';
    showAILoading('newsContainer', 'trending');

    try {
        const res  = await fetch('/api/trending-news', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ region, category })
        });
        const data = await res.json();
        clearLoading('newsContainer');

        if (data.success) displayNews(data.news);
        else showError('newsContainer', data.error || 'Failed to load news.');
    } catch {
        clearLoading('newsContainer');
        showError('newsContainer', 'Network error.');
    }
}

function displayNews(news) {
    const container = document.getElementById('newsContainer');
    if (typeof news === 'string') {
        container.innerHTML = `<div class="result-box"><div class="result-content">${news}</div></div>`;
        return;
    }
    if (!Array.isArray(news) || !news.length) {
        container.innerHTML = `<div class="alert alert-info"><i class="fas fa-info-circle"></i> No trending news available.</div>`;
        return;
    }

    container.innerHTML = news.map((item, i) => {
        const badgeClass = item.importance === 'High' ? 'badge-high' : item.importance === 'Medium' ? 'badge-medium' : 'badge-low';
        const timeStr = item.publishedAt ? (() => { try { return new Date(item.publishedAt).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }); } catch { return ''; } })() : '';
        const topicParam = encodeURIComponent((item.title || '').substring(0, 150));
        return `
            <div class="news-item">
                <div class="d-flex align-items-start justify-content-between gap-2 mb-2">
                    <h5 class="mb-0">${i + 1}. ${item.title}</h5>
                </div>
                <p>${item.summary}</p>
                <div class="d-flex flex-wrap align-items-center gap-2">
                    <span class="news-badge ${badgeClass}">${item.importance || 'Medium'}</span>
                    <span class="news-badge" style="background:rgba(245,158,11,.15);color:var(--amb);border:1px solid rgba(245,158,11,.3)">${item.category}</span>
                    ${item.source ? `<span class="news-meta-info"><i class="fas fa-newspaper"></i> ${item.source}</span>` : ''}
                    ${timeStr ? `<span class="news-meta-info"><i class="far fa-clock"></i> ${timeStr}</span>` : ''}
                    <a href="${item.url}" target="_blank" rel="noopener" class="ms-auto news-meta-info" style="text-decoration:none">
                        Read <i class="fas fa-external-link-alt"></i>
                    </a>
                    <a href="/generator?topic=${topicParam}" class="news-write-btn">
                        <i class="fas fa-pen-fancy"></i> Write Article
                    </a>
                </div>
            </div>`;
    }).join('');
}

// ── PDF Export ────────────────────────────────────────────────────────────────
function exportToPDF(elementId) {
    const el = document.getElementById(elementId);
    if (!el) return;
    const win = window.open('', '', 'height=600,width=800');
    if (!win) {
        alert('PDF export was blocked by your browser. Please allow popups for this site and try again.');
        return;
    }
    win.document.write('<html><head><title>AI Newsroom Export</title>');
    win.document.write('<style>body{font-family:Georgia,serif;padding:40px;line-height:1.7;color:#111}h1,h2,h3{color:#1a202c}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:8px}</style>');
    win.document.write('</head><body><h2>AI Newsroom — Generated Article</h2><hr>');
    win.document.write(el.innerHTML);
    win.document.write('</body></html>');
    win.document.close();
    setTimeout(() => win.print(), 300);
}