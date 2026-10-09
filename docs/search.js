'use strict';
/*
 * 공고 검색 — 글자가 그대로 일치하지 않아도 같은 뜻의 공고를 찾는다.
 *
 * 1. 동의어 확장: 검색어를 '개념'으로 바꾼다. "백엔드" → backend · back-end · server · 서버 …
 *    한·영 표기, 줄임말(PM, SRE), 회사 한글 이름(엔비디아)까지 같은 개념으로 묶었다.
 * 2. 연관어(약한 근거): 개념과 자주 함께 쓰이는 기술 이름. 백엔드 → spring, kotlin, java …
 * 3. 영문은 단어 단위로 비교 — "intern"이 "International"에 걸리지 않게 (복수형 -s는 허용).
 *    여러 단어 용어는 공백·하이픈 차이를 무시 ("back end" = "back-end" = "backend").
 *    한글은 띄어쓰기가 제각각이라 공백을 뺀 부분일치.
 * 4. 오타 허용: 5글자 이상 영문 단어는 한 글자 틀려도 제목 단어와 맞춘다 (enginer → engineer).
 *
 * 점수(관련도): 제목 일치 3 · 회사 일치 2.5 · 직무/부서/태그 일치 2 · 근무지 1.5 · 연관어(제목) 1.2 · 오타 1
 * 모든 개념이 맞는 공고만 보여 주고, 하나도 없으면 일부 개념만 맞는 공고로 대신한다(partial).
 */
(function () {
    // [강한 동의어 묶음, 연관어 묶음]
    const CONCEPTS = [
        [['백엔드', 'backend', 'back end', 'server', '서버', 'server side', '서버개발'],
         ['java', 'spring', 'kotlin', 'golang', 'node', 'django', 'api', 'msa', 'distributed systems']],
        [['프론트엔드', '프론트', 'frontend', 'front end', 'web frontend', '웹 프론트'],
         ['react', 'typescript', 'javascript', 'vue', 'next.js', 'web']],
        [['풀스택', 'fullstack', 'full stack'], []],
        [['모바일', 'mobile', '앱 개발', 'app developer', 'ios', 'android', '안드로이드'], ['swift', 'kotlin', 'flutter']],
        [['ios', '아이오에스', '아이폰'], ['swift']],
        [['안드로이드', 'android'], ['kotlin']],
        [['데브옵스', 'devops', 'sre', 'site reliability', '인프라', 'infrastructure', 'infra', '클라우드', 'cloud'],
         ['kubernetes', 'k8s', 'aws', 'terraform', 'platform']],
        [['데이터 엔지니어', 'data engineer', 'data engineering'], ['airflow', 'spark', 'hadoop', 'pipeline']],
        [['데이터 분석', 'data analyst', 'analytics', '분석가', '애널리스트'], ['sql', 'tableau']],
        [['데이터 사이언티스트', 'data scientist', 'data science'], ['statistics', '통계']],
        [['데이터', 'data'], []],
        [['머신러닝', 'machine learning', 'ml', '딥러닝', 'deep learning', '인공지능', '에이아이'],
         ['llm', 'pytorch', 'neural', 'reinforcement learning']],
        [['llm', '거대언어모델', '언어모델', 'language model', 'genai', '생성형', 'gpt'], ['nlp', 'transformer']],
        [['연구원', 'researcher', 'research scientist', 'research engineer', '리서처', '연구'], ['research']],
        [['컴퓨터 비전', 'computer vision', '비전', 'vision'], ['perception', 'image']],
        [['로봇', 'robot', 'robotics', '로보틱스', '휴머노이드', 'humanoid'], ['manipulation', 'locomotion', 'actuator']],
        [['자율주행', 'autonomous', 'autonomy', 'self driving', 'adas'], ['perception', 'planning', 'lidar', 'robotaxi']],
        [['반도체', 'semiconductor', 'chip', 'silicon', 'asic', 'soc', '칩'], ['rtl', 'verification', 'npu', 'gpu']],
        [['하드웨어', 'hardware', 'hw', '회로', 'circuit'], ['pcb', 'electrical', 'mechanical']],
        [['임베디드', 'embedded', 'firmware', '펌웨어'], ['rtos', 'c++']],
        [['보안', 'security', '정보보안', 'infosec', 'cyber', '사이버'], ['privacy', 'threat']],
        [['기획', 'product manager', 'pm', 'po', 'product owner', '프로덕트', '서비스기획', '프로덕트 매니저'], ['product']],
        [['디자인', 'design', 'designer', '디자이너', 'ux', 'ui'], ['figma']],
        [['영업', 'sales', 'account executive', 'ae', '세일즈', 'account manager', 'business development', '사업개발', 'bd'],
         ['partnership', '제휴', 'gtm']],
        [['마케팅', 'marketing', 'marketer', '마케터', '그로스', 'growth', 'pr', '홍보'], ['brand', 'content']],
        [['인사', 'hr', 'people', 'recruiter', '리크루터', '채용담당', 'talent acquisition', 'recruiting'], []],
        [['재무', 'finance', '회계', 'accounting', 'accountant'], ['tax', 'fp&a']],
        [['법무', 'legal', 'counsel', '변호사', 'lawyer', 'attorney'], ['policy', 'compliance']],
        [['고객지원', 'customer support', 'support', 'cs', '고객센터', '상담', 'customer success'], []],
        [['솔루션', 'solutions architect', 'solution architect', 'solutions engineer', 'sales engineer', '기술영업',
          'forward deployed', 'fde'], ['customer engineer', 'deployment']],
        [['qa', '테스트', 'test', 'quality assurance', '품질'], ['automation']],
        [['인턴', 'intern', 'internship', '체험형'], []],
        [['신입', 'new grad', 'entry level', 'junior', '주니어'], []],
        [['시니어', 'senior', 'staff', 'principal'], []],
        [['리드', 'lead', '팀장', 'head', '리더'], []],
        [['원격', 'remote', '재택'], []],
        [['계약직', 'contract', 'fixed term', '기간제'], []],
        [['한국', 'korea', '국내', '서울', 'seoul'], ['pangyo', '판교', 'seongnam']],
        [['판교', 'pangyo', '성남', 'seongnam'], []],
        [['미국', 'usa', 'us', 'united states', '북미'], ['san francisco', 'new york', 'seattle']],
        [['일본', 'japan', 'tokyo', '도쿄'], []],
        [['유럽', 'europe', 'london', '런던'], []],
        // 회사 한글 이름
        [['구글', 'google'], []], [['엔비디아', 'nvidia'], []], [['오픈에이아이', '오픈ai', 'openai'], []],
        [['앤트로픽', 'anthropic'], []], [['삼성', 'samsung'], []], [['네이버', 'naver'], []],
        [['토스', 'toss'], []], [['업스테이지', 'upstage'], []], [['퀄컴', 'qualcomm'], []],
        [['인텔', 'intel'], []], [['미디어텍', 'mediatek'], []], [['웨이모', 'waymo'], []],
        [['보스턴다이나믹스', '보스턴 다이나믹스', 'boston dynamics'], []], [['피규어', 'figure ai'], []],
        [['엘지', 'lg'], []], [['하이닉스', 'hynix', 'sk하이닉스'], []], [['현대', 'hyundai', '42dot'], []],
    ];

    const norm = s => (s || '').normalize('NFKC').toLowerCase();
    const compact = s => norm(s).replace(/[\s\-_./·・,]+/g, '');
    const isAscii = s => /^[\x00-\x7f]+$/.test(s);
    const escRe = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

    // 용어 하나를 '텍스트에 있나?' 함수로
    function matcher(term) {
        const t = norm(term);
        if (isAscii(t)) {
            // 단어 경계 + 복수형 허용. 여러 단어면 사이 공백·하이픈 차이도 허용
            const words = t.split(/[\s\-]+/).filter(Boolean).map(escRe);
            const body = words.join('[\\s\\-/]*');
            const re = new RegExp(`(^|[^a-z0-9])${body}(s|es)?($|[^a-z0-9])`);
            return { test: (n) => re.test(n.text), term: t };
        }
        const c = compact(t);
        return { test: (n) => n.text.includes(t) || n.compact.includes(c), term: t };
    }

    const TERM_TO_CONCEPTS = new Map();
    CONCEPTS.forEach(([strong], i) => strong.forEach(t => {
        const k = compact(t);
        if (!TERM_TO_CONCEPTS.has(k)) TERM_TO_CONCEPTS.set(k, []);
        TERM_TO_CONCEPTS.get(k).push(i);
    }));
    const COMPILED = CONCEPTS.map(([strong, related]) => ({
        strong: strong.map(matcher), related: related.map(matcher), label: strong,
    }));

    function lev1(a, b) {   // 편집 거리 ≤ 1 인가
        if (a === b) return true;
        if (Math.abs(a.length - b.length) > 1) return false;
        let i = 0, j = 0, diff = 0;
        while (i < a.length && j < b.length) {
            if (a[i] === b[j]) { i++; j++; continue; }
            if (++diff > 1) return false;
            if (a.length > b.length) i++;
            else if (b.length > a.length) j++;
            else { i++; j++; }
        }
        return diff + (a.length - i) + (b.length - j) <= 1;
    }

    // 공고별 검색용 텍스트 미리 계산
    function index(job) {
        const meta = [job.role, job.role_group, job.department, ...(job.tags || []), job.seniority, job.employment].filter(Boolean).join(' ');
        const place = [job.location, ...(job.regions || [])].filter(Boolean).join(' ');
        const mk = s => ({ text: norm(s), compact: compact(s) });
        job._s = {
            title: mk(job.title),
            company: mk(job.company),
            meta: mk(meta),
            place: mk(place),
            words: norm(job.title).split(/[^a-z0-9]+/).filter(w => w.length >= 4),
        };
    }

    // 검색어 → 개념 목록. 두 단어 구("machine learning")를 먼저 사전에서 찾는다
    function parse(q) {
        const toks = norm(q).split(/\s+/).filter(Boolean);
        const concepts = [];
        for (let i = 0; i < toks.length; i++) {
            const pair = i + 1 < toks.length ? compact(toks[i] + toks[i + 1]) : null;
            if (pair && TERM_TO_CONCEPTS.has(pair)) {
                concepts.push({ raw: `${toks[i]} ${toks[i + 1]}`, ids: TERM_TO_CONCEPTS.get(pair) });
                i++;
            } else {
                concepts.push({ raw: toks[i], ids: TERM_TO_CONCEPTS.get(compact(toks[i])) || [] });
            }
        }
        return concepts;
    }

    // 개념 하나에 대한 공고 점수 (0이면 불일치) + 제목에서 맞은 용어
    function scoreConcept(job, c) {
        const s = job._s;
        const raw = matcher(c.raw);
        const strong = [raw, ...c.ids.flatMap(i => COMPILED[i].strong)];
        const related = c.ids.flatMap(i => COMPILED[i].related);
        let best = 0;
        const hits = [];
        for (const m of strong) {
            if (m.test(s.title)) { best = Math.max(best, 3); hits.push(m.term); }
            else if (m.test(s.company)) best = Math.max(best, 2.5);
            else if (m.test(s.meta)) best = Math.max(best, 2);
            else if (m.test(s.place)) best = Math.max(best, 1.5);
        }
        // 연관어는 제목에 있을 때만 — 부서·태그까지 보면 너무 넓어진다
        if (best < 1.2) {
            for (const m of related) {
                if (m.test(s.title)) { best = 1.2; hits.push(m.term); break; }
            }
        }
        // 오타: 사전에 없는 5글자 이상 영문 단어만
        let typo = '';
        if (!best && !c.ids.length && isAscii(c.raw) && c.raw.length >= 5) {
            const w = s.words.find(w => lev1(w, c.raw));
            if (w) { best = 1; hits.push(w); typo = w; }
        }
        return [best, hits, typo];
    }

    /** 검색 실행. 반환: { scores: Map(job→점수), hits: Map(job→[제목에서 맞은 용어]), partial, expansions } */
    function run(jobs, q) {
        const concepts = parse(q);
        const scores = new Map();
        const hits = new Map();
        const partialScores = new Map();
        for (const j of jobs) {
            if (!j._s) index(j);
            let total = 0, matched = 0;
            const h = [];
            for (const c of concepts) {
                const [sc, ht, typo] = scoreConcept(j, c);
                if (sc > 0) { matched++; total += sc; h.push(...ht); }
                if (typo) (c.typos ||= new Set()).add(typo);
            }
            if (!matched) continue;
            hits.set(j, h);
            if (matched === concepts.length) scores.set(j, total);
            else partialScores.set(j, total + matched * 10);   // 더 많은 개념이 맞을수록 위로
        }
        const partial = scores.size === 0 && partialScores.size > 0;
        const expansions = concepts.filter(c => c.ids.length).map(c => ({
            query: c.raw,
            terms: [...new Set(c.ids.flatMap(i => COMPILED[i].label))].filter(t => compact(t) !== compact(c.raw)).slice(0, 5),
        }));
        // 오타로 찾은 단어 (가장 많이 쓰인 교정어 하나)
        const corrections = concepts.filter(c => c.typos && c.typos.size && !c.ids.length)
            .map(c => ({ query: c.raw, fixed: [...c.typos][0] }));
        return { scores: partial ? partialScores : scores, hits, partial, expansions, corrections };
    }

    window.JobSearch = { run, norm };
})();
