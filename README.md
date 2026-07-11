# Short Video Factory

YouTube Shorts / TikTok / Instagram リールで**いま再生数を伸ばしている動画の要点を抽出**し、
それを組み込んだ**商品紹介ショート動画を量産**するツールです。

自分の商品の認知を広げ、購入につなげるためのショート動画マーケティングを自動化します。

## 仕組み

```
1. research   トレンド収集   YouTube/TikTok/Instagram から再生数の高いショート動画のデータを収集
2. curate     人間による判定 収集した動画を1件ずつ確認し、参考にしてよいか (good/bad) を判定
3. analyze    要点抽出       Claude がgood判定の動画からのみフック・構成・映像表現の「勝ちパターン」を抽出
4. script     台本生成       トレンド × あなたの商品 × スタイル指定 で台本を量産 (8割exploit/2割explore)
5. produce    動画生成       音声合成 + 素材 + テロップ を ffmpeg で 9:16 の mp4 に組み立て
──────────────── (ここで実際にSNSへ投稿するかは人間が判断) ────────────────
6. publish    公開判断       実際に投稿したか (published) / しなかったか (rejected) を記録
7. report     実績記録       投稿後のインプレッション数などと、良い伸び方だったか (quality: good/bad) を記録
                             → 次の script 生成が、良い実績のパターンを優先的に再利用する
```

### なぜ「良い動画」を作り続けられるのか (改善ループ)

インプレッション数や再生数だけを基準に学習すると、**炎上煽り・釣りタイトルのような
動画が「勝ちパターン」として強化されてしまう**リスクがあります。これを防ぐため、
このツールは2箇所で人間の判断を必須にしています。

1. **`curate`(参考にする動画の選別)** — トレンド収集した動画を分析にかける前に、
   1件ずつ人間が「参考にしてよい (good)」か「参考にしない (bad)」かを判定します。
   bad判定の動画は `analyze` の入力から完全に除外されます。
2. **`report`(実績の質の判定)** — 投稿後の実績を記録する際、数値と一緒に
   「quality: good / bad」も記録します。仮に数値が良くても、炎上・誤解を招く
   煽りで伸びただけなら bad と記録すれば、そのパターンは次回以降**強化されません**
   (bad評価の数値は平均エンゲージメント率の計算から除外されます)。

`script` コマンドで台本を複数生成すると、実績データが十分に溜まっている場合、
**約8割はこれまでで最も反応が良かった(good評価のみで算出した)パターンを踏襲**し、
**約2割はあえて違うフック・構成を試します**。この探索分から新しい勝ちパターンが
見つかれば、次回はそちらが8割側に採用されていきます。

そして、**動画を実際にSNSへ投稿するかどうかは、常に人間 (`svf publish`) が決めます**。
このツールが自動で投稿することはありません。実績 (`svf report`) を記録できるのも、
`svf publish` で「投稿した」と記録した動画のみです。

### どの動画から購入されたかを特定する (計測リンク入り固定コメント)

台本には1本ごとに**固有の計測コード**と、動画の内容に合わせて文面が少しずつ違う
**固定コメント文**が自動で付きます。`svf links <script_id>` を実行すると、
プラットフォーム別の計測リンク (UTMパラメータ付き商品URL) を差し込んだ
コピペ用の固定コメントが表示されるので、投稿直後にコメント欄へ書き込んで固定します。

```
動画で紹介したのはこれです☕ → https://あなたの商品URL?utm_source=youtube&utm_medium=short_video&utm_campaign=svf_gilqql
```

- LP側のアクセス解析 (GA4など) で `utm_campaign=svf_xxxxxx` を見れば、
  **どの動画から何人来て何人買ったかが動画単位で分かります**
- リンクを踏まず検索して買う人向けに、計測コードは `SVF-XXXXXX` 形式の
  クーポンコードとしても使えます (ショップ側でコード登録が必要)
- 計測した数値を `svf report --clicks --purchases` で記録すると、
  8:2学習の勝ちパターン選定が「バズるパターン」ではなく
  「**購入につながるパターン**」を優先するようになります

## スタイルプリセット (動画の内容を細かく指定)

| プリセット | 内容 | 商品の見せ方 |
|---|---|---|
| `kawaii_presenter` | 可愛い女の子が商品を紹介 | 主役として紹介 |
| `english_presenter` | 白人の女の子が英語で商品を紹介 (海外向け) | 主役として紹介 |
| `hands_only` | 人物なし。手元と生活シーンでさりげなく紹介 | さりげなく |
| `daily_scene` | 一般人が撮った日常のワンシーン。商品はただ写っているだけ | 背景に写り込むだけ |

`config/styles/*.yaml` を編集・追加すれば、出演者・話し方・映像の雰囲気・尺・
商品の見せ方 (featured / subtle / background) を自由に定義できます。

## セットアップ

### 1. 必要なもの

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/) (`brew install ffmpeg` / `apt install ffmpeg`)
- Claude API キー (必須。分析と台本生成に使用)
- YouTube Data API キー (YouTubeのトレンド収集に使用)

### 2. インストール

```bash
git clone <このリポジトリ>
cd Short-Video-Factory
pip install -e .
```

### 3. 設定

```bash
cp .env.example .env          # APIキーを記入
cp config/product.example.yaml config/product.yaml   # 商品情報を記入
```

`config/product.yaml` に商品名・ターゲット・訴求ポイント・NG表現などを書きます。
ここの内容がすべての台本に反映されます。

### 4. 商品写真の取り込み (推奨)

```bash
svf add-photos 商品写真1.jpg 商品写真2.png
```

取り込んだ写真は `assets/product/` に保存され、**動画の中で商品が映るシーン
(featured / subtle) に自動的に登場します**。

- featured (商品が主役) のシーン → 必ず商品写真が使われる
- subtle (さりげなく映る) のシーン → 合う一般素材がなければ商品写真が使われる
- none (商品を映さない) のシーン → 商品写真は使われない
- 複数枚あればローテーションで使われ、静止画にはゆっくりズームの演出が付きます

### 5. その他の素材 (任意)

- `assets/broll/` … 商品や生活シーンの動画素材 (mp4など)
- `assets/images/` … 背景用の静止画素材

ファイル名にキーワードを入れると、台本のシーン指示と自動でマッチングされます
(例: `desk_morning.jpg`)。素材がない場合はテロップ中心の
グラデーション背景で生成されます。

## 使い方

```bash
# 1. トレンド収集 (例: スキンケア系のYouTube Shorts上位20件)
svf research --platform youtube --query "スキンケア" --limit 20

# 2. 収集した動画を1件ずつ確認し、参考にしてよいか判定 (対話式)
svf curate

# 3. good判定の動画から勝ちパターンを抽出
svf analyze

# 4. 「可愛い女の子が紹介」スタイルで台本を3本生成 (8割exploit/2割explore)
svf script --style kawaii_presenter --count 3

# 4'. 自分の意図を反映したい場合 (雰囲気・方向性 + 必ず入れるテキスト)
svf script --style kawaii_presenter --count 3 \
  --brief "梅雨の時期に合う、しっとり落ち着いた雰囲気で" \
  --must-text "今だけ送料無料" --must-text "詳細はプロフへ"

# 5. 台本から動画を生成 (data/scripts/ 内の全台本)
svf produce

# --- ここで動画の中身を確認し、実際にSNSへ投稿するかは自分で判断 ---

# 6. 投稿時: 計測リンク入りの固定コメントを取得してコメント欄に固定
svf links kawaii_presenter_20260708_xxxxxxxx

# 7. 投稿した場合、公開決定を記録 (script_idは data/scripts/<id>.json の<id>)
svf publish kawaii_presenter_20260708_xxxxxxxx --decision published --note "本人確認OK"

# 8. 数日後、実績を記録 (数値 + 良い伸び方だったかのquality評価)
#    --clicks/--purchases を入れると勝ちパターン選定が「購入率」優先になる
svf report kawaii_presenter_20260708_xxxxxxxx \
  --platform youtube --quality good \
  --impressions 50000 --views 12000 --likes 800 --comments 40 --saves 60 \
  --clicks 150 --purchases 6 --revenue 8880

# これまでの実績から見えている「勝ちパターン」を確認
svf leaderboard

# 1〜5を一括実行して5本量産 (curateは対話式で組み込み済み)
svf run --style hands_only --query "コーヒー" --count 5

# スタイル一覧
svf styles
```

生成された動画は `output/` に、台本は `data/scripts/` に保存されます。
台本JSONは手で修正してから `svf produce` に渡すこともできます。

実績データ (`data/feedback/`) が溜まるほど、`svf script` の8割は良い実績の
パターンを踏襲するようになります。継続的にクオリティを上げていくには、
投稿のたびに `svf publish` → `svf report` を行うことが重要です。

## プラットフォーム別のトレンド収集について

| プラットフォーム | 方式 |
|---|---|
| YouTube | YouTube Data API v3 (公式) で直近14日の再生数上位ショートを検索。字幕も取得して分析精度を上げる |
| TikTok | 公式のトレンドAPIが無いため、[TikTok Creative Center](https://ads.tiktok.com/business/creativecenter/) で見つけた動画URLを `data/sources/tiktok_urls.txt` に貼ると、公式oEmbed APIでメタデータを取得 |
| Instagram | Instagram Graph API のハッシュタグ検索 (ビジネス/クリエイターアカウントが必要) |

## 音声合成

| プロバイダー | 特徴 | 設定 |
|---|---|---|
| `edge` (デフォルト) | 無料・キー不要・日英対応 | 不要 |
| `voicevox` | 無料・日本語キャラボイス | ローカルでVOICEVOXエンジンを起動 |
| `elevenlabs` | 高品質・多言語 | `ELEVENLABS_API_KEY` |

```bash
svf produce --tts voicevox
```

## AIアバター動画 (人物が出演するスタイル) について

`kawaii_presenter` / `english_presenter` のような人物出演スタイルは、
本ツールが生成する**台本 (セリフ・カメラ指示・シーン割り)** をそのまま
HeyGen・Kling・Runway などのAI動画生成サービスや実際の撮影に使う想定です。
台本JSONの `visual_direction` が撮影指示書になります。
(素材なしで `produce` した場合はテロップ+ナレーション動画として出力されます)

## 運用上の注意

- 各プラットフォームの規約・広告表記ルール (ステマ規制含む) に従ってください。
  PR・広告である場合は `#PR` などの表記が必要です。
- トレンドの「要点 (フック・構成のパターン)」を参考にするツールであり、
  特定動画の複製は行わないでください。
- 効果効能の断定表現は `config/product.yaml` の `ng_expressions` でブロックできます。

## ディレクトリ構成

```
config/
  product.yaml          # あなたの商品情報 (product.example.yaml をコピー)
  styles/*.yaml         # スタイルプリセット
assets/
  broll/                # 動画素材
  images/               # 画像素材
data/
  trends/               # 収集したトレンドデータ
  insights/             # 抽出した勝ちパターン
  scripts/              # 生成された台本
output/                 # 完成した動画 (9:16 mp4)
```
