# Short Video Factory

YouTube Shorts / TikTok / Instagram リールで**いま再生数を伸ばしている動画の要点を抽出**し、
それを組み込んだ**商品紹介ショート動画を量産**するツールです。

自分の商品の認知を広げ、購入につなげるためのショート動画マーケティングを自動化します。

## 仕組み

```
1. research  トレンド収集   YouTube/TikTok/Instagram から再生数の高いショート動画のデータを収集
2. analyze   要点抽出       Claude がフック・構成・映像表現・ハッシュタグの「勝ちパターン」を抽出
3. script    台本生成       トレンド × あなたの商品 × スタイル指定 で台本を量産
4. produce   動画生成       音声合成 + 素材 + テロップ を ffmpeg で 9:16 の mp4 に組み立て
```

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

### 4. 素材の準備 (任意・推奨)

商品の実写素材があるほど動画の質が上がります。

- `assets/broll/` … 商品や生活シーンの動画素材 (mp4など)
- `assets/images/` … 商品写真など (自動でゆっくりズームする演出付き)

ファイル名にキーワードを入れると、台本のシーン指示と自動でマッチングされます
(例: `product_closeup.mp4`, `desk_morning.jpg`)。素材がない場合はテロップ中心の
グラデーション背景で生成されます。

## 使い方

```bash
# トレンド収集 (例: スキンケア系のYouTube Shorts上位20件)
svf research --platform youtube --query "スキンケア" --limit 20

# 収集したトレンドから勝ちパターンを抽出
svf analyze

# 「可愛い女の子が紹介」スタイルで台本を3本生成
svf script --style kawaii_presenter --count 3

# 台本から動画を生成 (data/scripts/ 内の全台本)
svf produce

# ↑を一括実行して5本量産
svf run --style hands_only --query "コーヒー" --count 5

# スタイル一覧
svf styles
```

生成された動画は `output/` に、台本は `data/scripts/` に保存されます。
台本JSONは手で修正してから `svf produce` に渡すこともできます。

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
