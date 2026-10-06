import json
import os
import re
import time
from getpass import getpass
from pathlib import Path

import pandas as pd
import requests


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
INPUT_FILE = DATA_DIR / "CCTV카메라(방범용)1.xlsx"
OUTPUT_FILE = DATA_DIR / "cctv_coordinates.csv"
CACHE_FILE = DATA_DIR / "geocoding_cache.json"

def get_api_credentials():
    """NAVER Cloud Maps 키를 환경변수에서 읽고, 없으면 터미널에서 직접 받습니다.

    관리자 앱(admin/app.py)의 주소검색과 같은 NAVER_MAP_CLIENT_ID /
    NAVER_MAP_CLIENT_SECRET 키를 그대로 사용합니다.
    """
    client_id = os.environ.get("NAVER_MAP_CLIENT_ID", "").strip()
    client_secret = os.environ.get("NAVER_MAP_CLIENT_SECRET", "").strip()

    if not client_id or not client_secret:
        print("NAVER Cloud Maps 인증 정보를 붙여넣고 Enter를 누르세요.")
        print("입력하는 동안 값은 화면에 표시되지 않습니다.")
        client_id = client_id or getpass("Client ID (ncpKeyId): ").strip()
        client_secret = client_secret or getpass("Client Secret: ").strip()

    if not client_id or not client_secret:
        raise ValueError(
            "NAVER Cloud Maps Client ID와 Client Secret이 모두 필요합니다. "
            "[NAVER Cloud Console > Maps > Application]에서 확인하세요."
        )

    return client_id, client_secret


CLIENT_ID, CLIENT_SECRET = get_api_credentials()


class GeocodingAPIError(RuntimeError):
    """주소 문제가 아닌 NAVER Geocoding API 호출 자체의 오류입니다."""


def extract_camera_number(address):
    """주소 끝의 _1, _2 등에서 카메라 번호를 추출합니다."""
    match = re.search(r"_(\d+)\s*$", str(address))
    return match.group(1) if match else ""


def clean_address(address):
    """원본은 보존하고 주소검색에 사용할 주소만 정리합니다."""
    address = str(address).strip()
    address = re.sub(r"_\d+\s*$", "", address)
    address = re.sub(r"\([^)]*\)", "", address)
    address = re.sub(r"\s+", " ", address)
    return address.strip().rstrip(",").strip()


def load_cache():
    if not CACHE_FILE.exists():
        return {}

    try:
        with CACHE_FILE.open("r", encoding="utf-8") as cache_file:
            return json.load(cache_file)
    except (json.JSONDecodeError, OSError):
        print("기존 좌표 캐시를 읽지 못해 새로 시작합니다.")
        return {}


def save_cache(cache):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with CACHE_FILE.open("w", encoding="utf-8") as cache_file:
        json.dump(cache, cache_file, ensure_ascii=False, indent=2)


def search_address(session, address):
    """NAVER Cloud Maps Geocoding API로 주소를 위도·경도로 변환합니다."""
    url = "https://maps.apigw.ntruss.com/map-geocode/v2/geocode"
    headers = {
        "x-ncp-apigw-api-key-id": CLIENT_ID,
        "x-ncp-apigw-api-key": CLIENT_SECRET,
        "Accept": "application/json",
    }

    try:
        response = session.get(
            url,
            headers=headers,
            params={"query": address, "count": 1},
            timeout=15,
        )
    except requests.RequestException as error:
        raise GeocodingAPIError(f"네트워크 오류: {error}") from error

    if response.status_code != 200:
        detail = response.text.strip() or "응답 본문 없음"
        raise GeocodingAPIError(
            f"NAVER Geocoding API HTTP {response.status_code}: {detail}"
        )

    addresses = response.json().get("addresses", [])
    if not addresses:
        return None, None

    # NAVER 응답은 x=경도, y=위도입니다.
    longitude = float(addresses[0]["x"])
    latitude = float(addresses[0]["y"])
    return latitude, longitude


if not INPUT_FILE.exists():
    raise FileNotFoundError(f"엑셀 파일을 찾을 수 없습니다: {INPUT_FILE}")

dataframe = pd.read_excel(INPUT_FILE)

if "설치장소" not in dataframe.columns:
    raise ValueError("엑셀 파일에서 '설치장소' 열을 찾을 수 없습니다.")

dataframe["카메라번호"] = dataframe["설치장소"].apply(
    extract_camera_number
)
dataframe["검색용주소"] = dataframe["설치장소"].apply(clean_address)

unique_addresses = dataframe["검색용주소"].dropna().unique()
cache = load_cache()
coordinate_map = {}
session = requests.Session()

print(f"전체 CCTV 행: {len(dataframe)}개")
print(f"중복 제거 검색 주소: {len(unique_addresses)}개")
print(f"기존 변환 캐시: {len(cache)}개")

for index, address in enumerate(unique_addresses, start=1):
    if address in cache:
        latitude = cache[address].get("latitude")
        longitude = cache[address].get("longitude")
        coordinate_map[address] = (latitude, longitude)
        print(f"[{index}/{len(unique_addresses)}] 캐시 사용: {address}")
        continue

    try:
        latitude, longitude = search_address(session, address)
    except GeocodingAPIError as error:
        save_cache(cache)
        print()
        print(f"API 호출 중단: {address}")
        print(error)
        print("성공한 좌표는 geocoding_cache.json에 보관했습니다.")
        raise SystemExit(1) from error

    coordinate_map[address] = (latitude, longitude)
    cache[address] = {
        "latitude": latitude,
        "longitude": longitude,
    }
    save_cache(cache)

    result = "성공" if latitude is not None else "검색 결과 없음"
    print(f"[{index}/{len(unique_addresses)}] {result}: {address}")
    time.sleep(1.0)

dataframe["latitude"] = dataframe["검색용주소"].map(
    lambda address: coordinate_map.get(address, (None, None))[0]
)
dataframe["longitude"] = dataframe["검색용주소"].map(
    lambda address: coordinate_map.get(address, (None, None))[1]
)
dataframe["좌표변환상태"] = dataframe["latitude"].apply(
    lambda value: "성공" if pd.notna(value) else "확인 필요"
)

dataframe.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

success_count = dataframe["latitude"].notna().sum()
failure_count = dataframe["latitude"].isna().sum()

print()
print("좌표 변환 완료")
print(f"성공: {success_count}개")
print(f"확인 필요: {failure_count}개")
print(f"저장 파일: {OUTPUT_FILE}")
