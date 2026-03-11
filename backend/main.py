"""インバウンド企業判定API - メインエントリポイント"""
import asyncio
import csv
import io
import json
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response

from models import ScrapeRequest, ScoringResult, ProgressEvent
from scraper import scrape_url
from scorer import calculate_score

app = FastAPI(title="インバウンド企業判定API")

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 処理結果を一時保存する辞書（セッションID -> 結果リスト）
results_store: dict[str, list[ScoringResult]] = {}

# キャンセルフラグ
cancel_flags: dict[str, bool] = {}


@app.get("/health")
async def health_check() -> dict[str, str]:
    """ヘルスチェックエンドポイント（コールドスタート対策）"""
    return {"status": "ok"}


@app.post("/api/judge")
async def judge_urls(request: ScrapeRequest) -> StreamingResponse:
    """
    URLリストを受け取り、SSEでリアルタイムに進捗と結果を返す。
    最終的にセッションIDを返し、CSV取得に使用する。
    """
    session_id = str(uuid.uuid4())
    cancel_flags[session_id] = False

    async def event_stream() -> AsyncGenerator[str, None]:
        urls = request.urls
        threshold = request.threshold
        total = len(urls)
        completed = 0
        inbound_count = 0
        all_results: list[ScoringResult] = []
        start_time = time.time()

        # セッションID通知
        yield f"data: {json.dumps({'session_id': session_id})}\n\n"

        # 30並列のセマフォ
        semaphore = asyncio.Semaphore(30)

        async def process_url(url: str) -> ScoringResult | None:
            """個別URLの処理"""
            nonlocal completed, inbound_count

            # キャンセルチェック
            if cancel_flags.get(session_id, False):
                return None

            jst = timezone(timedelta(hours=9))
            now = datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S")

            try:
                scraped_data, status = await scrape_url(url, semaphore)

                if status == "timeout":
                    result = ScoringResult(
                        url=url,
                        company_name="",
                        classification="タイムアウト",
                        score=0,
                        matched_keywords=[],
                        hreflang_langs=[],
                        processed_at=now,
                        status="timeout"
                    )
                elif status == "spa":
                    result = ScoringResult(
                        url=url,
                        company_name="",
                        classification="取得不可（SPA）",
                        score=0,
                        matched_keywords=[],
                        hreflang_langs=[],
                        processed_at=now,
                        status="spa"
                    )
                elif status == "skip" or scraped_data is None:
                    # 403/404/その他エラーはスキップ（CSVに出力しない）
                    completed += 1
                    return None
                else:
                    result = calculate_score(scraped_data, threshold)

                    if result.classification == "インバウンド":
                        inbound_count += 1

                completed += 1
                return result

            except Exception:
                # 個別エラーは握りつぶして次へ
                completed += 1
                return None

        # 全URLを非同期タスクとして実行
        tasks = [asyncio.create_task(process_url(url)) for url in urls]

        for coro in asyncio.as_completed(tasks):
            if cancel_flags.get(session_id, False):
                # 残りタスクをキャンセル
                for t in tasks:
                    t.cancel()
                break

            result = await coro
            if result is not None:
                all_results.append(result)

            # 進捗イベント送信
            elapsed = time.time() - start_time
            event = ProgressEvent(
                completed=completed,
                total=total,
                inbound_count=inbound_count,
                current_url=result.url if result else "",
                result=result,
                done=False,
                elapsed_seconds=round(elapsed, 1)
            )
            yield f"data: {event.model_dump_json()}\n\n"

        # 完了イベント
        elapsed = time.time() - start_time
        results_store[session_id] = all_results
        done_event = ProgressEvent(
            completed=completed,
            total=total,
            inbound_count=inbound_count,
            done=True,
            elapsed_seconds=round(elapsed, 1)
        )
        yield f"data: {done_event.model_dump_json()}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.post("/api/cancel/{session_id}")
async def cancel_processing(session_id: str) -> dict[str, str]:
    """処理のキャンセル"""
    cancel_flags[session_id] = True
    return {"status": "cancelled"}


def _build_csv(results: list[ScoringResult], filter_type: str = "all") -> str:
    """CSV文字列を生成する"""
    output = io.StringIO()
    # BOM付きUTF-8
    output.write("\ufeff")

    writer = csv.writer(output)
    writer.writerow([
        "url", "company_name", "classification", "score",
        "matched_keywords", "hreflang_langs", "processed_at"
    ])

    for r in results:
        if filter_type == "inbound" and r.classification != "インバウンド":
            continue
        if filter_type == "non_inbound" and r.classification != "非インバウンド":
            continue
        if filter_type == "inbound" and r.status in ("timeout", "spa"):
            continue
        if filter_type == "non_inbound" and r.status in ("timeout", "spa"):
            continue

        writer.writerow([
            r.url,
            r.company_name,
            r.classification,
            r.score,
            ",".join(r.matched_keywords),
            ",".join(r.hreflang_langs),
            r.processed_at
        ])

    return output.getvalue()


@app.get("/api/csv/{session_id}/{file_type}")
async def download_csv(session_id: str, file_type: str) -> Response:
    """CSV出力エンドポイント"""
    results = results_store.get(session_id, [])

    if file_type == "all_result":
        csv_data = _build_csv(results, "all")
        filename = "all_result.csv"
    elif file_type == "inbound":
        csv_data = _build_csv(results, "inbound")
        filename = "inbound.csv"
    elif file_type == "non_inbound":
        csv_data = _build_csv(results, "non_inbound")
        filename = "non_inbound.csv"
    else:
        return Response(content="Invalid file type", status_code=400)

    return Response(
        content=csv_data.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
