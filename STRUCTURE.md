# 프로젝트 구조

```text
changwon_safety/
├─ admin/       관리자 안전취약도 분석·최적 배치 웹
├─ citizen/     시민용 모바일 PWA
├─ data/        공통 원본 데이터
├─ analysis/    공통 격자·위험도·최적화 로직
├─ tests/       분석 로직 테스트
└─ app.py       기존 관리자 배포를 위한 호환 실행 파일
```

기존 관리자 Streamlit 배포는 루트 `app.py`를 계속 사용할 수 있다. 실제 관리자
소스는 `admin/app.py`에 있다. 시민 앱은 기존 모바일 웹의 Git 이력, Sites 배포
설정, 데이터베이스와 PWA 자산을 포함해 `citizen/`으로 이동했다.
