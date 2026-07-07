"""Short Video Factory CLI.

使い方:
  svf research --platform youtube --query "スキンケア"   # トレンド収集
  svf analyze                                            # 要点抽出
  svf script --style kawaii_presenter --count 3          # 台本生成
  svf produce data/scripts/xxx.json                      # 動画生成
  svf run --style hands_only --query "コーヒー" --count 5 # 一括実行
  svf styles                                             # スタイル一覧
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table

from svf.config import list_styles, load_style
from svf.pipeline import Pipeline, SCRIPTS_DIR
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
    """トレンド × 商品 × スタイルで台本を生成する (Claude API使用)."""
    scripts, paths = Pipeline().write_scripts(style, count=count)
    for s, p in zip(scripts, paths):
        console.print(f"[bold cyan]{s.title}[/bold cyan]")
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
