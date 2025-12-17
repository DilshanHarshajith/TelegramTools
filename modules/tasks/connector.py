import os
import csv
import itertools
from typing import Dict, List, Set, Any

from modules.utils.auth import connect_client
from modules.utils.output import info, success, warning, error
from config import OUTPUT_DIR


def get_args(parser):
    """
    CLI arguments for the infra_reuse_hunter module.
    """
    parser.add_argument(
        "--groups",
        nargs="*",
        help="Telegram group/channel links or usernames to analyze for shared infrastructure",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="Optional start time filter for messages (e.g. '2024-01-01' or '30d')",
    )
    parser.add_argument(
        "--until",
        type=str,
        default=None,
        help="Optional end time filter for messages (e.g. '2024-12-31')",
    )
    parser.add_argument(
        "--max-messages-per-chat",
        type=int,
        default=0,
        help="Maximum number of messages to scan per chat (0 = no limit)",
    )
    parser.add_argument(
        "--min-domain-overlap",
        type=int,
        default=1,
        help="Minimum number of shared domains required to report a channel pair",
    )
    parser.add_argument(
        "--min-user-overlap",
        type=int,
        default=1,
        help="Minimum number of shared users required to report a channel pair",
    )
    parser.add_argument(
        "--export-graphml",
        action="store_true",
        help="Export a GraphML file representing channels and shared infrastructure",
    )


async def run(args):
    """
    Entry point for the infra_reuse_hunter module.

    High-level steps (MVP):
      1. Connect to Telegram client.
      2. For each group/channel, collect basic infrastructure data (domains, users, bots, files).
      3. Compute pairwise overlaps between channels.
      4. Write summary CSVs (and optional graph export in future iterations).
    """
    groups = args.groups
    if not groups:
        error("No groups provided. Use --groups to specify channels or a file parser upstream.")
        return

    client = await connect_client()
    module_output = os.path.join(OUTPUT_DIR, "infra_reuse_hunter")
    os.makedirs(module_output, exist_ok=True)

    per_channel_infra: Dict[str, Dict[str, Set[str]]] = {}

    try:
        for group in groups:
            info(f"Collecting infrastructure for: {group}")
            channel_key = _normalize_group_name(group)
            infra = await _collect_channel_infra(client, group, args, module_output)
            per_channel_infra[channel_key] = infra

        if len(per_channel_infra) < 2:
            warning("Need at least two channels to compute overlaps.")
            return

        overlaps = _compute_pairwise_overlaps(per_channel_infra)
        if not overlaps:
            warning("No overlaps found with current thresholds.")
            return

        summary_csv = os.path.join(module_output, "infra_overlaps.csv")
        _write_overlaps_csv(summary_csv, overlaps)
        success(f"Saved {len(overlaps)} overlap record(s) to {summary_csv}")

        # Placeholder for optional future GraphML export
        if args.export_graphml:
            graph_path = os.path.join(module_output, "infra_graph.graphml")
            _write_graphml_placeholder(graph_path)
            success(f"GraphML export placeholder created at {graph_path}")

    except KeyboardInterrupt:
        warning("\nUser interrupted, stopping infra_reuse_hunter...")
    finally:
        try:
            await client.disconnect()
        except Exception as exc:
            warning(f"Error disconnecting client: {exc}")


async def _collect_channel_infra(client: Any, group: str, args: Any, module_output: str) -> Dict[str, Set[str]]:
    """
    Collect basic infrastructure for a single channel/group.

    This is a skeleton implementation:
      - In the MVP, this function should:
          * iterate over recent messages (respecting --since/--until and --max-messages-per-chat),
          * extract domains/URLs from message text and media,
          * track seen users (including bots/admins when available),
          * hash media/files for reuse detection.
      - For now, it returns empty sets as a structural placeholder.
    """
    # TODO: Implement real collection logic using Telethon once the design is finalized.
    # Keeping the structure here so that overlap computation and CSV writing already work.
    infra: Dict[str, Set[str]] = {
        "domains": set(),
        "users": set(),
        "bots": set(),
        "files": set(),
    }
    return infra


def _compute_pairwise_overlaps(
    per_channel_infra: Dict[str, Dict[str, Set[str]]]
) -> List[Dict[str, Any]]:
    """
    Compute pairwise overlaps between channels based on collected infrastructure.

    For now, overlap counts are simple set intersections:
      - shared_domains
      - shared_users
      - shared_bots
      - shared_files
    A more advanced version can add similarity scores (Jaccard, weighted scores, etc.).
    """
    results: List[Dict[str, Any]] = []

    for (chan_a, infra_a), (chan_b, infra_b) in itertools.combinations(per_channel_infra.items(), 2):
        domains_a = infra_a.get("domains", set())
        domains_b = infra_b.get("domains", set())
        users_a = infra_a.get("users", set())
        users_b = infra_b.get("users", set())
        bots_a = infra_a.get("bots", set())
        bots_b = infra_b.get("bots", set())
        files_a = infra_a.get("files", set())
        files_b = infra_b.get("files", set())

        shared_domains = domains_a & domains_b
        shared_users = users_a & users_b
        shared_bots = bots_a & bots_b
        shared_files = files_a & files_b

        result = {
            "channel_a": chan_a,
            "channel_b": chan_b,
            "shared_domains_count": len(shared_domains),
            "shared_users_count": len(shared_users),
            "shared_bots_count": len(shared_bots),
            "shared_files_count": len(shared_files),
            # Placeholders for future similarity scores:
            "score_domains_jaccard": _safe_jaccard(domains_a, domains_b),
            "score_users_jaccard": _safe_jaccard(users_a, users_b),
        }
        results.append(result)

    return results


def _write_overlaps_csv(csv_path: str, overlaps: List[Dict[str, Any]]) -> None:
    """
    Write pairwise overlap records to a CSV file.
    """
    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)

    with open(csv_path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "channel_a",
                "channel_b",
                "shared_domains_count",
                "shared_users_count",
                "shared_bots_count",
                "shared_files_count",
                "score_domains_jaccard",
                "score_users_jaccard",
            ]
        )

        for row in overlaps:
            writer.writerow(
                [
                    row.get("channel_a", ""),
                    row.get("channel_b", ""),
                    row.get("shared_domains_count", 0),
                    row.get("shared_users_count", 0),
                    row.get("shared_bots_count", 0),
                    row.get("shared_files_count", 0),
                    f"{row.get('score_domains_jaccard', 0.0):.4f}",
                    f"{row.get('score_users_jaccard', 0.0):.4f}",
                ]
            )


def _write_graphml_placeholder(path: str) -> None:
    """
    Minimal placeholder GraphML writer.

    This keeps the CLI flag working without committing to a concrete
    graph schema yet. Replace with a real implementation later.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    content = """<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <graph id="G" edgedefault="undirected">
    <!-- TODO: Populate with channels and infrastructure nodes -->
  </graph>
</graphml>
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _normalize_group_name(value: str) -> str:
    """
    Normalize a group/channel identifier into a filesystem/CSV-friendly key.
    """
    return value.replace("/", "_").strip()


def _safe_jaccard(a: Set[str], b: Set[str]) -> float:
    """
    Compute Jaccard similarity between two sets, handling empty sets safely.
    """
    if not a and not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    if union == 0:
        return 0.0
    return intersection / union


