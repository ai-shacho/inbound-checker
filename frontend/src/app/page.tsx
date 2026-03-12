"use client";

import { useState, useRef, useEffect, useCallback } from "react";

// APIのベースURL
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// 判定結果の型定義
interface ScoringResult {
  url: string;
  company_name: string;
  classification: string;
  score: number; // 該当条件数（0〜4）
  matched_keywords: string[];
  met_conditions: string[];
  hreflang_langs: string[];
  processed_at: string;
  status: string;
}

// SSE進捗イベントの型定義
interface ProgressEvent {
  session_id?: string;
  completed: number;
  total: number;
  inbound_count: number;
  current_url: string;
  result: ScoringResult | null;
  done: boolean;
  elapsed_seconds: number;
}

export default function Home() {
  const [urlText, setUrlText] = useState<string>("");
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [results, setResults] = useState<ScoringResult[]>([]);
  const [progress, setProgress] = useState<ProgressEvent | null>(null);
  const [sessionId, setSessionId] = useState<string>("");
  const [isDone, setIsDone] = useState<boolean>(false);
  const [apiStatus, setApiStatus] = useState<"checking" | "ok" | "error">("checking");

  const abortRef = useRef<AbortController | null>(null);

  // URL件数のリアルタイムカウント
  const urlCount = urlText
    .split("\n")
    .filter((line) => line.trim().length > 0).length;

  // サマリー計算
  const inboundCount = results.filter((r) => r.classification === "インバウンド").length;
  const nonInboundCount = results.filter((r) => r.classification === "非インバウンド").length;
  const timeoutCount = results.filter((r) => r.status === "timeout").length;
  const spaCount = results.filter((r) => r.status === "spa").length;

  // コールドスタート対策
  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((res) => {
        if (res.ok) setApiStatus("ok");
        else setApiStatus("error");
      })
      .catch(() => setApiStatus("error"));
  }, []);

  // 判定開始
  const handleStart = useCallback(async () => {
    const urls = urlText
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.length > 0)
      .slice(0, 1000);

    if (urls.length === 0) return;

    setIsProcessing(true);
    setResults([]);
    setProgress(null);
    setIsDone(false);
    setSessionId("");

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch(`${API_URL}/api/judge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ urls }),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error("APIリクエストに失敗しました");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const jsonStr = line.slice(6).trim();
          if (!jsonStr) continue;

          try {
            const event = JSON.parse(jsonStr);

            if (event.session_id && !event.done) {
              setSessionId(event.session_id);
              continue;
            }

            const progressEvent = event as ProgressEvent;

            if (progressEvent.result) {
              setResults((prev) => [...prev, progressEvent.result!]);
            }

            setProgress(progressEvent);

            if (progressEvent.done) {
              setIsDone(true);
              setIsProcessing(false);
            }
          } catch {
            // JSONパースエラーは無視
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") {
        // キャンセル
      } else {
        console.error("処理エラー:", err);
      }
    } finally {
      setIsProcessing(false);
    }
  }, [urlText]);

  // キャンセル
  const handleCancel = useCallback(async () => {
    abortRef.current?.abort();
    if (sessionId) {
      try {
        await fetch(`${API_URL}/api/cancel/${sessionId}`, { method: "POST" });
      } catch {
        // 無視
      }
    }
    setIsProcessing(false);
  }, [sessionId]);

  // CSVダウンロード
  const handleDownload = useCallback(
    (fileType: string) => {
      if (!sessionId) return;
      window.open(`${API_URL}/api/csv/${sessionId}/${fileType}`, "_blank");
    },
    [sessionId]
  );

  // バッジの色
  const getBadgeClass = (classification: string): string => {
    switch (classification) {
      case "インバウンド":
        return "bg-green-100 text-green-800 border-green-200";
      case "非インバウンド":
        return "bg-gray-100 text-gray-600 border-gray-200";
      default:
        return "bg-orange-100 text-orange-700 border-orange-200";
    }
  };

  // 条件バッジの色
  const getConditionColor = (condition: string): string => {
    if (condition.startsWith("A:")) return "bg-blue-100 text-blue-700";
    if (condition.startsWith("B:")) return "bg-purple-100 text-purple-700";
    if (condition.startsWith("C:")) return "bg-teal-100 text-teal-700";
    return "bg-gray-100 text-gray-600";
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-5xl mx-auto px-4 py-8">
        {/* ヘッダー */}
        <h1 className="text-2xl font-bold text-center mb-2">
          インバウンド企業判定システム
        </h1>
        <p className="text-center text-gray-500 text-sm mb-6">
          企業HPのURLからインバウンド企業かどうかを自動判定します
        </p>

        {/* 判定基準の説明 */}
        <div className="bg-white rounded-lg shadow-sm border p-5 mb-6">
          <h2 className="text-sm font-bold text-gray-700 mb-3">判定基準：以下のいずれか1つ以上に該当すればインバウンド企業と判定</h2>
          <p className="text-xs text-gray-400 mb-3">※ インバウンド支援事業（マーケティング支援、観光誘致コンサル等）は対象外</p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs text-gray-600">
            <div className="flex items-start gap-2">
              <span className="inline-block px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 font-medium shrink-0">A</span>
              <span>HP上で訪日外国人を対象とした事業を明示的に宣言している</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="inline-block px-1.5 py-0.5 rounded bg-purple-100 text-purple-700 font-medium shrink-0">B</span>
              <span>免税・多言語ガイド・海外決済等、訪日外国人向け専用サービスを提供</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="inline-block px-1.5 py-0.5 rounded bg-teal-100 text-teal-700 font-medium shrink-0">C</span>
              <span>観光・宿泊業に属し、かつ実質的な多言語対応を行っている</span>
            </div>
          </div>
        </div>

        {/* APIステータス */}
        {apiStatus === "checking" && (
          <div className="mb-4 p-3 bg-blue-50 text-blue-700 rounded text-sm text-center">
            APIサーバーに接続中...
          </div>
        )}
        {apiStatus === "error" && (
          <div className="mb-4 p-3 bg-red-50 text-red-700 rounded text-sm text-center">
            APIサーバーに接続できません。しばらく待ってからリロードしてください。
          </div>
        )}

        {/* URL入力エリア */}
        <div className="bg-white rounded-lg shadow-sm border p-6 mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            URLを1行1件で入力してください（最大1000件）
          </label>
          <textarea
            className="w-full h-[300px] border border-gray-300 rounded-lg p-3 text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
            placeholder={"https://example.com\nhttps://example.co.jp\n..."}
            value={urlText}
            onChange={(e) => setUrlText(e.target.value)}
            disabled={isProcessing}
          />
          <div className="mt-2 text-right text-sm text-gray-500">
            入力URL数：<span className="font-bold text-gray-700">{urlCount}</span> 件
            {urlCount > 1000 && (
              <span className="text-red-500 ml-2">（1000件を超えた分は無視されます）</span>
            )}
          </div>
        </div>

        {/* アクションボタン */}
        <div className="flex gap-3 mb-6">
          <button
            onClick={handleStart}
            disabled={isProcessing || urlCount === 0}
            className="px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            判定開始
          </button>
          {isProcessing && (
            <button
              onClick={handleCancel}
              className="px-6 py-3 bg-red-500 text-white rounded-lg font-medium hover:bg-red-600 transition-colors"
            >
              キャンセル
            </button>
          )}
        </div>

        {/* 進捗バー */}
        {isProcessing && progress && (
          <div className="bg-white rounded-lg shadow-sm border p-6 mb-6">
            <div className="flex justify-between text-sm text-gray-600 mb-2">
              <span>
                {progress.completed}件完了 / {progress.total}件中（インバウンド：{progress.inbound_count}件）
              </span>
              <span>{progress.elapsed_seconds}秒</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-3">
              <div
                className="bg-blue-500 h-3 rounded-full transition-all duration-300"
                style={{
                  width: `${progress.total > 0 ? (progress.completed / progress.total) * 100 : 0}%`,
                }}
              />
            </div>
            {progress.current_url && (
              <div className="mt-2 text-xs text-gray-400 truncate">
                処理中: {progress.current_url}
              </div>
            )}
          </div>
        )}

        {/* サマリー */}
        {isDone && (
          <div className="bg-white rounded-lg shadow-sm border p-6 mb-6">
            <h2 className="text-lg font-bold mb-4">処理結果サマリー</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <div className="bg-green-50 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-green-600">{inboundCount}</div>
                <div className="text-sm text-gray-600">インバウンド</div>
              </div>
              <div className="bg-gray-50 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-gray-600">{nonInboundCount}</div>
                <div className="text-sm text-gray-600">非インバウンド</div>
              </div>
              <div className="bg-orange-50 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-orange-600">{timeoutCount + spaCount}</div>
                <div className="text-sm text-gray-600">タイムアウト/SPA</div>
              </div>
              <div className="bg-blue-50 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-blue-600">{progress?.elapsed_seconds}秒</div>
                <div className="text-sm text-gray-600">処理時間</div>
              </div>
            </div>

            {/* CSVダウンロードボタン */}
            <div className="flex flex-wrap gap-3">
              <button
                onClick={() => handleDownload("all_result")}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 transition-colors"
              >
                all_result.csv
              </button>
              <button
                onClick={() => handleDownload("inbound")}
                className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm hover:bg-green-700 transition-colors"
              >
                inbound.csv
              </button>
              <button
                onClick={() => handleDownload("non_inbound")}
                className="px-4 py-2 bg-gray-600 text-white rounded-lg text-sm hover:bg-gray-700 transition-colors"
              >
                non_inbound.csv
              </button>
            </div>
          </div>
        )}

        {/* 結果テーブル */}
        {results.length > 0 && (
          <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b">
                    <th className="text-left px-4 py-3 font-medium text-gray-600">URL</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-600">企業名</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-600">判定</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-600">該当条件</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-600">根拠</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r, i) => (
                    <tr key={i} className="border-b last:border-b-0 hover:bg-gray-50">
                      <td className="px-4 py-3 max-w-[200px] truncate">
                        <a
                          href={r.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:underline"
                        >
                          {r.url}
                        </a>
                      </td>
                      <td className="px-4 py-3 max-w-[150px] truncate">{r.company_name}</td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-block px-2 py-1 rounded-full text-xs font-medium border ${getBadgeClass(r.classification)}`}
                        >
                          {r.classification}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1">
                          {r.met_conditions && r.met_conditions.length > 0 ? (
                            r.met_conditions.map((cond, j) => (
                              <span
                                key={j}
                                className={`inline-block px-1.5 py-0.5 rounded text-xs font-medium ${getConditionColor(cond)}`}
                              >
                                {cond.split(":")[0]}
                              </span>
                            ))
                          ) : (
                            <span className="text-xs text-gray-400">-</span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 max-w-[200px] truncate text-xs text-gray-500">
                        {r.matched_keywords.join(", ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
