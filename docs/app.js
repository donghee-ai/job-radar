let allJobs = [];
let activeRole = null;
let activeCompany = null;
let activeTab = 'roles';
let sortOrder = 'latest';
let currentFiltered = [];

// role별 색상 클래스 매핑
const ROLE_COLOR = {
    '개발':           'role-dev',
    'AI / ML':        'role-ai',
    '보안':           'role-sec',
    '영업 / 사업개발': 'role-sales',
    '마케팅':         'role-mkt',
    '제품 / 기획':    'role-product',
    '운영 / 경영지원': 'role-ops',
    '기타':           'role-etc',
};

async function load() {
    try {
        const res = await fetch('data/jobs.json?t=' + Date.now());
        const data = await res.json();
        allJobs = data.jobs || [];
        window._jobResults = data.results || {};
        renderHeader(data);
        renderFilters();
        render();
        initTabs();
        initTooltip();
    } catch (e) {
        document.getElementById('updated').textContent = '데이터를 불러올 수 없습니다';
        console.error(e);
    }
}

function renderHeader(data) {
    const updated = data.updated_at
        ? new Date(data.updated_at).toLocaleString('ko-KR', {
            year: 'numeric', month: 'short', day: 'numeric',
            hour: '2-digit', minute: '2-digit'
          })
        : '데이터 없음';
    document.getElementById('updated').textContent = `최근 업데이트: ${updated}`;

    const companies = new Set(allJobs.map(j => j.company)).size;
    document.getElementById('header-stats').innerHTML = `
        <div class="stat">
            <div class="stat-value">${allJobs.length.toLocaleString()}</div>
            <div class="stat-label">채용공고</div>
        </div>
        <div class="stat">
            <div class="stat-value">${companies}</div>
            <div class="stat-label">회사</div>
        </div>
    `;
}

/* ── Tab switching ── */

function initTabs() {
    document.querySelectorAll('.sidebar-tab').forEach(tab => {
        tab.onclick = () => switchTab(tab.dataset.tab);
    });
}

function switchTab(tabName) {
    activeTab = tabName;
    document.querySelectorAll('.sidebar-tab').forEach(t => {
        t.classList.toggle('active', t.dataset.tab === tabName);
    });
    document.querySelectorAll('.tab-panel').forEach(p => {
        p.classList.toggle('active', p.id === 'panel-' + tabName);
    });
}

/* ── Active filter chips ── */

function renderActiveFilters() {
    const container = document.getElementById('active-filters');
    if (!activeRole && !activeCompany) {
        container.innerHTML = '';
        return;
    }
    let html = '';
    if (activeRole) {
        html += `
            <div class="filter-chip">
                <span>${escapeHtml(activeRole)}</span>
                <button class="chip-remove" data-type="role" aria-label="직무 필터 해제">&times;</button>
            </div>
        `;
    }
    if (activeCompany) {
        html += `
            <div class="filter-chip">
                <span>${escapeHtml(activeCompany)}</span>
                <button class="chip-remove" data-type="company" aria-label="회사 필터 해제">&times;</button>
            </div>
        `;
    }
    container.innerHTML = html;
    container.querySelectorAll('.chip-remove').forEach(btn => {
        btn.onclick = () => {
            if (btn.dataset.type === 'role') {
                activeRole = null;
                switchTab('roles');
            } else {
                activeCompany = null;
            }
            renderFilters();
            render();
        };
    });
}

function renderFilters() {
    renderActiveFilters();

    // 현재 회사 필터 기준으로 role 카운트
    const baseForRole = activeCompany
        ? allJobs.filter(j => j.company === activeCompany)
        : allJobs;

    const roleCounts = {};
    baseForRole.forEach(j => {
        const r = j.role || '기타';
        roleCounts[r] = (roleCounts[r] || 0) + 1;
    });

    // 항상 8개 role을 고정 순서로 표시 (0건이어도 표시 — UI 흔들림 방지)
    const roleList = document.getElementById('role-list');
    roleList.innerHTML = `
        <div class="filter-item ${!activeRole ? 'active' : ''}" data-role="">
            <span>전체</span><span class="filter-count">${baseForRole.length}</span>
        </div>
    ` + Object.keys(ROLE_COLOR).map(role => {
        const n = roleCounts[role] || 0;
        const isEmpty = n === 0;
        return `
        <div class="filter-item ${activeRole === role ? 'active' : ''} ${isEmpty ? 'filter-empty' : ''}"
             data-role="${escapeHtml(role)}">
            <span>${escapeHtml(role)}</span>
            <span class="filter-count">${n}</span>
        </div>`;
    }).join('');

    roleList.querySelectorAll('.filter-item').forEach(el => {
        el.onclick = () => {
            activeRole = el.dataset.role || null;
            renderFilters();
            render();
            if (activeRole) {
                switchTab('companies');
            }
        };
    });

    // 현재 role 필터 기준으로 회사 카운트
    const baseForCompany = activeRole
        ? allJobs.filter(j => (j.role || '기타') === activeRole)
        : allJobs;

    const compCounts = {};
    baseForCompany.forEach(j => {
        compCounts[j.company] = (compCounts[j.company] || 0) + 1;
    });

    // 전체 회사 목록: data.results 키(크롤링된 모든 회사) + 실제 job 회사명 합산
    const allCompanies = [...new Set([
        ...Object.keys(window._jobResults || {}),
        ...allJobs.map(j => j.company)
    ])].sort((a, b) => a.localeCompare(b, 'ko'));

    const compList = document.getElementById('company-list');
    compList.innerHTML = `
        <div class="filter-item ${!activeCompany ? 'active' : ''}" data-comp="">
            <span>전체</span><span class="filter-count">${baseForCompany.length}</span>
        </div>
    ` + allCompanies.map(c => {
        const n = compCounts[c] || 0;
        const isEmpty = n === 0;
        return `
        <div class="filter-item ${activeCompany === c ? 'active' : ''} ${isEmpty ? 'filter-empty' : ''}"
             data-comp="${escapeHtml(c)}">
            <span>${escapeHtml(c)}</span>
            <span class="filter-count">${n}</span>
        </div>`;
    }).join('');

    compList.querySelectorAll('.filter-item').forEach(el => {
        el.onclick = () => {
            activeCompany = el.dataset.comp || null;
            renderFilters();
            render();
        };
    });
}

/* ── Freshness ── */

function getFreshness(job) {
    const posted = parseDate(job.posted_date);
    if (!posted) return null;
    const now = new Date();
    const diffDays = (now - posted) / (1000 * 60 * 60 * 24);
    if (diffDays <= 3) return 'new';
    if (diffDays <= 7) return 'recent';
    return null;
}

function parseDate(str) {
    if (!str) return null;
    const d = new Date(str);
    return isNaN(d.getTime()) ? null : d;
}

function sortJobs(jobs) {
    const arr = [...jobs];
    if (sortOrder === 'latest') {
        arr.sort((a, b) => {
            const da = parseDate(a.posted_date);
            const db = parseDate(b.posted_date);
            if (da && db) return db - da;
            if (da) return -1;
            if (db) return 1;
            return 0;
        });
    } else if (sortOrder === 'location') {
        arr.sort((a, b) => {
            const la = a.location || '위치 정보 없음';
            const lb = b.location || '위치 정보 없음';
            return la.localeCompare(lb, 'ko');
        });
    }
    return arr;
}

function render() {
    const search = document.getElementById('search').value.trim().toLowerCase();

    let filtered = allJobs.filter(j => {
        if (activeRole && (j.role || '기타') !== activeRole) return false;
        if (activeCompany && j.company !== activeCompany) return false;
        if (search) {
            const text = `${j.title} ${j.company} ${j.department || ''} ${j.location || ''}`.toLowerCase();
            if (!text.includes(search)) return false;
        }
        return true;
    });

    filtered = sortJobs(filtered);
    currentFiltered = filtered;
    document.getElementById('count').textContent = `${filtered.length.toLocaleString()}개`;

    const jobsEl = document.getElementById('jobs');
    const emptyEl = document.getElementById('empty');

    if (filtered.length === 0) {
        jobsEl.classList.add('hidden');
        emptyEl.classList.remove('hidden');
        return;
    }

    jobsEl.classList.remove('hidden');
    emptyEl.classList.add('hidden');

    jobsEl.innerHTML = filtered.map((j, i) => {
        const role = j.role || '기타';
        const roleClass = ROLE_COLOR[role] || 'role-etc';

        // freshness
        const freshness = getFreshness(j);
        const freshnessClass = freshness ? `job-${freshness}` : '';
        const newBadge = freshness === 'new' ? '<span class="badge-new">NEW</span>' : '';

        // 날짜: posted_date 파싱 → 실패 시 crawled_at 수집일로 폴백
        const postedDate = parseDate(j.posted_date);
        const crawledDate = parseDate(j.crawled_at);
        let dateLabel = '';
        if (postedDate) {
            dateLabel = postedDate.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' });
        } else if (crawledDate) {
            dateLabel = `수집 ${crawledDate.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' })}`;
        }

        // 위치: 없으면 '정보 없음'
        const locationStr = j.location ? escapeHtml(j.location) : '위치 정보 없음';

        return `
        <a href="${safeUrl(j.url)}" target="_blank" rel="noopener noreferrer"
           class="job-card ${freshnessClass}" data-index="${i}">
            <div class="job-header">
                <span class="job-company">${escapeHtml(j.company)}${newBadge}</span>
                <span class="role-tag ${roleClass}">${escapeHtml(role)}</span>
            </div>
            <div class="job-title">${escapeHtml(j.title)}</div>
            <div class="job-meta">
                <span>📍 ${locationStr}</span>
                ${j.department ? `<span>🏷️ ${escapeHtml(j.department)}</span>` : ''}
                <span>📅 ${dateLabel}</span>
            </div>
        </a>`;
    }).join('');
}

/* ── Tooltip ── */

function initTooltip() {
    const tooltip = document.getElementById('job-tooltip');
    const jobsContainer = document.getElementById('jobs');

    jobsContainer.addEventListener('mouseover', (e) => {
        const card = e.target.closest('.job-card');
        if (!card) return;
        const index = card.dataset.index;
        if (index == null) return;
        const job = currentFiltered[index];
        // description, employment_type, salary 중 하나라도 있어야 표시
        if (!job.description && !job.employment_type && !job.salary) return;

        const meta = [];
        if (job.employment_type) meta.push(escapeHtml(job.employment_type));
        if (job.salary) meta.push(`급여: ${escapeHtml(job.salary)}`);
        const metaLine = meta.length
            ? `<div class="tooltip-meta">${meta.join(' · ')}</div>`
            : '';

        tooltip.innerHTML = `
            ${metaLine}
            ${job.description ? `<div class="tooltip-desc">${escapeHtml(job.description)}</div>` : ''}
        `;

        const rect = card.getBoundingClientRect();
        const tooltipHeight = 100; // approximate
        let top = rect.top + window.scrollY - tooltipHeight - 8;
        if (rect.top < tooltipHeight + 16) {
            // show below if not enough space above
            top = rect.bottom + window.scrollY + 8;
        }
        tooltip.style.top = top + 'px';
        tooltip.style.left = (rect.left + rect.width / 2) + 'px';
        tooltip.classList.add('visible');
    });

    jobsContainer.addEventListener('mouseout', (e) => {
        const card = e.target.closest('.job-card');
        if (!card) return;
        // check if we're moving to a child of the same card
        if (card.contains(e.relatedTarget)) return;
        tooltip.classList.remove('visible');
    });
}

function escapeHtml(s) {
    if (!s) return '';
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function safeUrl(url) {
    if (!url) return '#';
    try {
        const parsed = new URL(url);
        if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') return '#';
        return parsed.href;
    } catch {
        return '#';
    }
}

document.getElementById('search').addEventListener('input', render);
document.getElementById('sort').addEventListener('change', e => {
    sortOrder = e.target.value;
    render();
});

load();
