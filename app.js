async function load() {
    try {
        // 실제 데이터 시도
        let res = await fetch('data/jobs.json?t=' + Date.now());
        if (!res.ok) throw new Error('No live data');
        const data = await res.json();
        if (!data.jobs || data.jobs.length === 0) throw new Error('Empty');
        
        allJobs = data.jobs;
        renderHeader(data);
        renderFilters();
        render();
    } catch (e) {
        // 샘플 데이터로 폴백
        try {
            const res = await fetch('data/jobs.sample.json');
            const data = await res.json();
            allJobs = data.jobs || [];
            
            renderHeader(data);
            renderFilters();
            render();
            
            // 샘플 데이터 알림 추가
            const banner = document.createElement('div');
            banner.style.cssText = 'background:#fff3cd;color:#856404;padding:12px 20px;text-align:center;font-size:13px;border-bottom:1px solid #ffeaa7;';
            banner.innerHTML = '📌 <strong>Demo Mode</strong> — Showing sample data. Run <code>python main.py</code> locally to see real jobs.';
            document.body.insertBefore(banner, document.body.firstChild);
        } catch (e2) {
            document.getElementById('updated').textContent = '데이터를 불러올 수 없습니다';
        }
    }
}