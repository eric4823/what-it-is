# RUNNER LAB — 모바일 급등주 연구 스캐너

GitHub Pages 정적 웹사이트 + GitHub Actions 일봉 수집/계산. **실전 매수 신호가 아님.** 머신러닝으로 검증된 적중률은 **없음**.

## 휴대폰 화면
- 저장소가 GitHub Pages(Deploy from a branch, `master`, `/(root)`)를 이미 사용하는 경우: https://eric4823.github.io/what-it-is/runner-scanner/
- Pages가 꺼져 있다면 GitHub 저장소 → **Settings → Pages → Build and deployment** → **Deploy from a branch** / **master** / **/(root)** → **Save**. 배포가 완료된 후 링크 방문.
- 별도 HTML 파일을 열어도 화면 레이아웃은 표시되지만, 공개 GitHub의 `data/latest.json`을 읽어야 최신 결과가 나옵니다.

## 실제 시세 연결
1. Massive(구 Polygon)의 미국 **Grouped Daily Aggregates**와 **Ticker Reference**에 접근 가능한 본인 API 키 확보.
2. GitHub 저장소 → **Settings → Secrets and variables → Actions → New repository secret**.
3. 이름: `MASSIVE_API_KEY` (값은 본인 키). 코딩 파일이나 공개 HTML에 적지 마세요.
4. **Actions → Update Runner Lab EOD Feed → Run workflow** 로 수동 실행. 이후 미국 정규장 이후 자동 업데이트(UTC Tue-Sat 01:15).
5. Actions 로그에서 `feed research_only` 여부 확인. `error`면 API 권한 / 유효한 종목 수 / 이용량 확인.
6. 화면 새로고침. `research_only`라면 지표 점수순 연구 후보가 표시됩니다.

## 실제 기능 / 한계
- 현재 활성 일반 보통주(type=CS) 기준으로 ETF/워런트 등 배제 시도; 데이터 공급원에 따라 예외 검증 필요.
- Grouped Daily Aggregates에서 최종 완료된 일봉을 최대 115평일(시장 휴장일 제외 85거래일 이상) 수집.
- 85일 이상 데이터 있는 보통주에서 CMF(5/20), 5일 중앙값 RVOL, 종가 위치, 거래대금, 과거 급등 이력, 20일 고가 돌파 등을 **휴리스틱 점수**로 결합.
- API 키 미설정·실패·커버리지 부족이면 자동으로 **매수 후보를 표시하지 않습니다**.
- 실제 수익률이나 익일 +50% 상승 확률이 검증된 모델이 아니며, 스코어 8점은 성공률 80%를 뜻하지 않습니다.
- 과거 상장폐지 종목, IPO/분할, 현재 보통주 분류 스냅샷 등 때문에 **생존편향 없는 역사적 적중률을 이 피드만으로 계산할 수 없습니다.**
- **15:45 매수 판단 불가**: 일봉은 장이 끝나야 확정됩니다. 15:45 스캐너는 라이선스가 포함된 당일 분봉/체결/호가와 그 시각 기준 별도 모델·실행 검증이 필요합니다.
- 급등/작전주 여부는 불법 시세조종의 확정 판정이 아닙니다.
- 공개 Pages에 데이터가 공개됩니다. 시세 재배포에 관한 제공업체 계약을 먼저 확인하세요.

## 저장소 구성
- `runner-scanner/index.html`: 모바일 반응형 HTML + JS; 외부 프레임워크 없음
- `runner-scanner/data/latest.json`: 업데이트 결과, 초기 상태는 `unconfigured`
- `runner-scanner/build_feed.py`: 데이터 수집 및 점수 계산
- `.github/workflows/runner-scanner.yml`: Actions 정기 실행

이 저장소의 다른 기존 파일은 수정하지 않았습니다.
