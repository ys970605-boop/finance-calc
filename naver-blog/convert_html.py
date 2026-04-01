#!/usr/bin/env python3
"""HTML 태그 포함 네이버 블로그 txt 파일을 플레인 텍스트로 변환"""

import os
import re
import json

BLOG_DIR = "/Users/yongseok/cursor/finance-calc/naver-blog"
POSTED_JSON = os.path.join(BLOG_DIR, "posted.json")


def has_html(text):
    return bool(re.search(r'<[a-zA-Z/][^>]*>', text))


def convert_html_to_plain(text):
    # <h2>텍스트</h2> → ▶ 텍스트
    text = re.sub(r'<h2[^>]*>(.*?)</h2>', lambda m: '▶ ' + m.group(1).strip(), text, flags=re.DOTALL)
    # <h3>텍스트</h3> → ▷ 텍스트
    text = re.sub(r'<h3[^>]*>(.*?)</h3>', lambda m: '▷ ' + m.group(1).strip(), text, flags=re.DOTALL)
    # <li>텍스트</li> → - 텍스트
    text = re.sub(r'<li[^>]*>(.*?)</li>', lambda m: '- ' + m.group(1).strip(), text, flags=re.DOTALL)
    # <a href="URL">텍스트</a> → 텍스트 (URL)
    text = re.sub(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                  lambda m: f'{m.group(2).strip()} ({m.group(1).strip()})', text, flags=re.DOTALL)
    # <br>, <br/>, <br /> → 빈 줄
    text = re.sub(r'<br\s*/?>', '\n', text)
    # <p>텍스트</p> → 텍스트\n
    text = re.sub(r'<p[^>]*>(.*?)</p>', lambda m: m.group(1).strip() + '\n', text, flags=re.DOTALL)
    # <strong>, <b>, <em>, <i> 등 인라인 태그 제거
    text = re.sub(r'<(strong|b|em|i|span|u)[^>]*>(.*?)</\1>', lambda m: m.group(2), text, flags=re.DOTALL)
    # <ul>, <ol>, <div>, <section> 등 블록 태그 제거
    text = re.sub(r'<(ul|ol|div|section|article|header|footer|nav|aside)[^>]*>', '', text)
    text = re.sub(r'</(ul|ol|div|section|article|header|footer|nav|aside)>', '', text)
    # 나머지 모든 태그 제거
    text = re.sub(r'<[^>]+>', '', text)
    # HTML 엔티티 디코딩
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>') \
               .replace('&nbsp;', ' ').replace('&quot;', '"').replace('&#39;', "'")
    # 3개 이상 연속 빈 줄 → 2개로 정리
    text = re.sub(r'\n{3,}', '\n\n', text)
    # 줄 앞뒤 공백 정리 (각 줄)
    lines = [line.rstrip() for line in text.splitlines()]
    text = '\n'.join(lines)
    return text.strip()


def main():
    with open(POSTED_JSON, 'r', encoding='utf-8') as f:
        posted = set(json.load(f))

    txt_files = [f for f in os.listdir(BLOG_DIR) if f.endswith('.txt')]
    unpublished = [f for f in txt_files if f not in posted]

    converted = []
    skipped = []

    for fname in sorted(unpublished):
        fpath = os.path.join(BLOG_DIR, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        if not has_html(content):
            skipped.append(fname)
            continue

        converted_content = convert_html_to_plain(content)
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(converted_content)
        converted.append(fname)
        print(f"[변환] {fname}")

    print(f"\n총 미발행 파일: {len(unpublished)}개")
    print(f"HTML 포함 → 변환: {len(converted)}개")
    print(f"이미 플레인텍스트 (스킵): {len(skipped)}개")

    if converted:
        print("\n변환된 파일:")
        for f in converted:
            print(f"  - {f}")


if __name__ == '__main__':
    main()
