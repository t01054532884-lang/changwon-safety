#!/usr/bin/env bash
# `npx cap add ios` / `npx cap sync ios`로 만든 Xcode 프로젝트에 앱스토어 제출용 설정을 입힌다.
# Codemagic(맥 빌드 서버)에서 실행된다. 로컬 맥에서도 citizen-app/ios-app 폴더에서 그대로 실행 가능.
set -euo pipefail
cd "$(dirname "$0")/.."

PLIST="ios/App/App/Info.plist"
PB=/usr/libexec/PlistBuddy

set_plist() {  # key type value
  $PB -c "Delete :$1" "$PLIST" 2>/dev/null || true
  $PB -c "Add :$1 $2 $3" "$PLIST"
}

LOCATION_TEXT="내 주변 안전시설을 보여주고, 현재 위치에서 출발하는 추천 보행 경로를 계산하며, 위험신고 위치를 확인하는 데 사용합니다. 위치 기록은 저장하지 않습니다."
set_plist NSLocationWhenInUseUsageDescription string "$LOCATION_TEXT"
set_plist NSLocationAlwaysAndWhenInUseUsageDescription string "$LOCATION_TEXT"
set_plist NSCameraUsageDescription string "위험신고에 현장 사진을 첨부할 때 사용합니다."
set_plist NSPhotoLibraryUsageDescription string "위험신고에 앨범의 사진을 첨부할 때 사용합니다."
set_plist ITSAppUsesNonExemptEncryption bool false
set_plist CFBundleDevelopmentRegion string ko
set_plist CFBundleDisplayName string "창원 안심길"

# 세로 화면만 지원
$PB -c "Delete :UISupportedInterfaceOrientations" "$PLIST" 2>/dev/null || true
$PB -c "Add :UISupportedInterfaceOrientations array" "$PLIST"
$PB -c "Add :UISupportedInterfaceOrientations:0 string UIInterfaceOrientationPortrait" "$PLIST"
$PB -c "Delete :UISupportedInterfaceOrientations~ipad" "$PLIST" 2>/dev/null || true

# iPhone 전용(iPad 스크린샷·심사 대상에서 제외)
sed -i '' 's/TARGETED_DEVICE_FAMILY = "1,2";/TARGETED_DEVICE_FAMILY = 1;/g' ios/App/App.xcodeproj/project.pbxproj

# 앱 아이콘(1024, 알파 없음)과 시작 화면 이미지 교체
ICONSET="ios/App/App/Assets.xcassets/AppIcon.appiconset"
for f in "$ICONSET"/*.png; do cp resources/icon-1024.png "$f"; done
SPLASH="ios/App/App/Assets.xcassets/Splash.imageset"
for f in "$SPLASH"/*.png; do cp resources/splash-2732x2732.png "$f"; done

echo "iOS 프로젝트 설정 완료"
$PB -c "Print" "$PLIST" | head -60
