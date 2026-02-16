# StayPick (체류시간 기반 트렌드 콘텐츠 자동 생성기)

**한 줄:** Analytics에서 **방문수 + 체류시간** 상위 콘텐츠를 뽑아, 내용을 **요약/인사이트화**하고, 타겟 페르소나별로 **새 콘텐츠(뉴스레터/블로그/스레드/영상대본 등)** 를 자동 생성합니다.

> ⚠️ 주의: URL 크롤링은 사이트 약관/robots.txt/저작권 정책에 따라 제한될 수 있습니다.  
> 내부 문서/내가 작성한 콘텐츠/공개 허용된 자료를 대상으로 사용하는 것을 권장합니다.


## ✨ v7.1 업데이트 (해커톤용)

- **연령/라이프스테이지 타게팅**: 초등/중등/고등/대학생/20대/30대 선택 → 요약/훅/새 콘텐츠 난이도 자동 조절
- **현지화 제목 + 훅(클릭 유도)**: 카드/SEO HTML에 함께 포함 (과장 금지)
- **Programmatic SEO 내보내기**: `/{lang}/{country}/{category}/index.html` 구조로 ZIP 생성 + (옵션) sitemap.xml

---

## 1) 빠른 실행

앱을 실행하면 기본적으로 **데모 데이터로 '실시간 도파민 피드(포털형 홈)'** 화면이 바로 열립니다. 실제 데이터는 '데이터 업로드' 탭에서 교체하세요.


### (1) 설치
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### (2) OpenAI API Key 설정
```bash
export OPENAI_API_KEY="YOUR_KEY"
# Windows PowerShell: $env:OPENAI_API_KEY="YOUR_KEY"
```

### (3) 실행
```bash
python -m streamlit run app.py
```

---

## 2) CSV 포맷

필수 컬럼(예시):

- `url` : 콘텐츠/페이지 URL
- `visits` : 방문수(views/pageviews/sessions 등)
- `avg_dwell_sec` : 평균 체류시간(초). `mm:ss`, `hh:mm:ss` 도 인식.

선택 컬럼:

- `title`
- `content` : 페이지 본문 텍스트(또는 text/body/본문). 있으면 URL 크롤링 없이 이 텍스트로 요약합니다.

샘플:
- `sample_data/metrics_sample.csv` (URL 기반)
- `sample_data/metrics_sample_with_content.csv` (content 컬럼 포함 - 데모 안정성 추천)

---

## 3) OpenAI API 사용 포인트(요건 충족)

- **Responses API**: 요약(Structured Outputs JSON Schema) + 새 콘텐츠 생성  
- **Embeddings API**: 요약 기반 토픽 클러스터링 (선택)  
- (선택) **web_search tool**: 외부 트렌드 참고

공식 문서 예시:
- Responses API quickstart: `client.responses.create(...)`
- Structured outputs: `text={"format": {"type": "json_schema", ...}}`
- Embeddings: `client.embeddings.create(model="text-embedding-3-small", input="...")`

---

## 4) 데모 시나리오(영상 촬영용)

1. **CSV 업로드** → 상위 Top N 콘텐츠 자동 랭킹
2. 버튼 클릭: **URL 본문 가져오기(또는 content 컬럼 사용) + AI 요약 생성**
3. **클러스터(트렌드 묶음)** 확인
4. 페르소나/포맷 선택 후 **새 콘텐츠 생성**
5. 결과를 **Markdown으로 다운로드** → 복사해서 발행/편집 가능

---

## 5) 확장 아이디어(본선/비즈니스 가치)

- GA4 / Amplitude / Mixpanel / Firebase Analytics 연동 (CSV 업로드 없이 자동 수집)
- Notion / Slack / Jira / Confluence 자동 발행
- A/B 테스트 카피 여러 버전 생성 + 성과(CTR/체류시간) 피드백 루프
- 기업별 톤앤매너(Brand voice) 학습(가이드/샘플 기반 RAG)
