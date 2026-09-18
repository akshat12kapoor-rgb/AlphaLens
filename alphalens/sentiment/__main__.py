"""
Command line for the sentiment tool.

    python -m alphalens.sentiment                     # the sample feed
    python -m alphalens.sentiment path/to/feed.txt
    python -m alphalens.sentiment --ticker TSLA --verbose
    python -m alphalens.sentiment --text "Nvidia beats estimates but warns of weak demand"
    python -m alphalens.sentiment --live AAPL         # live Yahoo headlines
"""
from __future__ import annotations

import argparse
import json
import sys

from alphalens.sentiment import feed as feed_module
from alphalens.sentiment.scoring import score_headlines, score_text

BAR_WIDTH = 21  # odd, so zero sits on the centre column


def bar(score: float) -> str:
    """A small text gauge from -1 (left) to +1 (right)."""
    half = BAR_WIDTH // 2
    offset = max(-half, min(half, round(score * half)))
    cells = ["-"] * BAR_WIDTH
    cells[half] = "|"
    cells[half + offset] = "#" if offset else "|"
    return "".join(cells)


def report(sentiments: dict, verbose: bool) -> None:
    for ticker in sorted(sentiments):
        s = sentiments[ticker]
        counts = s.counts
        print(f"\n{ticker}  {s.label}  (score {s.mean:+.3f}, confidence {s.confidence})")
        print(f"  {bar(s.mean)}")
        print(f"  {len(s.scores)} headlines: {counts['bullish']} bullish / "
              f"{counts['neutral']} neutral / {counts['bearish']} bearish")
        print(f"  momentum: {s.momentum:+.3f} ({s.momentum_word})")
        if verbose:
            print("  daily:")
            for day, value in s.by_day.items():
                print(f"    {day}  {value:+.3f}")
            print("  headlines:")
            for score in s.scores:
                print(f"    [{score.score:+.3f} {score.label:<7}] {score.text}")
                print(f"      {score.terms}")


def as_json(sentiments: dict) -> str:
    return json.dumps({
        ticker: {"score": round(s.mean, 4), "label": s.label, "momentum": s.momentum,
                 "confidence": s.confidence, "counts": s.counts,
                 "headline_count": len(s.scores),
                 "by_day": {str(day): value for day, value in s.by_day.items()}}
        for ticker, s in sorted(sentiments.items())}, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m alphalens.sentiment",
        description="Score financial headlines with a finance-tuned lexicon.")
    parser.add_argument("feed", nargs="?", help="feed file (default: the sample feed)")
    parser.add_argument("--live", metavar="TICKER", help="score live Yahoo headlines")
    parser.add_argument("--text", help="score one headline and exit")
    parser.add_argument("--ticker", help="restrict the report to one ticker")
    parser.add_argument("--verbose", action="store_true", help="show daily tone and every headline")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    if args.text:
        score = score_text(args.text)
        print(f"{score.score:+.4f}  {score.label}  (raw {score.raw:+.2f})")
        print(f"matched: {score.terms}")
        return 0

    try:
        if args.live:
            from alphalens.data import yahoo
            stories = yahoo.fetch_news(args.live)
            if not stories:
                print(f"No recent headlines for {args.live}.", file=sys.stderr)
                return 1
            headlines = [feed_module.Headline(date=s.day, ticker=args.live.upper(),
                                              text=s.title) for s in stories]
        elif args.feed:
            headlines = feed_module.load(args.feed)
        else:
            headlines = feed_module.sample()
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.ticker:
        headlines = feed_module.for_ticker(headlines, args.ticker)
        if not headlines:
            print(f"No headlines for {args.ticker}.", file=sys.stderr)
            return 1

    sentiments = score_headlines(headlines)
    if args.json:
        print(as_json(sentiments))
    else:
        source = args.live or args.feed or "the sample feed"
        print(f"Market sentiment from {len(headlines)} headlines in {source}")
        report(sentiments, args.verbose)
        print("\nScores range from -1 (bearish) to +1 (bullish). Sentiment is not a "
              "price forecast.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
