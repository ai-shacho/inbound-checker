"""データモデル定義"""
from pydantic import BaseModel
from typing import Optional


class ScrapeRequest(BaseModel):
    """スクレイピングリクエスト"""
    urls: list[str]


class ScrapedData(BaseModel):
    """スクレイピング結果データ"""
    url: str
    title: str = ""
    meta_description: str = ""
    hreflang_langs: list[str] = []
    body_text: str = ""
    nav_header_text: str = ""
    html_lang: str = ""
    has_google_translate: bool = False
    has_language_switcher: bool = False


class ScoringResult(BaseModel):
    """判定結果"""
    url: str
    company_name: str = ""
    classification: str = ""  # インバウンド / 非インバウンド / タイムアウト / 取得不可（SPA）
    score: int = 0  # 該当条件数（0〜4）
    matched_keywords: list[str] = []  # 根拠キーワード
    met_conditions: list[str] = []  # 該当した条件（A〜D）
    hreflang_langs: list[str] = []
    processed_at: str = ""
    status: str = "success"  # success / timeout / spa / skip


class ProgressEvent(BaseModel):
    """SSE進捗イベント"""
    completed: int = 0
    total: int = 0
    inbound_count: int = 0
    current_url: str = ""
    result: Optional[ScoringResult] = None
    done: bool = False
    elapsed_seconds: float = 0.0
