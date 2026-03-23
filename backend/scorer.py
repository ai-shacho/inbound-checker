"""
インバウンド企業判定ロジック（定義ベース）

【インバウンド企業の定義】
訪日外国人に対して直接サービスを提供する企業をインバウンド企業と判定する。
以下の条件のうち、いずれか1つ以上を満たすことが必要。

※ インバウンド支援事業（マーケティング支援、観光誘致コンサル等）は
  訪日外国人に直接サービスを提供するわけではないため対象外とする。

条件A: インバウンド事業の明示宣言
条件B: 訪日外国人向け専用サービス（HIGH: 1件, MEDIUM: 2件以上）
条件C: 観光・宿泊業 × 多言語対応
条件D: 宿泊業タイトル × 外国人向けキーワード
条件E: 予約・口コミプラットフォーム掲載（TripAdvisor等）
条件F: 観光業種 × 英語テキストの実在
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
    "訪日外国人", "訪日旅行者", "訪日観光客", "訪日客", "訪日外客",
    "外国人旅行者", "外国人客", "外国人観光客",
    "海外旅行者", "海外観光客",
    "着地型旅行",
    # 英語
    "inbound", "inbound tourism", "inbound travel", "visit japan", "visiting japan",
    "welcome to japan", "foreign visitors", "foreign tourists",
    "international visitors", "overseas tourists", "overseas visitors",
    "accommodation for foreigners",
    "travel to japan", "japan travel", "japan tourism",
    "foreign traveler", "foreign travelers",
    "international tourist",
]

# --- 条件B-HIGH: 1件でも該当すれば条件成立（外国人向け専用サービスの明確証拠） ---
CONDITION_B_HIGH = [
    # 免税（外国人旅行者のみ対象のサービス）
    "免税対応", "免税店", "免税手続き", "免税品",
    "tax free", "duty free", "tax-free", "tax free shopping",
    # 外国人特化サービス（空港送迎は海外旅行でも使うのでMEDIUMへ移動）
    "ビザサポート", "ビザ申請",
    "ハラール対応", "ハラール", "halal",
    "コーシャ", "ベジタリアン対応",
    "外国人向け", "外国人専用", "外国人スタッフ", "外国語スタッフ",
    # 海外決済（訪日外国人しか使わない）
    "銀聯", "銀聯カード", "unionpay", "union pay",
    "alipay", "アリペイ",
    "wechat pay", "wechatpay", "ウィーチャットペイ", "ウィーチャット",
    # 多言語対応（明示的）
    "多言語対応", "多言語サービス", "多言語化",
    "multilingual support", "multilingual staff", "multilingual",
    "外国語対応",
    # ランドオペレーター
    "ランドオペレーター",
]

# --- 条件B-MEDIUM: 2件以上で条件成立 ---
CONDITION_B_MEDIUM = [
    "免税",
    "英語対応", "英語メニュー", "英語スタッフ",
    "中国語対応", "韓国語対応",
    "通訳サービス", "通訳", "翻訳サービス",
    "english menu", "english speaking", "english staff",
    "税金還付",
    "両替", "外貨両替", "外貨",
    "バイリンガル",
    "観光ガイド", "ツアーガイド",
    "外国語", "多言語",
    "空港送迎",  # 海外旅行でも使う語のため単独では不十分、2件以上の組み合わせで判定
]

# --- 条件C: 観光・宿泊業の業種キーワード ---
# 注: 「宿泊」「旅行」「観光」単体は汎用すぎるため、より具体的なキーワードを優先
CONDITION_C_INDUSTRY_KEYWORDS = [
    "ホテル", "旅館", "民泊", "ゲストハウス", "ホステル",
    "旅行代理店", "観光バス", "観光ガイド", "ツアーガイド",
    "sightseeing", "tourism",
    "travel guide", "tour guide", "hotel", "hostel", "guesthouse", "ryokan",
    "貸し部屋", "貸部屋",
]

# 汎用的すぎる業種語（単独では判定に使わない、補助的に使用）
CONDITION_C_GENERIC_KEYWORDS = [
    "宿泊施設", "宿泊業", "宿泊サービス",
    "旅行業", "旅行会社", "旅行サービス",
    "観光施設", "観光業", "観光地",
    "ツアー会社", "ツアー企画",
]

# HR専業サイトのネガティブキーワード（誤検知防止）
# 注: 「採用情報」は一般企業も持つので除外。HR「サービス」として特化した会社のみ対象。
NEGATIVE_KEYWORDS = [
    "転職サービス", "求人サービス", "採用支援サービス",
    "人材紹介サービス", "人材派遣サービス",
    "就職支援サービス",
]

# --- 条件D: タイトルに宿泊業名 ---
CONDITION_D_TITLE_KEYWORDS = [
    "ホテル", "旅館", "ゲストハウス", "ホステル", "民泊",
    "hotel", "hostel", "ryokan", "inn",
]

CONDITION_D_BODY_KEYWORDS = [
    "外国人", "foreign", "international", "overseas", "tourist",
    "訪日", "観光客", "旅行者", "visitor",
]

# --- 条件E: 予約・口コミプラットフォーム（掲載されている=インバウンド対応済みの証拠） ---
CONDITION_E_PLATFORMS = [
    "tripadvisor", "trip advisor", "トリップアドバイザー",
    "booking.com", "ブッキングドットコム",
    "expedia", "エクスペディア",
    "agoda", "アゴダ",
    "airbnb", "エアービーアンドビー", "エアビーアンドビー",
    "hotels.com",
    "jalan.net", "楽天トラベル",  # 国内だが外国人も多い
    "hostelworld",
    "kkday", "klook", "クルック",
    "veltra", "ベルトラ",
    "viator",
    "jnto",  # 日本政府観光局掲載
]

# --- 条件F: 観光業 × 英語テキスト（英語文字が一定量以上あれば外国人向けの可能性） ---
# 英語単語パターン（3文字以上のASCII連続）
ENGLISH_WORD_PATTERN = re.compile(r'[a-zA-Z]{4,}')

# --- 中国語・韓国語検出 ---
CHINESE_INDICATOR_CHARS = set("的是我您欢谢请为来服务")
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
    cjk_chars = CJK_RANGE.findall(data.body_text)
    if len(cjk_chars) >= 5:
        indicator_count = sum(1 for c in cjk_chars if c in CHINESE_INDICATOR_CHARS)
        if indicator_count >= 3:
            return True
    # ボディテキストにハングル文字が10文字以上含まれる
    hangul_chars = HANGUL_RANGE.findall(data.body_text)
    if len(hangul_chars) >= 10:
        return True
    return False


def _count_english_words(text: str) -> int:
    """英語らしい単語数をカウント（日本語サイト上の英語コンテンツ検出用）"""
    # 日本語特有の英語語（URL, ブランド名等）を除外するため4文字以上で計測
    matches = ENGLISH_WORD_PATTERN.findall(text)
    # ありがちな日本語英単語（Japan, Tokyo, etc.）を除く
    exclude = {"japan", "tokyo", "osaka", "kyoto", "http", "html", "https",
               "www", "com", "net", "org", "corp", "email", "mail",
               "copyright", "rights", "reserved", "privacy", "policy",
               "terms", "service", "about", "contact", "menu", "home",
               "page", "news", "info", "blog", "shop", "online",
               "hotel", "tour", "travel", "booking", "reserve"}
    content_words = [w.lower() for w in matches if w.lower() not in exclude]
    return len(content_words)


def calculate_score(data: ScrapedData, threshold: int = 0) -> ScoringResult:
    """
    インバウンド企業の定義に基づいて判定する。
    条件A〜F のいずれか1つでも該当すればインバウンド企業と判定。
    """
    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S")

    # 全テキストを結合して検索対象とする
    full_text = " ".join([
        data.title, data.meta_description, data.body_text, data.nav_header_text
    ])

    met_conditions: list[str] = []
    evidence: list[str] = []

    # --- ネガティブチェック: 採用・HR系サイトは除外 ---
    is_hr_site = bool(_contains_any(full_text, NEGATIVE_KEYWORDS))

    # --- 条件A: インバウンド事業の明示宣言 ---
    # タイトル・メタ・ナビ/ヘッダーに含まれる場合は強いシグナル（1件で成立）
    # ボディのみの場合は記事・ニュースで言及されているだけの可能性があるため2件以上必要
    prominent_text = " ".join([
        data.title,
        data.meta_description,
        data.meta_keywords,
        data.og_description,
        data.nav_header_text
    ])
    matched_a_prominent = _contains_any(prominent_text, CONDITION_A_KEYWORDS)
    matched_a_body = _contains_any(data.body_text, CONDITION_A_KEYWORDS)

    if matched_a_prominent:
        # タイトル・メタ・ナビに出現 → 1件で成立
        # （自社がインバウンド事業であることを正面に打ち出している）
        met_conditions.append("A:インバウンド事業の明示")
        evidence.extend(matched_a_prominent[:3])
    # ボディのみの場合は条件Aとしては判定しない
    # → ニュースサイト・ブログ・業界メディアが記事の中でキーワードを使うケースを排除
    # → ボディ内キーワードは他条件（B〜G）との組み合わせで間接的にカバー

    # --- 条件B: 訪日外国人向け専用サービス ---
    matched_b_high = _contains_any(full_text, CONDITION_B_HIGH)
    matched_b_medium = _contains_any(full_text, CONDITION_B_MEDIUM)

    # タイトル・メタに「免税」単体があれば HIGH 判定として扱う
    prominent_lower = prominent_text.lower()
    if "免税" in prominent_lower and not any("免税" in kw for kw in matched_b_high):
        matched_b_high = list(matched_b_high) + ["免税(タイトル/メタ)"]

    if matched_b_high:
        met_conditions.append("B:訪日外国人向けサービス(HIGH)")
        evidence.extend(matched_b_high[:3])
    elif len(matched_b_medium) >= 2:
        met_conditions.append("B:訪日外国人向けサービス(MEDIUM)")
        evidence.extend(matched_b_medium[:3])

    # --- 条件C: 観光・宿泊業 × 多言語対応 ---
    matched_c_industry = _contains_any(full_text, CONDITION_C_INDUSTRY_KEYWORDS)
    matched_c_generic = _contains_any(full_text, CONDITION_C_GENERIC_KEYWORDS)
    # 汎用キーワードのみの場合は2件以上必要
    effective_c_industry = matched_c_industry or len(matched_c_generic) >= 2
    has_multilingual = _has_multilingual_support(data)
    if effective_c_industry and has_multilingual and not is_hr_site:
        met_conditions.append("C:観光業×多言語対応")
        evidence.extend(matched_c_industry[:2] or matched_c_generic[:2])
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

    # --- 条件E: 予約・口コミプラットフォーム掲載 ---
    matched_e = _contains_any(full_text, CONDITION_E_PLATFORMS)
    if matched_e:
        # プラットフォーム掲載 + 観光関連業種で判定（一般企業がTripAdvisor等に掲載されることは稀）
        if matched_c_industry:
            met_conditions.append("E:観光プラットフォーム掲載")
            evidence.extend(matched_e[:2])
        elif len(matched_e) >= 2:
            # 2つ以上掲載されていれば業種不問でインバウンド
            met_conditions.append("E:複数観光プラットフォーム掲載")
            evidence.extend(matched_e[:3])

    # --- 条件G: 言語サブページ × 観光・宿泊業種 ---
    # 大企業（SoftBank, Toyota等）も /zh/ /ko/ /en/ を持つため、
    # 観光・宿泊業種との組み合わせを必須とする（業種不問での単独判定は誤検知の原因）
    if data.found_language_subpages and effective_c_industry and not is_hr_site:
        met_conditions.append(f"G:観光業×言語サブページ({','.join(data.found_language_subpages[:3])})")
        evidence.extend(data.found_language_subpages[:3])

    # --- 条件F: 観光業種 × 英語テキストが豊富 ---
    if matched_c_industry and not met_conditions:
        # まだどの条件にも該当していない観光業種のみ追加チェック
        english_word_count = _count_english_words(data.body_text)
        if english_word_count >= 30:
            # 観光業で英語コンテンツが30語以上あれば外国人向けと推定
            met_conditions.append(f"F:観光業×英語コンテンツ({english_word_count}語)")
            evidence.append(f"英語{english_word_count}語")

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
        score=len(met_conditions),
        matched_keywords=unique_evidence,
        met_conditions=met_conditions,
        hreflang_langs=data.hreflang_langs,
        processed_at=now,
        status="success"
    )
