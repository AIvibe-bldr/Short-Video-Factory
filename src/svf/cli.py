"""Short Video Factory CLI.

使い方:
  svf add-photos 商品写真1.jpg 商品写真2.png              # 商品写真の取り込み
  svf research --platform youtube --query "スキンケア"   # トレンド収集
  svf curate                                             # 参考にしてよいか人間が判定 (good/bad)
  svf analyze                                            # 要点抽出 (good判定のみ使用)
  svf script --style kawaii_presenter --count 3          # 台本生成 (8割exploit/2割explore)
  svf produce data/scripts/xxx.json                      # 動画生成
  svf links <script_id>                                  # 計測リンク入り固定コメントを表示
  svf publish <script_id> --decision published           # 投稿するか人間が最終決定
  svf report  <script_id> --platform youtube --quality good --views 12000 --likes 300
                                                          # 投稿後の実績を記録 (次の台本生成に反映)
  svf import-csv 実績.csv                                 # 実績のCSV一括取り込み (--template で雛形作成)
  svf sync-ga4 --days 28                                 # GA4から流入・購入データを自動取得して記録
  svf leaderboard                                        # 実績から見えている勝ちパターン
  svf run --style hands_only --query "コーヒー" --count 5 # 一括実行 (curate含む)
  svf styles                                             # スタイル一覧
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table

from svf.config import ASSETS_DIR, list_styles, load_style
from svf.pipeline import Pipeline, SCRIPTS_DIR, TRENDS_DIR
from svf.script.generator import load_script

PRODUCT_PHOTOS_DIR = ASSETS_DIR / "product"

app = typer.Typer(help="トレンド分析型ショート動画量産ツール", no_args_is_help=True)
console = Console()


@app.command()
def research(
    platform: List[str] = typer.Option(
        ["youtube"], "--platform", "-p",
        help="収集対象: youtube / tiktok / instagram (複数指定可)",
    ),
    query: str = typer.Option("", "--query", "-q", help="検索キーワード (商品ジャンルなど)"),
    limit: int = typer.Option(20, "--limit", "-n", help="プラットフォームごとの取得件数"),
):
    """再生数の高いショート動画のデータを収集する."""
    items, path = Pipeline().research(list(platform), query=query, limit=limit)
    table = Table(title=f"収集結果 {len(items)}件")
    table.add_column("PF", width=9)
    table.add_column("タイトル", max_width=50)
    table.add_column("再生数", justify="right")
    for i in items[:15]:
        table.add_row(i.platform, i.title[:50], f"{i.view_count:,}")
    console.print(table)
    console.print(f"[green]保存:[/green] {path}")


@app.command()
def curate():
    """収集済みのトレンド動画を1件ずつ確認し、参考にしてよいか (good/bad) を判定する.

    インプレッション数だけで学習すると炎上・釣り構成が「勝ちパターン」として
    強化されてしまうため、分析に進む前に必ずこの工程を通す。
    """
    from svf.curation import curate_interactive
    from svf.trends.base import latest_trends_path, load_latest_trends, overwrite_trends

    path = latest_trends_path(TRENDS_DIR)
    items = load_latest_trends(TRENDS_DIR)
    items = curate_interactive(items)
    overwrite_trends(items, path)
    good = sum(1 for i in items if i.human_rating == "good")
    bad = sum(1 for i in items if i.human_rating == "bad")
    console.print(
        f"[green]保存しました[/green] good:{good} / bad:{bad} / "
        f"未評価:{len(items) - good - bad}"
    )


@app.command()
def analyze():
    """収集済みトレンドから勝ちパターンを抽出する (Claude API使用)."""
    insights, path = Pipeline().analyze()
    console.print("[bold]■ フックのパターン[/bold]")
    for h in insights.hooks:
        console.print(f"  ・{h}")
    console.print("[bold]■ 構成のパターン[/bold]")
    for s in insights.structures:
        console.print(f"  ・{s}")
    console.print(f"\n[bold]要約:[/bold] {insights.summary}")
    console.print(f"[green]保存:[/green] {path}")


@app.command(name="add-photos")
def add_photos(
    photos: List[Path] = typer.Argument(..., help="商品写真・動画のパス (複数指定可)"),
):
    """商品の写真 (または動画) を取り込む.

    取り込んだ写真は assets/product/ に保存され、動画生成時に
    商品が映るシーン (featured/subtle) で優先的に使われる。
    """
    import shutil

    PRODUCT_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    for src in photos:
        if not src.exists():
            console.print(f"[red]見つかりません:[/red] {src}")
            continue
        if src.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".webm", ".mkv"}:
            console.print(f"[yellow]未対応の形式なのでスキップ:[/yellow] {src}")
            continue
        dest = PRODUCT_PHOTOS_DIR / src.name
        shutil.copy2(src, dest)
        console.print(f"[green]取り込み:[/green] {dest}")
        ok += 1
    total = sum(
        1 for p in PRODUCT_PHOTOS_DIR.glob("*")
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".webm", ".mkv"}
    )
    console.print(f"\n{ok}件を取り込みました。現在の商品素材: {total}件")
    console.print("動画生成時、商品が映るシーンでこれらの写真が自動的に使われます。")


@app.command()
def script(
    style: str = typer.Option(..., "--style", "-s", help="スタイルプリセット名"),
    count: int = typer.Option(1, "--count", "-c", help="生成する台本の本数"),
    brief: str = typer.Option(
        "", "--brief", "-b",
        help="動画の雰囲気・方向性の指定 (例: '梅雨の時期に合う落ち着いた雰囲気で')",
    ),
    must_text: List[str] = typer.Option(
        [], "--must-text", "-t",
        help="動画に必ず入れるテキスト (複数指定可)。テロップかナレーションに原文のまま入る",
    ),
):
    """トレンド × 商品 × スタイルで台本を生成する (Claude API使用).

    実績データがあれば約8割は勝ちパターンを踏襲 (exploit)、
    約2割はあえて違う構成を試す (explore)。
    --brief や --must-text で自分の意図を台本に反映できる。
    """
    scripts, paths = Pipeline().write_scripts(
        style, count=count, brief=brief, must_texts=list(must_text)
    )
    for s, p in zip(scripts, paths):
        tag = "[magenta]explore[/magenta]" if s.variant == "explore" else "[blue]exploit[/blue]"
        console.print(f"[bold cyan]{s.title}[/bold cyan]  ({tag} / {s.pattern_tag})")
        console.print(f"  フック: {s.hook}")
        console.print(f"  シーン数: {len(s.scenes)} / 尺: {s.total_seconds}秒")
        console.print(f"  計測コード: {s.short_code}")
        console.print(f"  [green]保存:[/green] {p}\n")
    console.print(
        "投稿時は `svf links <script_id>` で計測リンク入りの固定コメントを取得できます。"
    )


@app.command()
def produce(
    script_path: Optional[Path] = typer.Argument(
        None, help="台本JSONのパス (省略時は未生成の台本すべて)"
    ),
    tts: str = typer.Option("edge", "--tts", help="音声合成: edge / voicevox / elevenlabs"),
):
    """台本からショート動画 (9:16 mp4) を生成する."""
    pipeline = Pipeline()
    paths = [script_path] if script_path else sorted(SCRIPTS_DIR.glob("*.json"))
    if not paths:
        console.print("[red]台本がありません。先に `svf script` を実行してください。[/red]")
        raise typer.Exit(1)
    for p in paths:
        s = load_script(p)
        console.print(f"生成中: {s.script_id} ...")
        result = pipeline.produce(s, tts_provider=tts)
        console.print(f"  [green]完成:[/green] {result.video_path}")


@app.command()
def links(
    script_id: str = typer.Argument(..., help="台本ID (data/scripts/<id>.json の<id>部分)"),
    platform: List[str] = typer.Option(
        ["youtube", "tiktok", "instagram"], "--platform", "-p",
        help="投稿先プラットフォーム (複数指定可)",
    ),
):
    """動画ごとの計測リンク入り固定コメントを表示する (コピペ用).

    リンクには動画固有のコード (utm_campaign=svf_xxxxxx) が入っており、
    LP側のアクセス解析でどの動画から来たかを動画単位で特定できる。
    投稿直後にこのコメントを書き込み、固定すること。
    """
    from svf.config import load_product
    from svf.tracking import build_tracking_url, coupon_code, render_pinned_comment

    path = SCRIPTS_DIR / f"{script_id}.json"
    if not path.exists():
        console.print(f"[red]台本 {script_id} が見つかりません。[/red]")
        raise typer.Exit(1)
    s = load_script(path)
    if not s.short_code:
        console.print(
            "[yellow]この台本には計測コードがありません "
            "(旧バージョンで生成された台本です)。[/yellow]"
        )
        raise typer.Exit(1)
    try:
        product_url = load_product().url
    except FileNotFoundError:
        product_url = ""
    if not product_url:
        console.print(
            "[yellow]config/product.yaml の url が未設定です。"
            "設定するとリンクが生成されます。[/yellow]"
        )

    console.print(f"[bold]動画:[/bold] {s.title}")
    console.print(f"[bold]計測コード:[/bold] {s.short_code}  "
                  f"(クーポンとして使う場合: {coupon_code(s.short_code)})\n")
    for pf in platform:
        url = build_tracking_url(product_url, pf, s.short_code)
        comment = render_pinned_comment(s.pinned_comment, product_url, pf, s.short_code)
        console.print(f"[bold cyan]■ {pf}[/bold cyan]")
        if url:
            console.print(f"  計測リンク: {url}")
        console.print("  固定コメント (コピペ用):")
        console.print(f"[on grey11]{comment}[/on grey11]\n")
    console.print(
        "LP側のアクセス解析 (GA4など) で utm_campaign=svf_" + s.short_code +
        " のセッション数・購入数を確認し、`svf report` の --clicks / --purchases に記録してください。"
    )


@app.command()
def publish(
    script_id: str = typer.Argument(..., help="台本ID (data/scripts/<id>.json の<id>部分)"),
    decision: str = typer.Option(
        ..., "--decision", help="published (実際に投稿した) か rejected (投稿しない)"
    ),
    note: str = typer.Option("", "--note", help="判断理由のメモ (任意)"),
):
    """その動画を実際に投稿するかどうかの最終判断を記録する (ツールは自動投稿しない).

    投稿後の実績を `svf report` で記録するには、先にここで
    published を記録しておく必要がある。
    """
    if decision not in ("published", "rejected"):
        console.print("[red]--decision は published か rejected を指定してください[/red]")
        raise typer.Exit(1)
    Pipeline().publish_decision(script_id, decision, note)
    console.print(f"[green]記録しました:[/green] {script_id} → {decision}")


@app.command()
def report(
    script_id: str = typer.Argument(..., help="台本ID"),
    platform: str = typer.Option(..., "--platform", "-p", help="投稿先プラットフォーム"),
    quality: str = typer.Option(
        ..., "--quality",
        help="good か bad。炎上・釣りタイトルなど不健全な伸び方なら bad にする",
    ),
    impressions: int = typer.Option(0, "--impressions"),
    views: int = typer.Option(0, "--views"),
    likes: int = typer.Option(0, "--likes"),
    comments: int = typer.Option(0, "--comments"),
    saves: int = typer.Option(0, "--saves"),
    shares: int = typer.Option(0, "--shares"),
    clicks: int = typer.Option(
        0, "--clicks", help="計測リンクのクリック数 (LP解析の utm_campaign 別セッション数)"
    ),
    purchases: int = typer.Option(0, "--purchases", help="この動画経由の購入数"),
    revenue: float = typer.Option(0.0, "--revenue", help="この動画経由の売上 (任意)"),
    url: str = typer.Option("", "--url", help="投稿先URL (任意)"),
    notes: str = typer.Option("", "--notes", help="quality判定の理由 (任意)"),
):
    """投稿後の実績を記録する。bad評価の実績は次回の勝ちパターン強化から除外される.

    --clicks / --purchases を記録すると、勝ちパターンの選定基準が
    エンゲージメント率より購入率を優先するようになる。
    """
    if quality not in ("good", "bad"):
        console.print("[red]--quality は good か bad を指定してください[/red]")
        raise typer.Exit(1)
    record = Pipeline().report_performance(
        script_id,
        platform,
        quality,
        impressions=impressions,
        views=views,
        likes=likes,
        comments=comments,
        saves=saves,
        shares=shares,
        clicks=clicks,
        purchases=purchases,
        revenue=revenue,
        posted_url=url,
        quality_notes=notes,
    )
    msg = f"[green]記録しました[/green] エンゲージメント率: {record.engagement_rate():.2%}"
    if clicks or purchases:
        msg += f" / 購入率: {record.conversion_rate():.2%} ({purchases}件)"
    console.print(msg + f" (quality: {quality})")


@app.command(name="import-csv")
def import_csv(
    csv_path: Optional[Path] = typer.Argument(None, help="実績CSVのパス"),
    template: bool = typer.Option(
        False, "--template", help="記入用テンプレートCSVを作成して終了"
    ),
):
    """実績をCSVで一括取り込みする (TikTok Shop Seller Center等の数値の転記用).

    列: script_id または short_code / platform / quality (good|bad) /
        impressions, views, likes, comments, saves, shares,
        clicks, purchases, revenue, url, notes (数値は空欄可)
    """
    from svf.feedback.importer import TEMPLATE_CSV

    if template:
        dest = Path("performance_template.csv")
        dest.write_text(TEMPLATE_CSV, encoding="utf-8")
        console.print(f"[green]テンプレートを作成しました:[/green] {dest}")
        console.print("2行目以降のサンプルを消して、実際の数値を記入してください。")
        return
    if csv_path is None or not csv_path.exists():
        console.print("[red]CSVファイルを指定してください。テンプレートは --template で作成できます。[/red]")
        raise typer.Exit(1)

    result = Pipeline().import_performance_csv(csv_path)
    console.print(f"[green]{len(result.imported)}件を取り込みました[/green]")
    for rec in result.imported:
        msg = f"  ・{rec.script_id} ({rec.platform}) エンゲージ率 {rec.engagement_rate():.2%}"
        if rec.purchases or rec.clicks:
            msg += f" / 購入率 {rec.conversion_rate():.2%} ({rec.purchases}件)"
        console.print(msg)
    if result.errors:
        console.print(f"\n[yellow]{len(result.errors)}行をスキップしました:[/yellow]")
        for e in result.errors:
            console.print(f"  [red]・{e}[/red]")


@app.command(name="sync-ga4")
def sync_ga4(
    days: int = typer.Option(28, "--days", help="取得対象期間 (直近N日)"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="取得結果の表示のみ (記録しない)"
    ),
):
    """GA4から動画別の流入・購入データを自動取得して実績に記録する.

    計測リンクの utm_campaign (svf_xxxxxx) をキーに、セッション数・購入数・
    売上を動画単位で取得する。記録時は動画ごとに quality (good/bad) を
    人間が判定する (自動では記録しない)。
    """
    from rich.prompt import Prompt

    from svf.integrations.ga4 import fetch_video_traffic
    from svf.pipeline import FEEDBACK_DIR

    pipeline = Pipeline()
    settings = pipeline.settings
    if not settings.ga4_property_id:
        console.print(
            "[red]GA4_PROPERTY_ID が未設定です。[/red] .env に設定してください "
            "(GA4管理画面 > プロパティ設定 に表示される数字)。"
        )
        raise typer.Exit(1)

    console.print(f"GA4 (property {settings.ga4_property_id}) から直近{days}日を取得中...")
    rows = fetch_video_traffic(
        settings.ga4_property_id, days=days,
        credentials_path=settings.google_credentials_path,
    )
    if not rows:
        console.print("svf_ で始まる utm_campaign のトラフィックが見つかりませんでした。")
        return

    # short_code → 台本の対応付け
    scripts = pipeline._load_all_scripts()
    by_code = {s.short_code: s for s in scripts.values() if s.short_code}

    table = Table(title=f"GA4 取得結果 (直近{days}日)")
    table.add_column("動画")
    table.add_column("PF")
    table.add_column("セッション", justify="right")
    table.add_column("購入", justify="right")
    table.add_column("売上", justify="right")
    matched = []
    for r in rows:
        script = by_code.get(r.short_code)
        name = script.title[:30] if script else f"(不明: svf_{r.short_code})"
        table.add_row(
            name, r.platform or r.raw_source,
            f"{r.sessions:,}", f"{r.purchases:,}", f"{r.revenue:,.0f}",
        )
        if script and r.platform:
            matched.append((script, r))
    console.print(table)

    if dry_run:
        console.print("(--dry-run のため記録していません)")
        return
    if not matched:
        console.print("[yellow]台本と対応付けできたデータがありませんでした。[/yellow]")
        return

    console.print(
        "\n動画ごとに quality を判定してください。数値が良くても炎上・釣りで"
        "伸びただけなら bad にします。 (g)ood / (b)ad / (s)kip"
    )
    recorded = 0
    for script, r in matched:
        console.print(
            f"\n[cyan]{script.title}[/cyan] ({r.platform}) "
            f"セッション{r.sessions:,} / 購入{r.purchases:,}"
        )
        answer = Prompt.ask("  quality", choices=["g", "b", "s"], default="g")
        if answer == "s":
            continue
        quality = "good" if answer == "g" else "bad"
        try:
            pipeline.report_performance(
                script.script_id, r.platform, quality,
                clicks=r.sessions, purchases=r.purchases, revenue=r.revenue,
                quality_notes="GA4自動同期",
            )
            recorded += 1
        except RuntimeError as e:
            console.print(f"  [yellow]スキップ: {e}[/yellow]")
    console.print(f"\n[green]{recorded}件を記録しました。[/green] `svf leaderboard` で確認できます。")


@app.command()
def leaderboard():
    """実績 (good評価のみ) から見えている、スタイルごとの「勝ちパターン」一覧."""
    stats = Pipeline().leaderboard()
    if not stats:
        console.print("まだ実績データがありません。`svf publish` → `svf report` で記録してください。")
        return
    table = Table(title="パターン別 実績 (good評価のみで平均を算出 / 購入データ優先で並び替え)")
    table.add_column("スタイル")
    table.add_column("パターン")
    table.add_column("購入率", justify="right")
    table.add_column("購入数", justify="right")
    table.add_column("エンゲージ率", justify="right")
    table.add_column("good/bad", justify="right")
    for s in stats:
        table.add_row(
            s.style,
            s.pattern_tag,
            f"{s.avg_conversion_rate:.2%}" if s.total_purchases else "-",
            str(s.total_purchases) if s.total_purchases else "-",
            f"{s.avg_engagement_rate:.2%}",
            f"{s.good_count}/{s.bad_count}",
        )
    console.print(table)


@app.command()
def run(
    style: str = typer.Option(..., "--style", "-s", help="スタイルプリセット名"),
    query: str = typer.Option("", "--query", "-q", help="トレンド検索キーワード"),
    count: int = typer.Option(3, "--count", "-c", help="量産する本数"),
    platform: List[str] = typer.Option(["youtube"], "--platform", "-p"),
    limit: int = typer.Option(20, "--limit", "-n"),
    tts: str = typer.Option("edge", "--tts"),
    brief: str = typer.Option("", "--brief", "-b", help="動画の雰囲気・方向性の指定 (任意)"),
    must_text: List[str] = typer.Option(
        [], "--must-text", "-t", help="動画に必ず入れるテキスト (複数指定可)"
    ),
):
    """収集→curate(対話)→分析→台本→動画を一括実行する."""
    results = Pipeline().run_all(
        list(platform), query, style, count, limit=limit, tts_provider=tts,
        brief=brief, must_texts=list(must_text),
    )
    console.print(f"\n[bold green]{len(results)}本の動画が完成しました[/bold green]")
    for r in results:
        console.print(f"  ・{r.video_path}")


@app.command()
def styles():
    """利用可能なスタイルプリセットの一覧."""
    table = Table(title="スタイルプリセット")
    table.add_column("名前")
    table.add_column("説明", max_width=60)
    table.add_column("商品の見せ方")
    for name in list_styles():
        s = load_style(name)
        table.add_row(name, s.display_name or s.description[:60], s.product_placement)
    console.print(table)


if __name__ == "__main__":
    app()
