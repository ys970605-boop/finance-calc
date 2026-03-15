#!/usr/bin/env python3
"""
Chrome Instagram 쿠키 추출 -> Playwright storage state JSON 변환
macOS 전용 (Keychain + SQLite AES-CBC 복호화)

사용법:
  python3 extract_instagram_cookies.py
  python3 extract_instagram_cookies.py --profile "Default"
  python3 extract_instagram_cookies.py --output my_session.json
  python3 extract_instagram_cookies.py --verify  # 추출 후 Playwright로 로그인 검증
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


# ─── Chrome 쿠키 DB 경로 ───────────────────────────────────────────────────────

CHROME_BASE = Path.home() / "Library/Application Support/Google/Chrome"

PROFILES = ["Default", "Profile 1", "Profile 2", "Profile 3", "Profile 4", "Profile 5"]


def find_cookie_db(profile: str = None) -> Path:
    """Chrome 쿠키 DB 파일 위치 반환. profile=None이면 자동 탐색."""
    candidates = [profile] if profile else PROFILES
    for p in candidates:
        path = CHROME_BASE / p / "Cookies"
        if path.exists():
            return path
    raise FileNotFoundError(f"Chrome Cookies DB를 찾을 수 없습니다. 경로: {CHROME_BASE}")


# ─── Keychain에서 Chrome Safe Storage 키 추출 ─────────────────────────────────

def get_chrome_safe_storage_key() -> bytes:
    """
    macOS Keychain에서 'Chrome Safe Storage' 비밀번호를 가져와
    PBKDF2-SHA1로 AES 키 유도 (16바이트).
    """
    result = subprocess.run(
        ["security", "find-generic-password", "-wa", "Chrome"],
        capture_output=True, text=True
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(
            "Keychain에서 Chrome Safe Storage 키를 가져올 수 없습니다.\n"
            "Chrome을 한 번 실행한 뒤 다시 시도하세요.\n"
            f"stderr: {result.stderr}"
        )

    raw_key = result.stdout.strip()

    # PBKDF2-SHA1: password=raw_key, salt='saltysalt', iterations=1003, dklen=16
    derived = hashlib.pbkdf2_hmac(
        "sha1",
        raw_key.encode("utf-8"),
        b"saltysalt",
        1003,
        dklen=16,
    )
    return derived


# ─── AES-128-CBC 복호화 ────────────────────────────────────────────────────────

def decrypt_cookie_value(encrypted: bytes, key: bytes) -> str:
    """
    Chrome v10 쿠키 복호화.
    형식: b'v10' + AES-128-CBC(key, IV=b' '*16, plaintext)
    복호화 후 앞 32바이트(Chrome 내부 prefix)를 제거.
    """
    if not encrypted:
        return ""

    enc = bytes(encrypted)

    if enc[:3] == b"v10":
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend

        data = enc[3:]
        iv = b" " * 16

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        raw = decryptor.update(data) + decryptor.finalize()

        # PKCS7 패딩 제거
        pad_len = raw[-1]
        if 1 <= pad_len <= 16:
            raw = raw[:-pad_len]

        # Chrome 내부 prefix 제거 (앞 32바이트 = 2 AES 블록)
        if len(raw) > 32:
            return raw[32:].decode("utf-8", errors="replace")
        else:
            # 짧은 값: printable ASCII 구간만 추출
            decoded = raw.decode("utf-8", errors="replace")
            match = re.search(r"[\x20-\x7e]+", decoded)
            return match.group() if match else decoded

    # 암호화 안 된 경우
    return enc.decode("utf-8", errors="ignore")


# ─── Chrome 시간 -> Unix timestamp 변환 ───────────────────────────────────────

def chrome_time_to_unix(chrome_time: int) -> float:
    """
    Chrome timestamp (microseconds since 1601-01-01) -> Unix epoch seconds.
    0 또는 음수면 -1 반환 (만료 없음).
    """
    if chrome_time <= 0:
        return -1
    # 1601-01-01 to 1970-01-01 = 11644473600 seconds
    return (chrome_time / 1_000_000) - 11_644_473_600


# ─── samesite 정수 -> 문자열 변환 ─────────────────────────────────────────────

SAMESITE_MAP = {-1: "None", 0: "None", 1: "Lax", 2: "Strict"}


def samesite_to_str(value: int) -> str:
    return SAMESITE_MAP.get(value, "None")


# ─── 메인: 쿠키 추출 및 변환 ──────────────────────────────────────────────────

def extract_instagram_cookies(
    profile: str = None,
    domains: list = None,
    output_path: str = "instagram_session.json",
) -> dict:
    """
    Chrome DB에서 Instagram 쿠키를 추출해 Playwright storage state 형식으로 반환.

    Args:
        profile: Chrome 프로필 폴더명 (예: "Default", "Profile 1")
        domains: 추출할 도메인 목록 (기본: instagram.com + threads)
        output_path: 저장할 JSON 파일 경로
    """
    if domains is None:
        domains = ["%instagram.com%", "%threads.net%", "%threads.com%"]

    # 1. Chrome Cookies DB 복사 (잠금 회피)
    cookie_db_path = find_cookie_db(profile)
    print(f"[+] 쿠키 DB: {cookie_db_path}")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name
    shutil.copy2(cookie_db_path, tmp_path)

    # 2. AES 키 유도
    print("[+] Keychain에서 Chrome Safe Storage 키 추출 중...")
    aes_key = get_chrome_safe_storage_key()
    print(f"[+] AES-128 키 유도 완료: {aes_key.hex()}")

    # 3. SQLite 쿼리
    conn = sqlite3.connect(tmp_path)
    cur = conn.cursor()

    placeholders = " OR ".join([f"host_key LIKE ?" for _ in domains])
    query = f"""
        SELECT name, value, encrypted_value, host_key, path,
               expires_utc, is_secure, is_httponly, samesite
        FROM cookies
        WHERE {placeholders}
        ORDER BY host_key, name
    """
    cur.execute(query, domains)
    rows = cur.fetchall()
    conn.close()
    os.unlink(tmp_path)

    print(f"[+] 총 {len(rows)}개 쿠키 발견")

    # 4. 복호화 및 변환
    playwright_cookies = []
    for name, value, enc_value, host, path, expires_utc, secure, httponly, samesite in rows:
        # 값 복호화
        if enc_value and bytes(enc_value)[:3] == b"v10":
            cookie_value = decrypt_cookie_value(enc_value, aes_key)
        else:
            cookie_value = value or ""

        # 도메인 정규화 (.instagram.com -> .instagram.com)
        domain = host if host.startswith(".") else f".{host}"

        playwright_cookies.append({
            "name": name,
            "value": cookie_value,
            "domain": domain,
            "path": path or "/",
            "expires": chrome_time_to_unix(expires_utc),
            "httpOnly": bool(httponly),
            "secure": bool(secure),
            "sameSite": samesite_to_str(samesite),
        })

    # 5. Playwright storage state 형식
    storage_state = {
        "cookies": playwright_cookies,
        "origins": [],
    }

    # 6. JSON 저장
    output_path = os.path.expanduser(output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(storage_state, f, ensure_ascii=False, indent=2)

    print(f"\n[+] 저장 완료: {output_path}")
    print(f"[+] 쿠키 수: {len(playwright_cookies)}")

    # 주요 쿠키 출력
    print("\n[주요 쿠키]")
    important = ["sessionid", "csrftoken", "ds_user_id", "ig_did", "mid", "datr"]
    for cookie in playwright_cookies:
        if cookie["name"] in important:
            val_preview = cookie["value"][:40] + "..." if len(cookie["value"]) > 40 else cookie["value"]
            print(f"  {cookie['domain']:25s} | {cookie['name']:15s} = {val_preview}")

    return storage_state


# ─── Playwright 검증 (선택) ────────────────────────────────────────────────────

def verify_with_playwright(session_file: str):
    """추출된 세션으로 Instagram 로그인 상태 검증."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("\n[!] playwright 미설치. 검증 건너뜀.")
        print("    설치: pip install playwright && playwright install chromium")
        return

    print("\n[+] Playwright로 Instagram 로그인 상태 검증 중...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(storage_state=session_file)
        page = ctx.new_page()
        page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # 로그인 여부 확인
        if page.url.startswith("https://www.instagram.com/") and "accounts/login" not in page.url:
            print(f"[+] 로그인 성공! URL: {page.url}")
        else:
            print(f"[-] 로그인 실패. URL: {page.url}")

        page.screenshot(path="/tmp/instagram_verify.png")
        print("[+] 스크린샷: /tmp/instagram_verify.png")
        browser.close()


# ─── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Chrome Instagram 쿠키 -> Playwright session JSON 변환"
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Chrome 프로필 폴더명 (예: Default, 'Profile 1'). 미지정 시 자동 탐색.",
    )
    parser.add_argument(
        "--output",
        default="instagram_session.json",
        help="출력 JSON 파일 경로 (기본: instagram_session.json)",
    )
    parser.add_argument(
        "--domains",
        nargs="+",
        default=None,
        help="추출할 도메인 LIKE 패턴 (기본: %%instagram.com%% %%threads.net%% %%threads.com%%)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="추출 후 Playwright로 Instagram 로그인 검증",
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="사용 가능한 Chrome 프로필 목록 출력",
    )
    args = parser.parse_args()

    if args.list_profiles:
        print("사용 가능한 Chrome 프로필:")
        for p in PROFILES:
            path = CHROME_BASE / p / "Cookies"
            if path.exists():
                print(f"  {p}: {path}")
        return

    try:
        storage_state = extract_instagram_cookies(
            profile=args.profile,
            domains=args.domains,
            output_path=args.output,
        )
        if args.verify:
            verify_with_playwright(args.output)
    except FileNotFoundError as e:
        print(f"[오류] {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"[오류] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
