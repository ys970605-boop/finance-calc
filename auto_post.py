"""
Blogger 자동 포스팅 스크립트
launchd가 매일 오전 9시에 실행 → 2개 발행 후 종료
글 목록: /tmp/blog_posts.py
"""

import pickle
import json
import os
import sys
import random
from datetime import datetime
from googleapiclient.discovery import build

BLOG_ID = "2186833071250214932"
TOKEN_FILE = "/tmp/blogger_token.pickle"
POSTED_FILE = "/tmp/posted_titles.json"
POSTS_FILE = "/tmp/blog_posts.py"
POSTS_PER_DAY = 2

def load_posts():
    import importlib.util
    spec = importlib.util.spec_from_file_location("blog_posts", POSTS_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.POSTS

def post_articles():
    if not os.path.exists(TOKEN_FILE):
        print(f"[{datetime.now()}] 토큰 없음: {TOKEN_FILE}")
        sys.exit(1)

    with open(TOKEN_FILE, "rb") as f:
        creds = pickle.load(f)

    # 토큰 갱신
    from google.auth.transport.requests import Request
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    service = build("blogger", "v3", credentials=creds)
    posts = load_posts()

    posted = json.load(open(POSTED_FILE)) if os.path.exists(POSTED_FILE) else []
    remaining = [p for p in posts if p["title"] not in posted]

    if not remaining:
        print(f"[{datetime.now()}] 60개 글 모두 발행 완료. 순환 시작.")
        posted = []
        remaining = posts
        with open(POSTED_FILE, "w") as f:
            json.dump(posted, f)

    to_post = random.sample(remaining, min(POSTS_PER_DAY, len(remaining)))

    for post in to_post:
        try:
            result = service.posts().insert(
                blogId=BLOG_ID,
                body={"title": post["title"], "content": post["content"]},
                isDraft=False
            ).execute()

            posted.append(post["title"])
            with open(POSTED_FILE, "w") as f:
                json.dump(posted, f)

            print(f"[{datetime.now()}] 발행 완료: {result['title']}")
            print(f"  URL: {result['url']}")

        except Exception as e:
            print(f"[{datetime.now()}] 오류 - {post['title']}: {e}")

if __name__ == "__main__":
    print(f"[{datetime.now()}] 자동 포스팅 시작 (하루 {POSTS_PER_DAY}개)")
    post_articles()
    print(f"[{datetime.now()}] 완료")
