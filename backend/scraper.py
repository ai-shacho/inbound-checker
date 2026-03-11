"""Webスクレイピングモジュール"""
import asyncio
import random
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from models import ScrapedData

# ユーザーエージェント
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 言語切替テキストのパターン
LANGUAGE_SWITCH_PATTERNS = re.compile(
    r'\b(EN|English|ENGLISH|中文|한국어|繁體|简体|Français|Chinese|Korean|French)\b',
    re.IGNORECASE
)


async def scrape_url(url: str, semaphore: asyncio.Semaphore) -> tuple[Optional[ScrapedData], str]:
    """
    URLをスクレイピングしてデータを返す。
    戻り値: (ScrapedData or None, status)
    status: "success" / "timeout" / "spa" / "skip"
    """
    async with semaphore:
        # ランダムウェイト（0.1〜0.3秒）
        await asyncio.sleep(random.uniform(0.1, 0.3))

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(15.0),
                follow_redirects=True,
                verify=False,
                headers={"User-Agent": USER_AGENT}
            ) as client:
                response = await client.get(url)

                # 403/404はスキップ
                if response.status_code in (403, 404):
                    return None, "skip"

                # その他のエラーステータス
                if response.status_code >= 400:
                    return None, "skip"

                html = response.text

        except httpx.TimeoutException:
            return None, "timeout"
        except Exception:
            # その他の接続エラーはスキップ
            return None, "skip"

        # HTMLパース
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return None, "skip"

        # ボディテキスト取得
        body_text = ""
        if soup.body:
            # scriptとstyleタグを除去
            for tag in soup.body.find_all(["script", "style"]):
                tag.decompose()
            body_text = soup.body.get_text(separator=" ", strip=True)[:5000]

        # テキストが200文字未満の場合はSPAと判断
        if len(body_text) < 200:
            return None, "spa"

        # ページタイトル
        title = soup.title.string.strip() if soup.title and soup.title.string else ""

        # メタディスクリプション
        meta_desc = ""
        meta_tag = soup.find("meta", attrs={"name": "description"})
        if meta_tag and meta_tag.get("content"):
            meta_desc = meta_tag["content"]

        # hreflangタグ一覧
        hreflang_langs: list[str] = []
        for link in soup.find_all("link", attrs={"hreflang": True}):
            lang = link.get("hreflang", "")
            if lang and lang not in hreflang_langs:
                hreflang_langs.append(lang)

        # navタグとheaderタグの内容
        nav_header_text = ""
        for tag_name in ["nav", "header"]:
            for tag in soup.find_all(tag_name):
                nav_header_text += " " + tag.get_text(separator=" ", strip=True)

        # html要素のlang属性
        html_lang = ""
        html_tag = soup.find("html")
        if html_tag and html_tag.get("lang"):
            html_lang = html_tag["lang"]

        # Google Translateスクリプトの検出
        has_google_translate = bool(
            soup.find("script", src=re.compile(r"translate\.google", re.IGNORECASE))
            or "google_translate_element" in html.lower()
            or "googletranslate" in html.lower().replace(" ", "")
        )

        # 言語切替リンクの検出（navとheader内のaタグ）
        has_language_switcher = False
        for tag_name in ["nav", "header"]:
            for container in soup.find_all(tag_name):
                for a_tag in container.find_all("a"):
                    link_text = a_tag.get_text(strip=True)
                    if LANGUAGE_SWITCH_PATTERNS.search(link_text):
                        has_language_switcher = True
                        break
                if has_language_switcher:
                    break
            if has_language_switcher:
                break

        return ScrapedData(
            url=url,
            title=title,
            meta_description=meta_desc,
            hreflang_langs=hreflang_langs,
            body_text=body_text,
            nav_header_text=nav_header_text,
            html_lang=html_lang,
            has_google_translate=has_google_translate,
            has_language_switcher=has_language_switcher,
        ), "success"
