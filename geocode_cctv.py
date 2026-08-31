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

def get_api_key():
    """환경변수를 우선 사용하고, 없으면 터미널에서 키를 직접 받습니다."""
    raw_key = os.environ.get("KAKAO_REST_API_KEY", "").strip()

    if not re.fullmatch(r"[0-9a-fA-F]{32}", raw_key):
        print("카카오 REST API 키를 붙여넣고 Enter를 누르세요.")
        print("입력하는 동안 키는 화면에 표시되지 않습니다.")
        raw_key = getpass("REST API 키: ").strip()

    # 복사 과정에서 앞뒤 설명이 붙어도 32자리 키 부분만 사용합니다.
    match = re.search(r"[0-9a-fA-F]{32}", raw_key)
    if not match:
        raise ValueError(
            "입력값에서 32자리 REST API 키를 찾지 못했습니다. "
            "[앱 > 플랫폼 키 > REST API 키]의 복사 버튼을 사용하세요."
        )

    return match.group(0)


API_KEY = get_api_key()


class KakaoAPIError(RuntimeError):
    """주소 문제가 아닌 카카오 API 호출 자체의 오류입니다."""


def extract_camera_number(address):
    """주소 끝의 _1, _2 등에서 카메라 번호를 추출합니다."""
    match = re.search(r"_(\d+)\s*$", str(address))
    return match.group(1) if match else ""


def clean_address(address):
    """원본은 보존하고 카카오 주소검색에 사용할 주소만 정리합니다."""
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
    """카카오 API로 주소를 위도·경도로 변환합니다."""
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {API_KEY}"}

    try:
        response = session.get(
            url,
            headers=headers,
            params={"query": address},
            timeout=15,
        )
    except requests.RequestException as error:
        raise KakaoAPIError(f"네트워크 오류: {error}") from error

    if response.status_code != 200:
        detail = response.text.strip() or "응답 본문 없음"
        raise KakaoAPIError(
            f"카카오 API HTTP {response.status_code}: {detail}"
        )

    documents = response.json().get("documents", [])
    if not documents:
        return None, None

    # 카카오 응답은 x=경도, y=위도입니다.
    longitude = float(documents[0]["x"])
    latitude = float(documents[0]["y"])
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
    except KakaoAPIError as error:
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
