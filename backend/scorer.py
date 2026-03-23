"""
インバウンド企業判定ロジック（定義ベース）

【インバウンド企業の定義】
訪日外国人に対して直接サービスを提供する企業をインバウンド企業と判定する。
以下の条件のうち、いずれか1つ以上を満たすことが必要。

※ インバウンド支援事業（マーケティング支援、観光誘致コンサル等）は
  訪日外国人に直接サービスを提供するわけではないため対象外とする。

条件A: インバウンド事業の明示宣言
  → HP上で「インバウンド」「訪日外国人」等のキーワードを用いて、
    訪日外国人を対象とした事業であることを明示的に記載している。

条件B: 訪日外国人向け専用サービスの提供
  → 免税対応、多言語ガイド、ビザサポート、空港送迎、ハラール対応、
    海外決済（銀聯/Alipay/WeChat Pay）など、訪日外国人を主要ターゲットとした
    サービスを提供している。
  → HIGH キーワードは1件でも該当すれば条件成立。
    MEDIUM キーワードは2件以上で条件成立。

条件C: 観光・宿泊業における多言語対応
  → ホテル・旅館・ゲストハウス・ツアー等の観光関連業種に属し、
    かつhreflangタグ・言語切替リンク・Google Translate等による
    実質的な多言語対応を行っている。

条件D: 観光・宿泊業の名称がタイトルに含まれ、外国人向けサービスを示す語がある
  → タイトルにホテル・旅館等の業種名を含み、かつボディに外国人・観光等の語を含む。
"""
import re
from models import ScrapedData, ScoringResult
from datetime import datetime, timezone, timedelta


# --- 条件A: インバウンド事業の明示宣言キーワード ---
CONDITION_A_KEYWORDS = [
    # 日本語（単体・複合）
    "インバウンド",
    "インバウンド事業", "インバウンド対応", "インバウンド観光", "インバウンドツーリズム",
    "インバウンド需要", "インバウンド消費", "訪日インバウンド",
    "訪日",
    "訪日外国人", "訪日旅行者", "訪日観光客", "訪日客", "訪日外客",
    "外国人旅行者", "外国人客",
    "海外旅行者", "海外観光客",
    "外国人観光客", "着地型旅行",
    # 英語
    "inbound tourism", "inbound travel", "visit japan", "visiting japan",
    "welcome to japan", "foreign visitors", "foreign tourists",
    "international visitors", "overseas tourists", "overseas visitors",
    "accommodation for foreigners",
    "tourist", "tourists",
    "foreign traveler", "foreign travelers",
    "international tourist",
    "travel to japan", "japan travel", "japan tourism",
]

# --- 条件B-HIGH: 1件でも該当すれば条件成立 ---
CONDITION_B_HIGH = [
    "免税対応", "免税店",
    "空港送迎",
    "ビザサポート",
    "ハラール対応",
    "外国人向け", "外国人スタッフ",
    "銀聯", "unionpay", "alipay", "wechat pay",
    "多言語対応", "多言語サービス",
    "multilingual support", "multilingual staff",
]

# --- 条件B-MEDIUM: 2件以上で条件成立 ---
CONDITION_B_MEDIUM = [
    "免税",
    "英語対応", "中国語対応", "韓国語対応",
    "通訳サービス", "翻訳サービス",
    "english menu", "english speaking",
    "tax free", "duty free",
    "multilingual",
    "両替", "外貨両替",
]

# --- 後方互換: 旧CONDITION_B_KEYWORDSは参照しない ---

# --- 条件C: 観光・宿泊業の業種キーワード ---
CONDITION_C_INDUSTRY_KEYWORDS = [
    "ホテル", "旅館", "民泊", "ゲストハウス", "ホステル",
    "旅行代理店", "ツアー", "観光バス", "観光ガイド", "ツアーガイド",
    "観光", "宿泊", "旅行", "sightseeing", "tourism",
    "travel guide", "tour guide", "hotel", "hostel", "guesthouse",
]

# --- 条件D: タイトルに宿泊業名 ---
CONDITION_D_TITLE_KEYWORDS = [
    "ホテル", "旅館", "ゲストハウス", "ホステル", "民泊",
    "hotel", "hostel", "ryokan",
]

CONDITION_D_BODY_KEYWORDS = [
    "外国人", "foreign", "international", "overseas", "tourist",
    "訪日", "観光",
]

# --- 中国語特徴文字（「的」「是」「我」「您」「欢」「谢」「请」「为」「来」「服」） ---
CHINESE_INDICATOR_CHARS = set("的是我您欢谢请为来服")
CJK_RANGE = re.compile(r'[\u4e00-\u9fff]')
HANGUL_RANGE = re.compile(r'[\uac00-\ud7a3]')


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
    # html_lang が ja 以外（en, zh, ko など）
    if data.html_lang and not data.html_lang.lower().startswith("ja"):
        return True
    # ボディテキストに中国語文字が含まれる
    # CJK文字が5文字以上かつ中国語特徴文字が含まれる
    cjk_chars = CJK_RANGE.findall(data.body_text)
    if len(cjk_chars) >= 5:
        indicator_count = sum(1 for c in cjk_chars if c in CHINESE_INDICATOR_CHARS)
        if indicator_count >= 5:
            return True
    # ボディテキストにハングル文字が10文字以上含まれる
    hangul_chars = HANGUL_RANGE.findall(data.body_text)
    if len(hangul_chars) >= 10:
        return True
    return False


def calculate_score(data: ScrapedData, threshold: int = 0) -> ScoringResult:
    """
    インバウンド企業の定義に基づいて判定する。
    条件A/B/C/D のいずれか1つでも該当すればインバウンド企業と判定。
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
    matched_b_high = _contains_any(full_text, CONDITION_B_HIGH)
    matched_b_medium = _contains_any(full_text, CONDITION_B_MEDIUM)
    # HIGH: 1件以上で成立
    if matched_b_high:
        met_conditions.append("B:訪日外国人向けサービス(HIGH)")
        evidence.extend(matched_b_high[:3])
    # MEDIUM: 2件以上で成立（かつまだ条件B未成立の場合も加算）
    elif len(matched_b_medium) >= 2:
        met_conditions.append("B:訪日外国人向けサービス(MEDIUM)")
        evidence.extend(matched_b_medium[:3])

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

    # --- 条件D: 宿泊業タイトル × 外国人向けキーワード ---
    title_lower = data.title.lower()
    has_hospitality_title = any(kw.lower() in title_lower for kw in CONDITION_D_TITLE_KEYWORDS)
    if has_hospitality_title:
        matched_d_body = _contains_any(data.body_text, CONDITION_D_BODY_KEYWORDS)
        if matched_d_body:
            met_conditions.append("D:宿泊業×外国人向け")
            evidence.extend(matched_d_body[:2])

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
