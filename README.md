# インバウンド企業判定システム

企業HPのURLからインバウンド企業（訪日外国人をターゲットとしたビジネスを行う企業）かどうかを自動判定するWebアプリケーションです。

## 構成

- **フロントエンド**: Next.js + Tailwind CSS（Vercelにデプロイ）
- **バックエンド**: Python FastAPI（Renderにデプロイ）

## ローカル開発

### バックエンド起動

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windowsの場合: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### フロントエンド起動

```bash
cd frontend
npm install
npm run dev
```

ブラウザで http://localhost:3000 にアクセスしてください。

## デプロイ手順

### 1. GitHubへのプッシュ

```bash
# リポジトリのルートディレクトリで実行
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/<ユーザー名>/<リポジトリ名>.git
git push -u origin main
```

### 2. Renderへのバックエンドデプロイ

1. [Render](https://render.com) にログインし「New +」→「Web Service」を選択
2. GitHubリポジトリを接続
3. 以下を設定:
   - **Name**: `inbound-checker-api`（任意）
   - **Root Directory**: `backend`
   - **Runtime**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free
4. 「Create Web Service」をクリック
5. デプロイ完了後、表示されるURL（例: `https://inbound-checker-api.onrender.com`）をメモ

### 3. Vercelへのフロントエンドデプロイ

1. [Vercel](https://vercel.com) にログインし「New Project」を選択
2. GitHubリポジトリをインポート
3. 以下を設定:
   - **Root Directory**: `frontend`
   - **Framework Preset**: Next.js（自動検出）
4. 環境変数を設定:
   - **Key**: `NEXT_PUBLIC_API_URL`
   - **Value**: RenderのURL（例: `https://inbound-checker-api.onrender.com`）
5. 「Deploy」をクリック

### 注意事項

- Renderの無料プランでは一定時間アクセスがないとスリープ状態になります。初回アクセス時は起動に30〜60秒かかる場合があります（コールドスタート）。フロントエンドは初期表示時に自動的にヘルスチェックを行い、APIの起動を促します。
- 大量のURLを処理する場合、Renderの無料プランではタイムアウトする可能性があります。
