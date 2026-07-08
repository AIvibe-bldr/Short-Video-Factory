"""収集したトレンド動画を分析に使う前に、人間が参考にしてよいか判定する.

インプレッション数・再生数だけを基準に「勝ちパターン」を学習すると、
炎上煽り・釣りタイトル・誤情報のような動画が構成として強化されてしまう。
これを防ぐため、トレンド分析にかける前に必ずこの工程を通し、
動画ごとに good (参考にしてよい) / bad (参考にしない) を人間が判定する。
"""

from __future__ import annotations

from rich.console import Console
from rich.prompt import Prompt

from svf.models import TrendItem

console = Console()


def curate_interactive(items: list[TrendItem]) -> list[TrendItem]:
    """1件ずつ表示し、人間に good/bad を判定させる.

    g: good (参考にしてよい) / b: bad (参考にしない・理由を記録) /
    s: skip (今回は判定せず未評価のまま) / q: quit (中断してここまでを保存)
    """
    console.print(
        f"[bold]{len(items)}件のトレンド動画を確認します。[/bold] "
        "内容を見て、次の台本作りの参考にしてよいか判定してください。\n"
        "(g)ood / (b)ad / (s)kip / (q)uit\n"
    )
    for idx, item in enumerate(items, start=1):
        console.print(
            f"[{idx}/{len(items)}] [cyan]{item.platform}[/cyan]  "
            f"再生数 {item.view_count:,} / いいね {item.like_count:,} / "
            f"コメント {item.comment_count:,}"
        )
        console.print(f"  タイトル: {item.title}")
        if item.description:
            console.print(f"  説明: {item.description[:150]}")
        if item.transcript:
            console.print(f"  字幕抜粋: {item.transcript[:150]}")
        if item.hashtags:
            console.print(f"  タグ: {' '.join('#' + h for h in item.hashtags[:8])}")
        console.print(f"  URL: {item.url}")

        answer = Prompt.ask("  評価", choices=["g", "b", "s", "q"], default="g")
        if answer == "q":
            console.print("[yellow]中断しました。ここまでの評価を保存します。[/yellow]")
            break
        if answer == "s":
            console.print()
            continue
        item.human_rating = "good" if answer == "g" else "bad"
        if item.human_rating == "bad":
            item.human_notes = Prompt.ask(
                "  bad判定の理由 (炎上煽り・誤情報・悪目立ちなど。空欄可)", default=""
            )
        console.print()
    return items
