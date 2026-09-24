"""위험신고 저장소 (Stage 4).

SQLite 파일 기반 저장소. 시민 앱의 신고 제출(POST /api/reports)과 관리자 웹의 조회/상태
변경(GET·PATCH /api/reports) 양쪽에서 이 모듈을 공유한다.

⚠️ 알려진 한계(중요): Render 무료 플랜의 로컬 디스크는 코드를 다시 "배포"할 때마다 완전히
새 컨테이너로 교체된다(서버가 잠들었다 깨어나는 것과는 다름 — 그건 디스크가 그대로 유지됨).
즉 이 SQLite 파일도 다음 배포 전까지만 보존되고, 배포할 때마다 신고 데이터가 초기화된다.
지금 단계의 목표는 "실제로 저장되고, 관리자 웹에서 조회·상태변경까지 되는" 구조 자체를
완성하는 것이고, 배포 사이에도 데이터를 남기려면 이후 Render 유료 Disk나 외부
DB(예: Supabase Postgres 무료 티어)로 옮겨야 한다 — 그때는 이 파일의 함수들만 그 저장소를
쓰도록 바꾸면 되고, main.py나 프론트엔드/관리자 웹 쪽은 손댈 필요 없도록 인터페이스를
분리해뒀다.

⚠️ 인증 없음: 지금은 관리자 웹 전용이라고 가정하고 /api/reports 조회·수정에 별도 인증을
걸지 않았다. URL만 알면 누구나 신고 목록을 볼 수 있으니, 실제 운영 전에는 최소한 API 키
정도는 붙이는 걸 권장한다(Stage 7 이후 후보).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent / "reports.db"

REPORT_TYPE_LABELS = {
    "dark_alley": "어둡고 인적 드문 골목",
    "broken_facility": "파손된 시설(가로등·CCTV 등)",
    "suspicious_person": "불안한 사람·행동",
    "traffic": "교통·보행 위험",
    "etc": "기타 위험 상황",
}

STATUS_VALUES = ["접수됨", "확인중", "처리완료", "반려"]

# base64 데이터 URL 문자열 길이 기준 대략적 상한(SQLite 파일이 과도하게 커지는 것 방지).
# base64는 원본보다 ~33% 커지므로 이 값은 원본 이미지 기준 약 3~4MB 정도에 해당.
MAX_IMAGE_DATA_URL_LEN = 5_000_000


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                report_type TEXT NOT NULL,
                description TEXT,
                lat REAL,
                lng REAL,
                age_group TEXT,
                image_data TEXT,
                status TEXT NOT NULL DEFAULT '접수됨',
                admin_note TEXT,
                updated_at TEXT
            )
            """
        )


def create_report(
    report_type: str,
    description: Optional[str],
    lat: Optional[float],
    lng: Optional[float],
    age_group: Optional[str],
    image_data_url: Optional[str],
) -> int:
    if report_type not in REPORT_TYPE_LABELS:
        raise ValueError(f"알 수 없는 신고 유형입니다: {report_type}")
    has_description = bool(description and description.strip())
    has_image = bool(image_data_url)
    if not has_description and not has_image:
        raise ValueError("사진 또는 상황 설명 중 최소 하나는 있어야 합니다.")
    if has_image and len(image_data_url) > MAX_IMAGE_DATA_URL_LEN:
        raise ValueError("첨부 이미지가 너무 커요. 더 작은 사진으로 다시 시도해주세요.")

    created_at = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO reports
                (created_at, report_type, description, lat, lng, age_group, image_data, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, '접수됨')
            """,
            (created_at, report_type, description, lat, lng, age_group, image_data_url),
        )
        return int(cursor.lastrowid)


def _row_to_dict(row: sqlite3.Row, include_image: bool) -> dict:
    d = dict(row)
    d["report_type_label"] = REPORT_TYPE_LABELS.get(d["report_type"], d["report_type"])
    image_data = d.pop("image_data", None)
    d["has_image"] = bool(image_data)
    if include_image:
        d["image_data_url"] = image_data
    return d


def list_reports(status: Optional[str] = None, include_image: bool = False) -> list[dict]:
    query = "SELECT * FROM reports"
    params: tuple = ()
    if status:
        query += " WHERE status = ?"
        params = (status,)
    query += " ORDER BY id DESC"
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_dict(row, include_image) for row in rows]


def get_report(report_id: int, include_image: bool = True) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    if row is None:
        return None
    return _row_to_dict(row, include_image)


def update_report_status(report_id: int, status: str, admin_note: Optional[str]) -> bool:
    if status not in STATUS_VALUES:
        raise ValueError(f"알 수 없는 상태값입니다: {status} (허용값: {STATUS_VALUES})")
    updated_at = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE reports SET status = ?, admin_note = ?, updated_at = ? WHERE id = ?",
            (status, admin_note, updated_at, report_id),
        )
        return cursor.rowcount > 0
