let allJobs = [];
let activeCategory = null;
let activeCompany = null;

async function load() {
    try {
        const res = await fetch('data/jobs.json?t=' + Date.now());
        const data = await res.json();
        allJobs = data.jobs || [];
        
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
    // 카테고리
    const catCounts = {};
    allJobs.forEach(j => catCounts[j.category] = (catCounts[j.category] || 0) + 1);
    
    const catList = document.getElementById('category-list');
    catList.innerHTML = `
        <div class="filter-item ${!activeCategory ? 'active' : ''}" data-cat="">
            <span>전체</span><span class="filter-count">${allJobs.length}</span>
        </div>
    ` + Object.entries(catCounts).sort((a,b) => b[1]-a[1]).map(([cat, n]) => `
        <div class="filter-item ${activeCategory === cat ? 'active' : ''}" data-cat="${cat}">
            <span>${cat}</span><span class="filter-count">${n}</span>
        </div>
    `).join('');
    
    catList.querySelectorAll('.filter-item').forEach(el => {
        el.onclick = () => {
            activeCategory = el.dataset.cat || null;
            renderFilters();
            render();
        };
    });
    
    // 회사 (활성 카테고리 기준)
    const filteredForCompany = activeCategory 
        ? allJobs.filter(j => j.category === activeCategory)
        : allJobs;
    const compCounts = {};
    filteredForCompany.forEach(j => compCounts[j.company] = (compCounts[j.company] || 0) + 1);
    
    const compList = document.getElementById('company-list');
    compList.innerHTML = `
        <div class="filter-item ${!activeCompany ? 'active' : ''}" data-comp="">
            <span>전체</span><span class="filter-count">${filteredForCompany.length}</span>
        </div>
    ` + Object.entries(compCounts).sort((a,b) => b[1]-a[1]).map(([c, n]) => `
        <div class="filter-item ${activeCompany === c ? 'active' : ''}" data-comp="${c}">
            <span>${c}</span><span class="filter-count">${n}</span>
        </div>
    `).join('');
    
    compList.querySelectorAll('.filter-item').forEach(el => {
        el.onclick = () => {
            activeCompany = el.dataset.comp || null;
            renderFilters();
            render();
        };
    });
}

function render() {
    const search = document.getElementById('search').value.trim().toLowerCase();
    
    const filtered = allJobs.filter(j => {
        if (activeCategory && j.category !== activeCategory) return false;
        if (activeCompany && j.company !== activeCompany) return false;
        if (search) {
            const text = `${j.title} ${j.company} ${j.department} ${j.location}`.toLowerCase();
            if (!text.includes(search)) return false;
        }
        return true;
    });
    
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
    
    jobsEl.innerHTML = filtered.map(j => `
        <a href="${safeUrl(j.url)}" target="_blank" rel="noopener noreferrer" class="job-card">
            <div class="job-header">
                <span class="job-company">${escapeHtml(j.company)}</span>
                <span class="job-category">${escapeHtml(j.category)}</span>
            </div>
            <div class="job-title">${escapeHtml(j.title)}</div>
            <div class="job-meta">
                ${j.location ? `<span>📍 ${escapeHtml(j.location)}</span>` : ''}
                ${j.department ? `<span>🏷️ ${escapeHtml(j.department)}</span>` : ''}
                ${j.posted_date ? `<span>📅 ${j.posted_date.slice(0,10)}</span>` : ''}
            </div>
        </a>
    `).join('');
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
load();