"""
インバウンド企業判定ロジック（定義ベース）

【インバウンド企業の定義】
以下4つの条件のうち、いずれか1つ以上を満たす企業をインバウンド企業と判定する。

条件A: インバウンド事業の明示宣言
  → HP上で「インバウンド」「訪日外国人」等のキーワードを用いて、
    訪日外国人を対象とした事業であることを明示的に記載している。

条件B: 訪日外国人向け専用サービスの提供
  → 免税対応、多言語ガイド、ビザサポート、空港送迎、ハラール対応、
    海外決済（銀聯/Alipay/WeChat Pay）など、訪日外国人を主要ターゲットとした
    サービスを提供している。

条件C: 観光・宿泊業における多言語対応
  → ホテル・旅館・ゲストハウス・ツアー等の観光関連業種に属し、
    かつhreflangタグ・言語切替リンク・Google Translate等による
    実質的な多言語対応を行っている。

条件D: インバウンド集客・マーケティング支援事業
  → インバウンドマーケティング、訪日促進支援、観光誘致、DMO等、
    インバウンド集客や支援を事業として行っている。
"""
from models import ScrapedData, ScoringResult
from datetime import datetime, timezone, timedelta


# --- 条件A: インバウンド事業の明示宣言キーワード ---
CONDITION_A_KEYWORDS = [
    # 日本語
    "インバウンド事業", "インバウンド対応", "インバウンド観光", "インバウンドツーリズム",
    "インバウンド需要", "インバウンド消費", "訪日インバウンド",
    "訪日外国人", "訪日旅行者", "訪日観光客", "訪日客", "訪日外客",
    "外国人観光客", "着地型旅行",
    # 英語
    "inbound tourism", "inbound travel", "visit japan", "visiting japan",
    "welcome to japan", "foreign visitors", "foreign tourists",
    "international visitors", "overseas tourists", "overseas visitors",
    "accommodation for foreigners",
]

# --- 条件B: 訪日外国人向け専用サービスキーワード ---
CONDITION_B_KEYWORDS = [
    # 免税関連
    "免税対応", "免税手続き", "免税品", "免税店",
    "tax free", "duty free", "tax-free shopping",
    # 多言語サービス
    "多言語対応", "多言語サービス", "多言語化", "外国語対応",
    "英語対応", "中国語対応", "韓国語対応",
    "multilingual", "multilingual support", "multilingual staff",
    "外国人スタッフ", "バイリンガル", "通訳サービス", "翻訳サービス",
    "english speaking staff", "english menu",
    # 外国人向けサービス
    "外国人向け", "ビザサポート", "空港送迎",
    "ハラール対応", "ベジタリアン対応",
    "外貨両替", "両替サービス",
    "ランドオペレーター",
    # 海外決済
    "銀聯カード", "unionpay", "alipay", "wechat pay",
    # 中国語・韓国語での案内表記
    "欢迎光临", "中文対応", "简体中文", "繁體中文", "韓国語対応",
]

# --- 条件C: 観光・宿泊業の業種キーワード ---
CONDITION_C_INDUSTRY_KEYWORDS = [
    "ホテル", "旅館", "民泊", "ゲストハウス", "ホステル",
    "旅行代理店", "ツアー", "観光バス", "観光ガイド", "ツアーガイド",
    "観光", "宿泊", "旅行", "sightseeing", "tourism",
    "travel guide", "tour guide", "hotel", "hostel", "guesthouse",
]

# --- 条件D: インバウンド支援事業キーワード ---
CONDITION_D_KEYWORDS = [
    "インバウンドマーケティング", "訪日促進", "訪日促進支援",
    "観光誘致", "観光振興", "観光促進", "観光PR",
    "DMO", "外国人旅行",
    "inbound marketing", "inbound",
]


def _contains_any(text: str, keywords: list[str]) -> list[str]:
    """テキスト中に含まれるキーワードのリストを返す"""
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]


def _has_multilingual_support(data: ScrapedData) -> bool:
    """実質的な多言語対応を行っているか判定する"""
    # hreflangにja以外の言語コードが含まれる
    non_ja_langs = [lang for lang in data.hreflang_langs if lang.lower() not in ("ja", "x-default")]
    if non_ja_langs:
        return True
    # 言語切替リンクがある
    if data.has_language_switcher:
        return True
    # Google Translateが埋め込まれている
    if data.has_google_translate:
        return True
    return False


def calculate_score(data: ScrapedData, threshold: int = 0) -> ScoringResult:
    """
    インバウンド企業の定義に基づいて判定する。
    4条件のうち1つでも該当すればインバウンド企業と判定。
    thresholdパラメータは後方互換のため残すが使用しない。
    """
    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S")

    # 全テキストを結合して検索対象とする
    full_text = " ".join([
        data.title, data.meta_description, data.body_text, data.nav_header_text
    ])

    met_conditions: list[str] = []  # 該当した条件のリスト
    evidence: list[str] = []  # 根拠となるキーワード

    # --- 条件A: インバウンド事業の明示宣言 ---
    matched_a = _contains_any(full_text, CONDITION_A_KEYWORDS)
    if matched_a:
        met_conditions.append("A:インバウンド事業の明示")
        evidence.extend(matched_a[:3])

    # --- 条件B: 訪日外国人向け専用サービス ---
    matched_b = _contains_any(full_text, CONDITION_B_KEYWORDS)
    # 条件Bは2つ以上のキーワードが該当した場合のみ（1つだけだと偶発的な一致の可能性）
    if len(matched_b) >= 2:
        met_conditions.append("B:訪日外国人向けサービス")
        evidence.extend(matched_b[:3])

    # --- 条件C: 観光・宿泊業 × 多言語対応 ---
    matched_c_industry = _contains_any(full_text, CONDITION_C_INDUSTRY_KEYWORDS)
    has_multilingual = _has_multilingual_support(data)
    if matched_c_industry and has_multilingual:
        met_conditions.append("C:観光業×多言語対応")
        evidence.extend(matched_c_industry[:2])
        # 多言語対応の根拠を追加
        non_ja = [l for l in data.hreflang_langs if l.lower() not in ("ja", "x-default")]
        if non_ja:
            evidence.append(f"hreflang:{','.join(non_ja)}")
        if data.has_language_switcher:
            evidence.append("言語切替リンク")
        if data.has_google_translate:
            evidence.append("Google Translate")

    # --- 条件D: インバウンド支援事業 ---
    matched_d = _contains_any(full_text, CONDITION_D_KEYWORDS)
    # 「inbound」単体は汎用的すぎるため、他のD条件キーワードも必要
    d_without_generic = [kw for kw in matched_d if kw.lower() != "inbound"]
    if d_without_generic:
        met_conditions.append("D:インバウンド支援事業")
        evidence.extend(d_without_generic[:3])

    # --- 判定 ---
    is_inbound = len(met_conditions) > 0

    # 企業名をタイトルから取得
    company_name = data.title
    for sep in ["|", "｜", " - ", "–", "—", "：", ":"]:
        if sep in company_name:
            company_name = company_name.split(sep)[0].strip()
            break

    # 重複除去して上位5件
    seen: set[str] = set()
    unique_evidence: list[str] = []
    for e in evidence:
        if e not in seen:
            seen.add(e)
            unique_evidence.append(e)
        if len(unique_evidence) >= 5:
            break

    return ScoringResult(
        url=data.url,
        company_name=company_name,
        classification="インバウンド" if is_inbound else "非インバウンド",
        score=len(met_conditions),  # 該当条件数（0〜4）
        matched_keywords=unique_evidence,
        met_conditions=met_conditions,
        hreflang_langs=data.hreflang_langs,
        processed_at=now,
        status="success"
    )
