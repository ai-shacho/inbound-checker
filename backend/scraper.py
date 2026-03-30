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

# 言語別サブパスリスト（存在確認用）
LANGUAGE_SUBPATHS = [
    "/en", "/en/",
    "/english", "/english/",
    "/zh", "/zh/", "/zh-cn", "/zh-cn/", "/zh-tw", "/zh-tw/",
    "/chinese", "/chinese/",
    "/ko", "/ko/",
    "/korean", "/korean/",
    "/fr", "/fr/",
    "/lang/en", "/lang/zh", "/lang/ko",
    "/language/en", "/language/zh",
]

# 言語切替テキストのパターン
LANGUAGE_SWITCH_PATTERNS = re.compile(
    r'\b(EN|English|ENGLISH|中文|한국어|繁體|简体|Français|Chinese|Korean|French)\b',
    re.IGNORECASE
)


async def _check_language_subpages(base_url: str) -> list[str]:
    """
    ベースURLに対して言語別サブパスが存在するか並列チェックする。
    リダイレクト先が別ドメインの場合はカウントしない。
    HEADリクエストが拒否（405等）された場合はGETにフォールバック（最大2KB取得）。
    """
    from urllib.parse import urlparse

    subpage_sem = asyncio.Semaphore(20)  # 専用セマフォ（メインと別）
    base_parsed = urlparse(base_url)
    base_domain = base_parsed.netloc

    async def check_one(path: str) -> Optional[str]:
        target_url = f"{base_parsed.scheme}://{base_domain}{path}"
        async with subpage_sem:
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(5.0),
                    follow_redirects=False,
                    verify=False,
                    headers={"User-Agent": USER_AGENT}
                ) as client:
                    # まずHEADリクエストを試みる
                    try:
                        resp = await client.head(target_url)
                    except Exception:
                        return None

                    # HEADが許可されていない場合はGETにフォールバック
                    if resp.status_code == 405:
                        try:
                            resp = await client.get(target_url, headers={"Range": "bytes=0-2047"})
                        except Exception:
                            return None

                    # リダイレクトの場合、別ドメインへのリダイレクトはカウントしない
                    if resp.status_code in (301, 302, 303, 307, 308):
                        location = resp.headers.get("location", "")
                        if location:
                            redir_parsed = urlparse(location)
                            # 絶対URLの場合はドメインを確認
                            if redir_parsed.netloc and redir_parsed.netloc != base_domain:
                                return None
                        # 同一ドメインへのリダイレクトはOK（存在とみなす）
                        return path

                    # 200〜399 なら存在するとみなす
                    if 200 <= resp.status_code <= 399:
                        return path

                    return None
            except Exception:
                return None

    tasks = [check_one(path) for path in LANGUAGE_SUBPATHS]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


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

                # Content-Typeヘッダーのcharsetを確認して適切にデコード
                content_type = response.headers.get("content-type", "")
                if "charset=shift_jis" in content_type.lower() or "charset=sjis" in content_type.lower():
                    html = response.content.decode("shift_jis", errors="replace")
                elif "charset=euc-jp" in content_type.lower():
                    html = response.content.decode("euc-jp", errors="replace")
                else:
                    # Content-Typeヘッダーにcharsetがない場合、HTML内のmetaタグから検出
                    if not any(x in content_type.lower() for x in ["charset=shift_jis","charset=sjis","charset=euc-jp"]):
                        raw = response.content
                        # <meta charset="..."> または <meta http-equiv="Content-Type" content="...charset=...">
                        charset_match = re.search(
                            rb'<meta[^>]+charset=["\']?([A-Za-z0-9_\-]+)',
                            raw[:2048],
                            re.IGNORECASE
                        )
                        if charset_match:
                            detected = charset_match.group(1).decode("ascii", errors="ignore").lower()
                            if detected in ("shift_jis", "shift-jis", "sjis", "x-sjis"):
                                html = raw.decode("shift_jis", errors="replace")
                            elif detected in ("euc-jp", "euc_jp"):
                                html = raw.decode("euc-jp", errors="replace")
                            else:
                                html = response.text
                        else:
                            html = response.text
                    else:
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
            body_text = soup.body.get_text(separator=" ", strip=True)[:10000]

        # テキストが100文字未満の場合はSPAと判断
        if len(body_text) < 100:
            return None, "spa"

        # ページタイトル
        title = soup.title.string.strip() if soup.title and soup.title.string else ""

        # メタディスクリプション
        meta_desc = ""
        meta_tag = soup.find("meta", attrs={"name": "description"})
        if meta_tag and meta_tag.get("content"):
            meta_desc = meta_tag["content"]

        # meta keywords タグ（<meta name="keywords" content="...">）
        meta_keywords = ""
        kw_tag = soup.find("meta", attrs={"name": re.compile(r'^keywords$', re.IGNORECASE)})
        if kw_tag and kw_tag.get("content"):
            meta_keywords = kw_tag["content"]

        # Open Graph description（<meta property="og:description" content="...">）
        og_desc = ""
        og_tag = soup.find("meta", attrs={"property": "og:description"})
        if og_tag and og_tag.get("content"):
            og_desc = og_tag["content"]

        # hreflangタグ一覧
        hreflang_langs: list[str] = []
        for link in soup.find_all("link", attrs={"hreflang": True}):
            lang = link.get("hreflang", "")
            if lang and lang not in hreflang_langs:
                hreflang_langs.append(lang)

        # navタグ・headerタグ・footerタグ・language系div/ulの内容
        nav_header_text = ""
        for tag_name in ["nav", "header", "footer"]:
            for tag in soup.find_all(tag_name):
                nav_header_text += " " + tag.get_text(separator=" ", strip=True)
        # language系クラスのdiv/ul
        for selector_class in ["language", "lang", "lang-switcher", "language-switcher"]:
            for tag in soup.find_all(["div", "ul"], class_=re.compile(selector_class, re.IGNORECASE)):
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

        # 言語切替リンクの検出（nav・header・footer・language系divも対象）
        has_language_switcher = False
        for tag_name in ["nav", "header", "footer"]:
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

        # language系クラスのdiv/ulも確認
        if not has_language_switcher:
            for selector_class in ["language", "lang", "lang-switcher", "language-switcher"]:
                for container in soup.find_all(["div", "ul"], class_=re.compile(selector_class, re.IGNORECASE)):
                    for a_tag in container.find_all("a"):
                        link_text = a_tag.get_text(strip=True)
                        if LANGUAGE_SWITCH_PATTERNS.search(link_text):
                            has_language_switcher = True
                            break
                    if has_language_switcher:
                        break
                if has_language_switcher:
                    break

    # semaphore を解放した後でサブページチェック（semaphore 競合なし）
    found_language_subpages = await _check_language_subpages(url)

    # og:locale:alternate の検出（多言語対応の追加シグナル）
    has_og_locale_alternate = False
    for og_tag in soup.find_all("meta", property="og:locale:alternate"):
        content = og_tag.get("content", "")
        if content and content.lower() not in ("ja_jp", "ja"):
            has_og_locale_alternate = True
            break

    return ScrapedData(
        url=url,
        title=title,
        meta_description=meta_desc,
        meta_keywords=meta_keywords,
        og_description=og_desc,
        hreflang_langs=hreflang_langs,
        body_text=body_text,
        nav_header_text=nav_header_text,
        html_lang=html_lang,
        has_google_translate=has_google_translate,
        has_language_switcher=has_language_switcher,
        found_language_subpages=found_language_subpages,
        has_og_locale_alternate=has_og_locale_alternate,
    ), "success"
