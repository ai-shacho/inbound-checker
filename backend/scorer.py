"""インバウンド企業判定スコアリングロジック"""
import re
from models import ScrapedData, ScoringResult
from datetime import datetime, timezone, timedelta

# --- Layer1: 日本語インバウンドキーワード ---
LAYER1_5PT = [
    "インバウンド", "訪日外国人", "訪日旅行者", "訪日観光客", "訪日客",
    "訪日インバウンド", "インバウンド需要", "インバウンド対応", "インバウンド消費",
    "訪日外客", "外国人観光客", "着地型旅行", "インバウンド観光",
    "インバウンドツーリズム", "訪日促進"
]
LAYER1_3PT = [
    "免税店", "免税対応", "免税手続き", "免税品", "多言語対応", "多言語サービス",
    "多言語化", "外国語対応", "英語対応", "中国語対応", "韓国語対応",
    "外国人スタッフ", "バイリンガル", "通訳サービス", "翻訳サービス",
    "外国人向け", "観光誘致", "観光振興", "観光促進", "外国人旅行",
    "インバウンドマーケティング", "ランドオペレーター", "外貨両替", "両替サービス",
    "銀聯カード", "訪日旅行", "DMO", "ハラール対応", "ベジタリアン対応",
    "ビザサポート", "空港送迎"
]
LAYER1_1PT = [
    "観光", "旅行", "ホテル", "旅館", "宿泊", "外国語", "多言語", "観光客",
    "旅行者", "外国人", "海外", "国際", "免税", "ゲストハウス", "ホステル",
    "民泊", "ツアーガイド", "観光ガイド", "SIMカード", "訪問者", "海外旅行者"
]

# --- Layer2: 英語・多言語キーワード ---
LAYER2_5PT = [
    "inbound", "inbound tourism", "inbound travel", "visit japan", "visiting japan",
    "welcome to japan", "foreign visitors", "foreign tourists", "international visitors",
    "overseas tourists", "overseas visitors", "tax free", "duty free",
    "tax-free shopping", "multilingual", "multilingual support", "multilingual staff",
    "accommodation for foreigners"
]
LAYER2_3PT = [
    "english menu", "english speaking staff", "english speaking", "foreign language",
    "overseas", "international", "tourism", "travel guide", "tour guide",
    "sightseeing", "unionpay", "alipay", "wechat pay"
]

# --- Layer4: 業種・サービスキーワード ---
LAYER4_KEYWORDS = [
    "ホテル", "旅館", "民泊", "ゲストハウス", "ホステル", "旅行代理店",
    "ツアー", "観光バス", "空港", "免税店", "両替", "外貨", "通訳",
    "翻訳", "インバウンドマーケティング", "観光PR", "訪日促進支援"
]

# --- Layer5: 中国語・韓国語キーワード ---
LAYER5_CN = ["欢迎光临", "免税", "中文対応", "简体中文", "繁體中文"]
LAYER5_KR = ["한국어", "韓国語対応"]

# --- Layer3: 言語切替テキスト ---
LANGUAGE_SWITCH_TEXTS = [
    "EN", "English", "中文", "한국어", "繁體", "简体", "Français",
    "english", "ENGLISH", "Chinese", "Korean", "French"
]


def _count_keywords(text: str, keywords: list[str], points: int, max_score: int) -> tuple[int, list[str]]:
    """テキスト中のキーワードを検出してスコアとマッチしたキーワードを返す"""
    score = 0
    matched: list[str] = []
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower:
            score += points
            matched.append(kw)
            if score >= max_score:
                return max_score, matched
    return min(score, max_score), matched


def calculate_score(data: ScrapedData, threshold: int = 30) -> ScoringResult:
    """スクレイピングデータからインバウンドスコアを算出する"""
    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S")

    # 全テキストを結合して検索対象とする
    full_text = " ".join([
        data.title, data.meta_description, data.body_text, data.nav_header_text
    ])

    total_score = 0
    all_matched: list[str] = []

    # Layer1: 日本語インバウンドキーワード（最大35点）
    layer1_score = 0
    layer1_matched: list[str] = []
    for keywords, points in [(LAYER1_5PT, 5), (LAYER1_3PT, 3), (LAYER1_1PT, 1)]:
        remaining = 35 - layer1_score
        if remaining <= 0:
            break
        s, m = _count_keywords(full_text, keywords, points, remaining)
        layer1_score += s
        layer1_matched.extend(m)
    layer1_score = min(layer1_score, 35)
    total_score += layer1_score
    all_matched.extend(layer1_matched)

    # Layer2: 英語・多言語キーワード（最大25点）
    layer2_score = 0
    layer2_matched: list[str] = []
    for keywords, points in [(LAYER2_5PT, 5), (LAYER2_3PT, 3)]:
        remaining = 25 - layer2_score
        if remaining <= 0:
            break
        s, m = _count_keywords(full_text, keywords, points, remaining)
        layer2_score += s
        layer2_matched.extend(m)
    layer2_score = min(layer2_score, 25)
    total_score += layer2_score
    all_matched.extend(layer2_matched)

    # Layer3: HTML構造シグナル（最大25点）
    layer3_score = 0
    # hreflangにja以外が含まれるか
    non_ja_langs = [lang for lang in data.hreflang_langs if lang.lower() not in ("ja", "x-default")]
    if non_ja_langs:
        layer3_score += 15
        all_matched.append(f"hreflang:{','.join(non_ja_langs)}")

    # 言語切替リンクの検出
    if data.has_language_switcher:
        layer3_score += 10
        all_matched.append("言語切替リンク")

    # Google Translateスクリプト
    if data.has_google_translate:
        layer3_score += 5
        all_matched.append("Google Translate")

    # html lang属性が複数言語対応
    if data.html_lang and data.html_lang.lower() not in ("ja", ""):
        layer3_score += 5
        all_matched.append(f"lang={data.html_lang}")

    layer3_score = min(layer3_score, 25)
    total_score += layer3_score

    # Layer4: 業種・サービスキーワード（最大15点）
    s4, m4 = _count_keywords(full_text, LAYER4_KEYWORDS, 3, 15)
    total_score += s4
    all_matched.extend(m4)

    # Layer5: 中国語・韓国語表記（最大10点）
    layer5_score = 0
    layer5_matched: list[str] = []
    for kw in LAYER5_CN:
        if kw in full_text:
            layer5_score += 3
            layer5_matched.append(kw)
    for kw in LAYER5_KR:
        if kw in full_text:
            layer5_score += 3
            layer5_matched.append(kw)
    layer5_score = min(layer5_score, 10)
    total_score += layer5_score
    all_matched.extend(layer5_matched)

    # 最大100点に丸める
    total_score = min(total_score, 100)

    # 企業名をタイトルから取得（区切り文字で分割して最初の部分を使用）
    company_name = data.title
    for sep in ["|", "｜", " - ", "–", "—", "：", ":"]:
        if sep in company_name:
            company_name = company_name.split(sep)[0].strip()
            break

    # 判定
    if total_score >= threshold:
        classification = "インバウンド"
    else:
        classification = "非インバウンド"

    # マッチしたキーワード上位5件
    top_keywords = all_matched[:5]

    return ScoringResult(
        url=data.url,
        company_name=company_name,
        classification=classification,
        score=total_score,
        matched_keywords=top_keywords,
        hreflang_langs=data.hreflang_langs,
        processed_at=now,
        status="success"
    )
