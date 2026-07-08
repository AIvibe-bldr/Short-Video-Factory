"""Short Video Factory CLI.

使い方:
  svf research --platform youtube --query "スキンケア"   # トレンド収集
  svf curate                                             # 参考にしてよいか人間が判定 (good/bad)
  svf analyze                                            # 要点抽出 (good判定のみ使用)
  svf script --style kawaii_presenter --count 3          # 台本生成 (8割exploit/2割explore)
  svf produce data/scripts/xxx.json                      # 動画生成
  svf publish <script_id> --decision published           # 投稿するか人間が最終決定
  svf report  <script_id> --platform youtube --quality good --views 12000 --likes 300
                                                          # 投稿後の実績を記録 (次の台本生成に反映)
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

from svf.config import list_styles, load_style
from svf.pipeline import Pipeline, SCRIPTS_DIR, TRENDS_DIR
from svf.script.generator import load_script

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


@app.command()
def script(
    style: str = typer.Option(..., "--style", "-s", help="スタイルプリセット名"),
    count: int = typer.Option(1, "--count", "-c", help="生成する台本の本数"),
):
    """トレンド × 商品 × スタイルで台本を生成する (Claude API使用).

    実績データがあれば約8割は勝ちパターンを踏襲 (exploit)、
    約2割はあえて違う構成を試す (explore)。
    """
    scripts, paths = Pipeline().write_scripts(style, count=count)
    for s, p in zip(scripts, paths):
        tag = "[magenta]explore[/magenta]" if s.variant == "explore" else "[blue]exploit[/blue]"
        console.print(f"[bold cyan]{s.title}[/bold cyan]  ({tag} / {s.pattern_tag})")
        console.print(f"  フック: {s.hook}")
        console.print(f"  シーン数: {len(s.scenes)} / 尺: {s.total_seconds}秒")
        console.print(f"  [green]保存:[/green] {p}\n")


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
    url: str = typer.Option("", "--url", help="投稿先URL (任意)"),
    notes: str = typer.Option("", "--notes", help="quality判定の理由 (任意)"),
):
    """投稿後の実績を記録する。bad評価の実績は次回の勝ちパターン強化から除外される."""
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
        posted_url=url,
        quality_notes=notes,
    )
    console.print(
        f"[green]記録しました[/green] エンゲージメント率: {record.engagement_rate():.2%} "
        f"(quality: {quality})"
    )


@app.command()
def leaderboard():
    """実績 (good評価のみ) から見えている、スタイルごとの「勝ちパターン」一覧."""
    stats = Pipeline().leaderboard()
    if not stats:
        console.print("まだ実績データがありません。`svf publish` → `svf report` で記録してください。")
        return
    table = Table(title="パターン別 実績 (good評価のみで平均を算出)")
    table.add_column("スタイル")
    table.add_column("パターン")
    table.add_column("平均エンゲージメント率", justify="right")
    table.add_column("good/bad件数", justify="right")
    for s in stats:
        table.add_row(
            s.style, s.pattern_tag, f"{s.avg_engagement_rate:.2%}",
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
):
    """収集→分析→台本→動画を一括実行する."""
    results = Pipeline().run_all(
        list(platform), query, style, count, limit=limit, tts_provider=tts
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
