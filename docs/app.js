let allJobs = [];
let activeRole = null;
let activeCompany = null;
let sortOrder = 'latest';

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

function renderFilters() {
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
    // → 0건(Samsung 등 모집 없는 시즌)이어도 항상 표시, 가나다/ABC 순 고정
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

    jobsEl.innerHTML = filtered.map(j => {
        const role = j.role || '기타';
        const roleClass = ROLE_COLOR[role] || 'role-etc';

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
        <a href="${safeUrl(j.url)}" target="_blank" rel="noopener noreferrer" class="job-card">
            <div class="job-header">
                <span class="job-company">${escapeHtml(j.company)}</span>
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
