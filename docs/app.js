'use strict';

// ── 기본 분류 체계 (jobs.json에 taxonomy가 없을 때만 사용) ──────────────────
const DEFAULT_TAXONOMY = {
    groups: {
        '엔지니어링': ['AI / ML', '소프트웨어 개발', '데이터', '하드웨어 / 반도체', '로보틱스 / 자율주행', '제조 / 품질', '보안'],
        '제품 · 디자인': ['제품 / 기획', '디자인'],
        '비즈니스': ['영업 / 사업개발', '솔루션 / 고객지원', '마케팅 / PR'],
        '운영 · 지원': ['운영 / 전략', '리스크 / 컴플라이언스', '법무 / 정책', '경영지원'],
    },
    levels: ['인턴', '신입/주니어', '경력', '시니어', '리더'],
    regions: ['한국', '북미', '유럽', '아시아·태평양', '원격', '기타'],
};
// 직군 태그 색 — CSP(style-src)가 인라인 style을 막으므로 클래스로
const GROUP_TAG = { '엔지니어링': 't-eng', '제품 · 디자인': 't-prod', '비즈니스': 't-biz', '운영 · 지원': 't-ops', '기타': 't-etc' };
// docs/logos/ 에 저장한 회사 로고. 없으면 이니셜 배지
const LOGOS = {
    'NVIDIA': 'nvidia', 'Google': 'google', 'Anthropic': 'anthropic', 'OpenAI': 'openai',
    'Samsung': 'samsung', 'Naver': 'navercorp', 'Toss': 'toss', 'Upstage': 'upstage',
    'LG AI연구원': 'lgresearch', 'LG전자': 'lge', '42dot': '42dot', 'Boston Dynamics': 'bostondynamics',
    'Figure AI': 'figure', '1X': '1x', 'Physical Intelligence': 'physicalintelligence', 'Skild AI': 'skild',
    'Agility Robotics': 'agilityrobotics', 'Waymo': 'waymo', 'Wayve': 'wayve', 'Motional': 'motional',
    'Qualcomm': 'qualcomm', 'Intel': 'intel', 'MediaTek': 'mediatek', 'AMD': 'amd', 'SK하이닉스': 'skhynix',
};
// 가로로 긴 워드마크 로고는 칸 안 여백을 줄여야 글자가 읽힌다
const WIDE_LOGOS = new Set(['Samsung', 'SK하이닉스', 'AMD', 'Qualcomm', 'MediaTek']);
const MONO_COLOR = {};
const CATEGORY_ORDER = ['외국계', '대기업', 'IT', '금융', '제조업', '스타트업'];
const PAGE_SIZE = 50;
const NEW_DAYS = 2;     // NEW 배지: 오늘·어제 처음 본 공고
const WEEK_DAYS = 7;    // '새 공고' 기준

// ── 상태 ───────────────────────────────────────────────────────────────
const state = {
    q: '', group: '', role: '', company: '', sector: '', level: '', region: '',
    kr: false, fresh: false, sort: 'recent',
};
let data = { jobs: [], sources: {}, taxonomy: DEFAULT_TAXONOMY };
let companyMeta = {};
let today = '';
let shown = PAGE_SIZE;
let filtered = [];
let search = null;   // 현재 검색 결과 (JobSearch.run) — 검색어가 없으면 null

const $ = id => document.getElementById(id);

// ── 유틸 ───────────────────────────────────────────────────────────────
function esc(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function safeUrl(url) {
    try {
        const u = new URL(url);
        return (u.protocol === 'https:' || u.protocol === 'http:') ? u.href : '#';
    } catch { return '#'; }
}
const kstDate = d => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(d);
function parseDate(str) {
    if (!str) return null;
    let s = str;
    // 오프셋 없는 과거 기록은 UTC — 'Z'를 붙여야 브라우저 로컬 시간으로 오인하지 않는다
    if (/^\d{4}-\d{2}-\d{2}T/.test(s) && !/(Z|[+-]\d{2}:?\d{2})$/.test(s)) s += 'Z';
    const d = new Date(s);
    return isNaN(d.getTime()) ? null : d;
}
const dayDiff = (a, b) => Math.round((Date.parse(a) - Date.parse(b)) / 86400000);
function relDate(ymd) {
    const n = dayDiff(today, ymd);
    if (n <= 0) return '오늘';
    if (n === 1) return '어제';
    if (n < 7) return `${n}일 전`;
    if (n < 30) return `${Math.floor(n / 7)}주 전`;
    const [, m, d] = ymd.split('-');
    return `${Number(m)}월 ${Number(d)}일`;
}
function hash(s) { let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) | 0; return Math.abs(h); }
function logo(company, cls = '') {
    const file = LOGOS[company];
    if (file) {
        const wide = WIDE_LOGOS.has(company) ? 'logo-wide' : '';
        return `<img class="logo ${wide} ${cls}" src="logos/${file}.png" alt="" loading="lazy" data-company="${esc(company)}">`;
    }
    return monogram(company, cls);
}
function monogram(company, cls = '') {
    const color = MONO_COLOR[company] ?? hash(company) % 8;
    const letters = /^[A-Za-z0-9]/.test(company) ? company.replace(/[^A-Za-z0-9]/g, '').slice(0, 3) : company.slice(0, 2);
    return `<span class="logo logo-mono mono-${color} ${cls}" aria-hidden="true">${esc(letters)}</span>`;
}

// ── 데이터 준비 ─────────────────────────────────────────────────────────
function prepare(raw) {
    data = raw;
    data.taxonomy = raw.taxonomy || DEFAULT_TAXONOMY;
    const updated = parseDate(raw.updated_at);
    today = updated ? kstDate(updated) : kstDate(new Date());

    companyMeta = {};
    for (const src of Object.values(raw.sources || {})) {
        companyMeta[src.company] = {
            category: src.category || '', sectors: src.sectors || [],
            status: src.status || 'ok', last_success: src.last_success || '', error: src.error || '',
        };
    }
    for (const j of raw.jobs) {
        if (!companyMeta[j.company]) companyMeta[j.company] = { category: j.category || '', sectors: [], status: 'ok' };
        // 등록일이 있으면 등록일, 없으면 처음 발견한 날 — 둘 다 있으면 더 이른 쪽
        const posted = (j.posted_date || '').slice(0, 10);
        const seen = j.first_seen || '';
        j._when = posted && (!seen || posted <= seen) ? posted : seen;
        j._age = seen ? dayDiff(today, seen) : Infinity;
        j._regions = j.regions || [];
        j._sectors = companyMeta[j.company].sectors;
        j._group = j.role_group || '기타';
    }
}

// ── 필터 ───────────────────────────────────────────────────────────────
function matches(j, except = '') {
    if (except !== 'group' && state.group && j._group !== state.group) return false;
    if (except !== 'role' && except !== 'group' && state.role && (j.role || '기타') !== state.role) return false;
    if (except !== 'company' && state.company && j.company !== state.company) return false;
    if (except !== 'sector' && state.sector && !j._sectors.includes(state.sector)) return false;
    if (except !== 'level' && state.level && j.seniority !== state.level) return false;
    if (except !== 'region' && state.region && !j._regions.includes(state.region)) return false;
    if (except !== 'kr' && state.kr && !j._regions.includes('한국')) return false;
    if (except !== 'fresh' && state.fresh && !(j._age < WEEK_DAYS)) return false;
    if (search && !search.scores.has(j)) return false;
    return true;
}
function countBy(except, keyFn) {
    const counts = {};
    for (const j of data.jobs) {
        if (!matches(j, except)) continue;
        for (const k of [].concat(keyFn(j))) counts[k] = (counts[k] || 0) + 1;
    }
    return counts;
}
function sortJobs(arr) {
    const recent = (a, b) => (b._when || '').localeCompare(a._when || '');
    if (state.sort === 'relevance' && search) {
        return arr.sort((a, b) => search.scores.get(b) - search.scores.get(a) || recent(a, b));
    }
    return arr.sort(state.sort === 'company'
        ? (a, b) => a.company.localeCompare(b.company, 'ko') || recent(a, b)
        : (a, b) => recent(a, b) || a.company.localeCompare(b.company, 'ko'));
}

// 제목에서 검색어(또는 같은 뜻의 말)와 맞은 부분 강조
function highlight(title, terms) {
    const safe = esc(title);
    const uniq = [...new Set(terms)].filter(t => t && t.length >= 2).sort((a, b) => b.length - a.length);
    if (!uniq.length) return safe;
    const re = new RegExp(uniq.map(t => {
        const e = esc(t).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        return /^[a-z0-9]{1,3}$/.test(t) ? `(?<![a-z0-9])${e}(?![a-z0-9])` : e;
    }).join('|'), 'gi');
    return safe.replace(re, '<mark>$&</mark>');
}

function renderSearchHint() {
    const el = $('search-hint');
    if (!search) { el.hidden = true; return; }
    const parts = search.expansions.filter(x => x.terms.length)
        .map(x => `<b>${esc(x.query)}</b> → ${x.terms.map(esc).join(' · ')}`);
    let html = parts.length ? `같은 뜻의 말도 함께 찾았어요: ${parts.join(' / ')}` : '';
    const fixes = search.corrections.map(x => `<b>${esc(x.query)}</b> → ${esc(x.fixed)}`);
    if (fixes.length) html = `오타로 보여서 고쳐서 찾았어요: ${fixes.join(' / ')} ${html}`;
    if (search.partial) html = `모든 검색어가 맞는 공고는 없어서, 일부만 맞는 공고를 보여 드려요. ${html}`;
    el.innerHTML = html;
    el.hidden = !html;
}
const activeCount = () =>
    ['q', 'group', 'company', 'sector', 'level', 'region', 'kr', 'fresh'].filter(k => state[k]).length;

// ── 렌더: 상단 ──────────────────────────────────────────────────────────
function renderHero() {
    const updated = parseDate(data.updated_at);
    $('updated').textContent = updated
        ? `${updated.toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit' })} 업데이트`
        : '';
    const total = data.jobs.length;
    const fresh = data.jobs.filter(j => j._age < WEEK_DAYS).length;
    const kr = data.jobs.filter(j => j._regions.includes('한국')).length;
    const companies = Object.keys(companyMeta).length;
    $('hero-title').innerHTML = `<em>${total.toLocaleString()}개</em>의 포지션이 열려 있어요`;
    $('hero-sub').innerHTML = `${companies}개 회사 · 이번 주 새 공고 <b>${fresh.toLocaleString()}</b> · 한국 근무 <b>${kr.toLocaleString()}</b>`;

    const broken = Object.entries(companyMeta).filter(([, m]) => m.status === 'stale' || m.status === 'failed');
    $('alerts').innerHTML = broken.map(([name, m]) => {
        const since = m.last_success ? `${relDate(m.last_success)}부터` : '최근';
        const tail = m.status === 'failed'
            ? '닫힌 공고가 섞이지 않도록 이 회사 공고는 잠시 내려 두었어요.'
            : '마지막으로 받은 공고를 보여 드리고 있어요.';
        const why = m.error ? `<span class="alert-why">원인: ${esc(m.error)}</span>` : '';
        return `<p class="alert"><span>${esc(name)} 공고가 ${since} 새로 수집되지 않고 있어요. ${tail}</span>${why}</p>`;
    }).join('');
}

function renderCompanyStrip() {
    // 이번 주 새 공고가 많은 순 → 전체 공고 많은 순
    const stats = {};
    for (const j of data.jobs) {
        const s = stats[j.company] ||= { total: 0, fresh: 0 };
        s.total++;
        if (j._age < WEEK_DAYS) s.fresh++;
    }
    const top = Object.entries(stats)
        .sort((a, b) => b[1].fresh - a[1].fresh || b[1].total - a[1].total);
    $('company-strip').innerHTML = top.map(([name, s]) => `
        <button type="button" class="company-card" data-company="${esc(name)}" aria-pressed="${state.company === name}">
            ${logo(name)}
            <span class="company-card-name">${esc(name)}</span>
            <span class="company-card-meta">${s.total.toLocaleString()}개 포지션${s.fresh ? ` · <span class="plus">+${s.fresh}</span>` : ''}</span>
        </button>`).join('');
    $('company-strip').querySelectorAll('.company-card').forEach(el => {
        el.onclick = () => { state.company = state.company === el.dataset.company ? '' : el.dataset.company; update(); };
    });
}
function syncCompanyStrip() {
    $('company-strip').querySelectorAll('.company-card').forEach(el => {
        el.setAttribute('aria-pressed', state.company === el.dataset.company);
    });
}

// ── 회사 캐러셀: 3초마다 한 칸, 끝에 닿으면 처음으로. 마우스·포커스·터치 중엔 멈춤 ──
function initCarousel() {
    const strip = $('company-strip');
    const prev = $('carousel-prev');
    const next = $('carousel-next');
    const box = $('carousel');
    const total = strip.children.length;
    const step = () => {
        const card = strip.querySelector('.company-card');
        return card ? card.getBoundingClientRect().width + 12 : 184;
    };
    const atEnd = () => strip.scrollLeft + strip.clientWidth >= strip.scrollWidth - 4;
    const sync = () => {
        prev.disabled = strip.scrollLeft <= 4;
        const s = step();
        const first = Math.round(strip.scrollLeft / s) + 1;
        const last = Math.min(total, first + Math.max(1, Math.floor((strip.clientWidth + 12) / s)) - 1);
        $('carousel-pos').textContent = `${first}–${last} / ${total}개 회사`;
    };
    const go = dir => {
        if (dir > 0 && atEnd()) strip.scrollTo({ left: 0 });
        else strip.scrollBy({ left: dir * step() });
    };
    let paused = false;
    let resumeTimer;
    const pauseFor = ms => {
        paused = true;
        clearTimeout(resumeTimer);
        resumeTimer = setTimeout(() => { paused = false; }, ms);
    };
    prev.onclick = () => { go(-1); pauseFor(6000); };
    next.onclick = () => { go(1); pauseFor(6000); };
    box.addEventListener('mouseenter', () => { clearTimeout(resumeTimer); paused = true; });
    box.addEventListener('mouseleave', () => { paused = false; });
    box.addEventListener('focusin', () => { clearTimeout(resumeTimer); paused = true; });
    box.addEventListener('focusout', () => { paused = false; });
    strip.addEventListener('touchstart', () => pauseFor(8000), { passive: true });
    strip.addEventListener('scroll', sync, { passive: true });
    addEventListener('resize', sync);
    sync();
    if (!matchMedia('(prefers-reduced-motion: reduce)').matches) {
        setInterval(() => { if (!paused && !document.hidden) go(1); }, 3000);
    }
}

// ── 렌더: 직군 탭 · 직무 알약 ───────────────────────────────────────────
function renderGroups() {
    const gc = countBy('group', j => j._group);
    const groups = [...Object.keys(data.taxonomy.groups), '기타'];
    const all = data.jobs.filter(j => matches(j, 'group')).length;
    $('group-tabs').innerHTML =
        `<button type="button" class="group-tab" role="tab" data-group="" aria-selected="${!state.group}">전체 <span class="n">${all.toLocaleString()}</span></button>` +
        groups.map(g => `<button type="button" class="group-tab" role="tab" data-group="${esc(g)}" aria-selected="${state.group === g}">${esc(g)} <span class="n">${(gc[g] || 0).toLocaleString()}</span></button>`).join('');
    $('group-tabs').querySelectorAll('.group-tab').forEach(el => {
        el.onclick = () => { state.group = el.dataset.group; state.role = ''; update(); };
    });

    const roles = state.group && data.taxonomy.groups[state.group];
    if (!roles) { $('role-pills').innerHTML = ''; return; }
    const rc = countBy('role', j => j.role || '기타');
    $('role-pills').innerHTML = roles.map(r =>
        `<button type="button" class="role-pill" data-role="${esc(r)}" aria-pressed="${state.role === r}">${esc(r)}<span class="n">${rc[r] || 0}</span></button>`).join('');
    $('role-pills').querySelectorAll('.role-pill').forEach(el => {
        el.onclick = () => { state.role = state.role === el.dataset.role ? '' : el.dataset.role; update(); };
    });
}

// ── 렌더: 드롭다운 칩 ───────────────────────────────────────────────────
const CARET = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
const MENUS = {
    company: { label: '회사', all: '전체 회사' },
    sector: { label: '분야', all: '전체 분야' },
    level: { label: '경력', all: '전체 경력' },
    region: { label: '지역', all: '전체 지역' },
};

function renderChips() {
    const chips = Object.entries(MENUS).map(([key, m]) => {
        const on = !!state[key];
        return `<button type="button" class="chip ${on ? 'is-on' : ''}" data-menu="${key}" aria-haspopup="true">${esc(on ? state[key] : m.label)}${CARET}</button>`;
    });
    chips.push('<span class="chip-sep" aria-hidden="true"></span>');
    chips.push(`<button type="button" class="chip ${state.kr ? 'is-on' : ''}" data-toggle="kr" aria-pressed="${state.kr}">한국 근무</button>`);
    chips.push(`<button type="button" class="chip ${state.fresh ? 'is-on' : ''}" data-toggle="fresh" aria-pressed="${state.fresh}">이번 주 새 공고</button>`);
    $('filter-chips').innerHTML = chips.join('');
    $('filter-chips').querySelectorAll('[data-menu]').forEach(el => { el.onclick = e => { e.stopPropagation(); openMenu(el); }; });
    $('filter-chips').querySelectorAll('[data-toggle]').forEach(el => {
        el.onclick = () => { state[el.dataset.toggle] = !state[el.dataset.toggle]; update(); };
    });
    $('sort').querySelectorAll('button').forEach(b => {
        b.setAttribute('aria-pressed', b.dataset.sort === state.sort);
        if (b.dataset.sort === 'relevance') b.hidden = !state.q;
    });
}

function menuItems(key) {
    if (key === 'company') {
        const counts = countBy('company', j => j.company);
        const byCat = {};
        for (const [name, m] of Object.entries(companyMeta)) (byCat[m.category || '기타'] ||= []).push(name);
        const cats = Object.keys(byCat).sort((a, b) => {
            const ia = CATEGORY_ORDER.indexOf(a), ib = CATEGORY_ORDER.indexOf(b);
            return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
        });
        return cats.map(cat => ({ group: cat, items: byCat[cat].sort((a, b) => a.localeCompare(b, 'ko')).map(n => ({ value: n, n: counts[n] || 0, logo: true })) }));
    }
    const values = key === 'sector'
        ? [...new Set(Object.values(companyMeta).flatMap(m => m.sectors))]
        : data.taxonomy[key === 'level' ? 'levels' : 'regions'];
    const keyFn = { sector: j => j._sectors, level: j => j.seniority || [], region: j => j._regions }[key];
    const counts = countBy(key, keyFn);
    return [{ items: values.map(v => ({ value: v, n: counts[v] || 0 })) }];
}

function openMenu(chip) {
    const pop = $('popover');
    const key = chip.dataset.menu;
    if (!pop.hidden && pop.dataset.key === key) return closeMenu();
    const sections = menuItems(key);
    let html = `<button type="button" class="pop-item" data-v="" aria-pressed="${!state[key]}"><span class="label">${MENUS[key].all}</span></button>`;
    for (const s of sections) {
        if (s.group) html += `<div class="pop-group">${esc(s.group)}</div>`;
        html += s.items.map(it => `<button type="button" class="pop-item ${it.n ? '' : 'is-empty'}" data-v="${esc(it.value)}" aria-pressed="${state[key] === it.value}">
            ${it.logo ? logo(it.value) : ''}<span class="label">${esc(it.value)}</span><span class="n">${it.n.toLocaleString()}</span></button>`).join('');
    }
    pop.innerHTML = html;
    pop.dataset.key = key;
    pop.hidden = false;
    const r = chip.getBoundingClientRect();
    const left = Math.min(r.left + scrollX, scrollX + document.documentElement.clientWidth - pop.offsetWidth - 16);
    pop.style.left = `${Math.max(16, left)}px`;
    pop.style.top = `${r.bottom + scrollY + 6}px`;
    pop.querySelectorAll('.pop-item').forEach(b => {
        b.onclick = () => { state[key] = b.dataset.v; closeMenu(); update(); };
    });
}
function closeMenu() { $('popover').hidden = true; }

// ── 렌더: 공고 목록 ─────────────────────────────────────────────────────
function jobRow(j) {
    const tagCls = GROUP_TAG[j._group] || 't-etc';
    const meta = [
        j.location,
        j.seniority,
        j.employment,
        j.department && j.department !== j.location ? j.department : '',
    ].filter(Boolean).map(esc).join(' · ');
    const isNew = j._age < NEW_DAYS;
    return `<li class="job"><a class="job-link" href="${safeUrl(j.url)}" target="_blank" rel="noopener noreferrer">
        ${logo(j.company)}
        <span class="job-main">
            <span class="job-company">${esc(j.company)}${isNew ? '<span class="badge-new">NEW</span>' : ''}${j.pool ? '<span class="badge-pool" title="특정 자리가 아닌 인재풀·상시 지원">인재풀</span>' : ''}</span>
            <span class="job-title">${search ? highlight(j.title, search.hits.get(j) || []) : esc(j.title)}</span>
            <span class="job-meta"><span class="tag-inline">${esc(j.role || '기타')} · </span>${meta}</span>
        </span>
        <span class="job-side">
            <span class="tag ${tagCls}">${esc(j.role || '기타')}</span>
            ${j._when ? `<span class="job-date">${relDate(j._when)}</span>` : ''}
        </span>
    </a></li>`;
}

function renderList() {
    const total = filtered.length;
    $('count').innerHTML = `<b>${total.toLocaleString()}개</b>의 포지션`;
    $('reset').hidden = activeCount() === 0;
    $('empty').hidden = total > 0;
    $('jobs').innerHTML = filtered.slice(0, shown).map(jobRow).join('');
    renderSearchHint();
    const left = total - shown;
    $('more').hidden = left <= 0;
    $('more').textContent = `${Math.min(left, PAGE_SIZE)}개 더 보기`;
}

// ── 상태 ↔ URL ─────────────────────────────────────────────────────────
function readUrl() {
    const p = new URLSearchParams(location.search);
    for (const k of Object.keys(state)) {
        if (p.has(k)) state[k] = typeof state[k] === 'boolean' ? p.get(k) === '1' : p.get(k);
    }
    $('search').value = state.q;
    if (state.q && !p.has('sort')) state.sort = 'relevance';
}
function writeUrl() {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(state)) {
        if (k === 'sort' && v === 'recent') continue;
        if (v === true) p.set(k, '1');
        else if (v) p.set(k, v);
    }
    const qs = p.toString();
    history.replaceState(null, '', qs ? `?${qs}` : location.pathname);
}

function update() {
    shown = PAGE_SIZE;
    search = state.q ? JobSearch.run(data.jobs, state.q) : null;
    if (!state.q && state.sort === 'relevance') state.sort = 'recent';
    filtered = sortJobs(data.jobs.filter(j => matches(j)));
    renderHero();
    syncCompanyStrip();
    renderGroups();
    renderChips();
    renderList();
    writeUrl();
}
function resetFilters() {
    Object.assign(state, { q: '', group: '', role: '', company: '', sector: '', level: '', region: '', kr: false, fresh: false });
    $('search').value = '';
    update();
}

// ── 테마 ───────────────────────────────────────────────────────────────
function initTheme() {
    let saved = null;
    try { saved = localStorage.getItem('jr-theme'); } catch { /* 저장소 차단 시 시스템 설정 사용 */ }
    if (saved === 'dark' || saved === 'light') document.documentElement.dataset.theme = saved;
    $('theme-toggle').onclick = () => {
        const cur = document.documentElement.dataset.theme
            || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
        const next = cur === 'dark' ? 'light' : 'dark';
        document.documentElement.dataset.theme = next;
        try { localStorage.setItem('jr-theme', next); } catch { /* 무시 */ }
    };
}

// ── 시작 ───────────────────────────────────────────────────────────────
function bind() {
    let t;
    $('search').addEventListener('input', e => {
        clearTimeout(t);
        t = setTimeout(() => {
            const q = e.target.value.trim();
            // 검색을 시작하면 관련도순, 검색어를 지우면 최신순으로
            if (q && !state.q && state.sort === 'recent') state.sort = 'relevance';
            state.q = q;
            update();
        }, 150);
    });
    $('sort').querySelectorAll('button').forEach(b => { b.onclick = () => { state.sort = b.dataset.sort; update(); }; });
    $('more').onclick = () => { shown += PAGE_SIZE; renderList(); };
    $('reset').onclick = resetFilters;
    $('empty-reset').onclick = resetFilters;
    document.addEventListener('click', e => { if (!$('popover').contains(e.target)) closeMenu(); });
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') {
            closeMenu();
            if (document.activeElement === $('search')) { $('search').value = ''; state.q = ''; update(); }
        }
        if (e.key === '/' && document.activeElement !== $('search')) { e.preventDefault(); $('search').focus(); }
    });
    addEventListener('resize', closeMenu);
    // 로고 파일을 못 읽으면 이니셜 배지로 교체 (error는 버블링되지 않아 캡처 단계에서 받는다)
    document.addEventListener('error', e => {
        const img = e.target;
        if (img.tagName === 'IMG' && img.classList.contains('logo')) {
            img.outerHTML = monogram(img.dataset.company || '?');
        }
    }, true);
}

async function load() {
    initTheme();
    bind();
    try {
        const res = await fetch('data/jobs.json?t=' + Date.now());
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        prepare(await res.json());
        readUrl();
        renderCompanyStrip();
        initCarousel();
        update();
    } catch (e) {
        $('hero-title').textContent = '데이터를 불러오지 못했어요';
        $('hero-sub').textContent = 'jobs.json이 없거나 손상됐어요. python main.py 로 한 번 수집해 주세요.';
        console.error(e);
    }
}

load();
