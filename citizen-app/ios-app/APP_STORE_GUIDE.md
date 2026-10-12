# 창원 안심길 iOS 앱스토어 제출 가이드

웹앱(`citizen-app/frontend`, Render 배포)을 Capacitor로 감싼 iOS 앱을 Mac 없이 Codemagic 클라우드에서 빌드해 App Store Connect에 올립니다.

## 구성 요약

| 파일 | 역할 |
|---|---|
| `capacitor.config.json` | 앱 ID `com.ooez.changwonansimgil`, 앱 이름, 웹앱 주소(`server.url`), 시작 화면 설정 |
| `www/index.html`, `www/error.html` | 앱에 내장된 로딩 화면. 서버가 잠들어 있으면 깨어날 때까지 기다렸다가 웹앱으로 넘어감 |
| `resources/icon-1024.png` | 앱 아이콘(1024×1024, 투명도 없음) |
| `resources/splash-2732x2732.png` | 시작 화면 이미지(“창원시의 안전한 보행경로를 위해 지도를 불러오고 있습니다”) |
| `scripts/configure-ios.sh` | 위치·카메라 권한 문구, 세로 고정, iPhone 전용, 아이콘·시작 화면 적용 |
| `scripts/make_assets.py` | 아이콘·시작 화면 이미지를 다시 만들 때 사용(Windows, `python scripts/make_assets.py`) |
| `/codemagic.yaml` (저장소 루트) | 클라우드 빌드 → TestFlight 업로드 |

번들 ID를 바꾸려면 `capacitor.config.json`의 `appId`와 `codemagic.yaml`의 `bundle_identifier`를 같이 바꾸세요.

## 1. Apple Developer에서 번들 ID 등록

1. https://developer.apple.com/account → Certificates, IDs & Profiles → Identifiers → `+`
2. App IDs → App → Description `Changwon Ansimgil`, Bundle ID **Explicit** `com.ooez.changwonansimgil`
3. Capabilities는 추가로 켤 것 없음 → Register

## 2. App Store Connect에 앱 만들기

https://appstoreconnect.apple.com → 앱 → `+` → 신규 앱

| 항목 | 값 |
|---|---|
| 플랫폼 | iOS |
| 이름 | 창원 안심길 |
| 기본 언어 | 한국어 |
| 번들 ID | com.ooez.changwonansimgil |
| SKU | ansimgil-ios-001 |
| 사용자 액세스 | 전체 액세스 |

## 3. App Store Connect API 키 만들기 (Codemagic 연결용)

1. App Store Connect → 사용자 및 액세스 → 통합 → App Store Connect API → 팀 키 `+`
2. 이름 `Codemagic`, 액세스 **App Manager** → 생성
3. **Issuer ID**, **키 ID**를 메모하고 `.p8` 파일을 내려받기(한 번만 받을 수 있음, 저장소에 절대 올리지 말 것)

## 4. Codemagic 설정 (최초 1회)

1. https://codemagic.io 에서 GitHub 계정으로 가입 → Add application → `changwon-safety` 저장소 선택 → 프로젝트 유형 **Other**(codemagic.yaml 사용)
2. Team settings → Integrations → **Developer Portal** → Connect
   - Name: **`ansimgil_asc`** (codemagic.yaml과 같아야 함), Issuer ID, Key ID, `.p8` 업로드
3. Team settings → Code signing identities
   - iOS certificates → **Generate certificate** → 유형 Apple Distribution → 이름 지정 → 생성
   - iOS provisioning profiles → **Fetch profiles** (없으면 빌드 때 자동 생성됨)
4. 앱 화면에서 **Start new build** → 워크플로 `ios-appstore` 선택 → 시작
   - 15~25분 뒤 빌드가 끝나면 App Store Connect의 TestFlight 탭에 업로드됨(처리에 10~30분 추가)
   - 무료 플랜은 월 500분이라 1회 빌드 약 20분 기준 20회 이상 가능

> 빌드 번호는 Codemagic 빌드 횟수로 자동 증가합니다. 앱 버전을 올릴 때는 `codemagic.yaml`의 `agvtool new-marketing-version 1.0.0`을 바꾸세요.

## 5. TestFlight로 실기기 확인

1. App Store Connect → TestFlight → 내부 테스트 그룹에 팀원 Apple ID 추가
2. iPhone에 TestFlight 앱 설치 → 초대 수락 → 설치
3. 확인할 것
   - 시작 화면 → 위치 권한 팝업(한국어 문구) → 홈 지도 표시
   - 안심경로 3가지 옵션, 위험신고 사진 첨부(카메라·앨범 권한 문구), 112·119 버튼
   - 저장 탭 맨 아래 개인정보처리방침·고객지원 링크
   - 창원 밖에서 “🗺️ 창원 둘러보기” 버튼 표시 여부

## 6. 스크린샷

- 필수: **6.9형 iPhone**(1320×2868 또는 1290×2796). 없으면 6.5형(1284×2778 또는 1242×2688)
- 3~5장 권장: ① 홈 지도(주변 안전시설) ② 안심경로 3가지 비교 ③ 경로 안내 화면 ④ 위험신고 ⑤ 온보딩(연령대 선택)
- 가장 쉬운 방법: Pro Max 모델 iPhone에서 TestFlight 앱으로 캡처(전원+볼륨 업). 크기가 그대로 맞음

## 7. 앱 정보 입력 (App Store 탭)

**이름**: 창원 안심길
**부제**(30자): 안전시설 데이터로 찾는 보행 경로
**카테고리**: 기본 내비게이션 / 보조 유틸리티
**가격**: 무료 · **배포 국가**: 대한민국
**저작권**: 2026 창원 안심길 개발팀
**지원 URL**: https://changwon-ansimgil.onrender.com/support.html
**개인정보처리방침 URL**: https://changwon-ansimgil.onrender.com/privacy.html

**프로모션 텍스트**(170자)
```
창원시 CCTV·보안등·공공 Wi-Fi 공공데이터를 참고해 안전시설이 많은 길을 추천해 드려요. 어린이·고령자 생활권 분석을 반영한 맞춤 경로를 확인해 보세요.
```

**설명**
```
창원 안심길은 창원시의 공공데이터를 활용해, 걸어서 이동할 때 안전시설이 많은 길을 함께 보여주는 보행 경로 서비스입니다.
※ 창원 안심길은 창원시 공식 앱이 아니며, 공공데이터를 활용해 만든 서비스입니다.

■ 주요 기능
· 내 주변 안전시설: 현재 위치 주변의 CCTV·보안등·공공 Wi-Fi가 모두 가까운 지점과 추천 시설을 지도에 표시합니다.
· 3가지 추천 경로: 최단 / 균형 / 안심 우선 경로를 비교하고, 안전시설 데이터를 참고한 경로를 선택할 수 있습니다.
· 연령대 맞춤: 어린이·청소년, 성인, 고령자 중 선택하면 어린이집·경로당 생활권 분석 결과를 반영합니다.
· 위험신고: 어두운 골목, 고장 난 가로등 같은 위험 지점을 사진과 함께 운영팀에 알릴 수 있습니다.
· 자주 가는 곳 저장, 내 위치 공유

■ 활용 데이터
경찰청 생활안전지도, 공공데이터포털의 CCTV·보안등·공공 Wi-Fi·어린이집·경로당 위치 데이터를 100m 격자 단위로 분석했습니다.

■ 꼭 알아두세요
· 추천 경로는 안전시설 데이터를 참고한 것으로 실제 안전을 보장하지 않습니다.
· 긴급 상황에서는 바로 112(경찰)·119(소방)에 신고하세요. 앱의 위험신고는 긴급 신고가 아닙니다.
· 안전시설 데이터는 창원시 지역만 제공합니다.
```

**키워드**(100자)
```
창원,안심귀가,보행,길찾기,경로,CCTV,보안등,가로등,안전,어린이,노인,마산,진해,의창,성산
```

## 8. 앱 개인정보 보호(데이터 수집 라벨)

“데이터를 수집합니까?” → **예**. 아래 항목만 선택하고 모두 **앱 기능** 용도, **사용자와 연결되지 않음**, **추적에 사용하지 않음**.

| 데이터 유형 | 이유 |
|---|---|
| 위치 > 정밀한 위치 | 위험신고 접수 시 신고 위치가 저장됨(경로 계산 시 전송되는 위치는 저장하지 않음) |
| 사용자 콘텐츠 > 사진 또는 비디오 | 위험신고 첨부 사진 |
| 사용자 콘텐츠 > 기타 사용자 콘텐츠 | 위험신고 상황 설명 |
| 기타 데이터 > 기타 데이터 유형 | 위험신고와 함께 저장되는 연령대 |

성별·자주 가는 곳은 기기에만 저장되므로 수집에 해당하지 않습니다.

## 9. 연령 등급

모든 질문 **없음** → 4+. (사용자 간 콘텐츠 공유·채팅 없음, 신고 내용은 다른 사용자에게 보이지 않음)

## 10. 앱 심사 정보

- 로그인 필요: **아니요**
- 연락처: 대표자 이름, 전화번호, 이메일 입력
- **메모**(영어로 작성 권장)

```
Thank you for reviewing Changwon Ansimgil.

- This is NOT an official app of Changwon City. It is built by a student team using public data (Korean National Police Agency Safety Map and Public Data Portal) for Changwon, South Korea.
- No login is required.
- Location data is used only to show nearby safety facilities (CCTV, street lights, public Wi-Fi) and to calculate walking routes. Location history is not stored.
- Testing outside Changwon: the safety data covers Changwon only. When your location is outside Changwon (or location is unavailable), a "🗺️ 창원 둘러보기 (Explore Changwon)" button appears at the top of the home screen. Tap it to move to a sample location inside Changwon and try all features (home map, 3 route options, hazard report).
- First launch may take 1-2 minutes while our server wakes up. A loading screen is shown during this time.
- The "위험신고 (Hazard Report)" tab sends reports to our operating team for facility improvement. It is NOT an emergency service; the tab shows 112 (police) and 119 (fire) call buttons and tells users to call them in emergencies.
```

## 11. 수출 규정

`ITSAppUsesNonExemptEncryption = false`가 이미 들어가 있어 제출 시 암호화 질문이 생략됩니다(HTTPS만 사용).

## 12. 반려 대응 메모

- **4.2 최소 기능(웹사이트를 감싼 앱)**: 위치 기반 지도, 3가지 경로 계산, 사진 첨부 신고, 기기 저장 기능이 있는 독립 서비스임을 답변. 네이티브 위치 권한·시작 화면·오프라인 로딩 화면을 사용함을 설명
- **2.1 앱 완성도(로딩 실패)**: 심사 기간에는 Render 서버가 잠들지 않도록 제출 직전에 앱을 한 번 열어 깨워 두기
- **5.1.1 개인정보**: 개인정보처리방침이 앱 안(저장 탭 맨 아래)과 App Store Connect 모두에 연결되어 있는지 확인
- **5.2 지적재산권/공식 오인**: 창원시 로고·상표 사용 안 함, 설명 첫 줄과 앱 안에 “공식 앱 아님” 고지
