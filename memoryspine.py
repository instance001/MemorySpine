#!/usr/bin/env python3
"""
MemorySpine v0.1 - minimal, boring, one-button ChatGPT export parser.

- Input:  ChatGPT data export (zip), or a conversations.json file, or a folder containing it
- Output: Markdown files and a simple index under ./output/

This script is intentionally simple and dependency-free.
"""

import argparse
import json
import os
import sys
import zipfile
from io import TextIOWrapper
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

def find_conversations_json(path: Path) -> Tuple[Optional[Path], Optional[zipfile.ZipFile]]:
    """
    Try to locate conversations.json from:
    - a direct .json file
    - a directory containing it (any depth)
    - a zip file containing it at any depth

    Returns (path_or_virtual, zip_ref)
    If zip_ref is not None, the first element is a pseudo-path within the zip.
    """
    if not path.exists():
        print(f"[ERROR] Input path does not exist: {path}", file=sys.stderr)
        return None, None

    # Direct JSON file
    if path.is_file() and path.suffix.lower() == ".json":
        return path, None

    # Directory search
    if path.is_dir():
        for root, _, files in os.walk(path):
            if "conversations.json" in files:
                return Path(root) / "conversations.json", None
        print(f"[ERROR] No conversations.json found under directory: {path}", file=sys.stderr)
        return None, None

    # Zip file
    if path.is_file() and path.suffix.lower() == ".zip":
        try:
            zf = zipfile.ZipFile(path, "r")
        except zipfile.BadZipFile:
            print(f"[ERROR] Not a valid zip file: {path}", file=sys.stderr)
            return None, None

        # Try to find conversations.json anywhere in the archive
        for name in zf.namelist():
            if name.endswith("conversations.json"):
                return Path(name), zf

        print(f"[ERROR] No conversations.json found inside zip: {path}", file=sys.stderr)
        zf.close()
        return None, None

    print(f"[ERROR] Unsupported input path type: {path}", file=sys.stderr)
    return None, None

def load_conversations(json_path: Path, zf: Optional[zipfile.ZipFile]) -> List[Dict[str, Any]]:
    """Load the conversations JSON either from disk or from a zip."""
    if zf is None:
        with json_path.open("r", encoding="utf-8-sig") as f:
            return json.load(f)
    else:
        with zf.open(str(json_path), "r") as raw:
            f = TextIOWrapper(raw, encoding="utf-8-sig")
            return json.load(f)

def safe_slug(text: str, max_len: int = 80) -> str:
    """Generate filesystem-friendly slug from a title."""
    slug = "".join(c if c.isalnum() or c in "-_ " else "_" for c in text)
    slug = "_".join(slug.split())  # collapse whitespace to underscores
    if len(slug) > max_len:
        slug = slug[:max_len]
    return slug or "untitled"

def extract_messages(conv: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract a linear list of messages from a ChatGPT export conversation.
    This is a best-effort flattening that works with the public export format as of 2024.

    Fallback behaviour: if structure is unknown, return an empty list and let the caller
    handle raw JSON dumping.
    """
    mapping = conv.get("mapping")
    if not isinstance(mapping, dict):
        return []

    # Many exports have a "current_node" pointing to the last message; walk backwards via parents
    current_id = conv.get("current_node")
    if current_id and current_id in mapping:
        order = []
        seen = set()
        node_id = current_id
        while node_id and node_id not in seen and node_id in mapping:
            seen.add(node_id)
            order.append(node_id)
            node = mapping[node_id]
            parent = node.get("parent")
            node_id = parent if isinstance(parent, str) else None
        order.reverse()
        node_ids = order
    else:
        # Fallback: sort all nodes that have a message by create_time if present
        def node_key(item):
            _id, node = item
            msg = node.get("message") or {}
            meta = msg.get("metadata") or {}
            ts = meta.get("timestamp") or msg.get("create_time") or 0
            try:
                return float(ts)
            except Exception:
                return 0.0

        node_ids = [nid for nid, node in sorted(mapping.items(), key=node_key)]

    messages: List[Dict[str, Any]] = []
    for node_id in node_ids:
        node = mapping.get(node_id, {})
        msg = node.get("message")
        if not msg:
            continue
        author = (msg.get("author") or {}).get("role") or "unknown"
        content = msg.get("content") or {}
        parts = content.get("parts") or []
        text = "\n\n".join(str(p) for p in parts if p is not None)
        if not text.strip():
            continue
        meta = msg.get("metadata") or {}
        ts = meta.get("timestamp") or msg.get("create_time")
        # Try to normalise timestamp
        dt: Optional[datetime] = None
        if ts is not None:
            try:
                dt = datetime.fromtimestamp(float(ts))
            except Exception:
                try:
                    dt = datetime.fromisoformat(str(ts))
                except Exception:
                    dt = None
        messages.append(
            {
                "role": author,
                "text": text,
                "timestamp": dt.isoformat() if dt else None,
            }
        )

    return messages

def write_markdown(conv: Dict[str, Any], messages: List[Dict[str, Any]], out_dir: Path) -> None:
    """Write a single conversation to a markdown file."""
    title = conv.get("title") or "Untitled Conversation"
    create_time = conv.get("create_time")
    try:
        dt = datetime.fromtimestamp(float(create_time)) if create_time else None
    except Exception:
        dt = None

    dt_str = dt.isoformat(timespec="seconds") if dt else "unknown"
    slug = safe_slug(title)
    filename = f"{dt_str.replace(':', '-')}_{slug}.md"
    path = out_dir / filename
    raw_json_path = path.with_suffix(".raw.json")

    lines: List[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- ID: `{conv.get('id', 'unknown')}`")
    lines.append(f"- Created: {dt_str}")
    model_slug = conv.get("create_model") or conv.get("model") or "unknown"
    lines.append(f"- Model: `{model_slug}`")
    lines.append("")

    if not messages:
        lines.append("> ⚠️ Unable to parse messages from this conversation format.")
        lines.append("> Raw JSON for this conversation is stored alongside this file.")
        raw_json_path.parent.mkdir(parents=True, exist_ok=True)
        with raw_json_path.open("w", encoding="utf-8") as f:
            json.dump(conv, f, ensure_ascii=False, indent=2)
    else:
        for msg in messages:
            role = msg.get("role", "unknown")
            ts = msg.get("timestamp") or "unknown time"
            text = msg.get("text", "").strip()
            lines.append(f"---")
            lines.append(f"**{role}** · _{ts}_")
            lines.append("")
            lines.append(text)
            lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def write_index(conversations: List[Dict[str, Any]], out_dir: Path) -> None:
    """Write a simple index.md file linking all conversations."""
    index_path = out_dir / "index.md"
    lines: List[str] = []
    lines.append("# MemorySpine Index")
    lines.append("")
    lines.append("This index was generated by MemorySpine v0.1 from a ChatGPT data export.")
    lines.append("")

    entries = []
    for conv in conversations:
        title = conv.get("title") or "Untitled Conversation"
        create_time = conv.get("create_time")
        try:
            dt = datetime.fromtimestamp(float(create_time)) if create_time else None
        except Exception:
            dt = None
        dt_str = dt.isoformat(timespec="seconds") if dt else "unknown"
        slug = safe_slug(title)
        filename = f"{dt_str.replace(':', '-')}_{slug}.md"
        entries.append((dt_str, title, filename))

    # Sort by datetime string (works reasonably well even with "unknown")
    entries.sort(key=lambda e: e[0])

    for dt_str, title, filename in entries:
        lines.append(f"- `{dt_str}` · [{title}](./{filename})")

    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="MemorySpine v0.1 - parse ChatGPT export into local markdown spine."
    )
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        default="data_export.zip",
        help="Path to ChatGPT export zip, conversations.json file, or folder containing it.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="output",
        help="Directory to write markdown files and index into (default: ./output).",
    )

    args = parser.parse_args(argv)
    in_path = Path(args.input).expanduser().resolve()
    out_dir = Path(args.output).expanduser().resolve()

    json_path, zf = find_conversations_json(in_path)
    if json_path is None:
        return 1

    try:
        conversations = load_conversations(json_path, zf)
    finally:
        if zf is not None:
            zf.close()

    if not isinstance(conversations, list):
        print("[ERROR] conversations.json did not contain a list.", file=sys.stderr)
        return 1

    conv_out_dir = out_dir
    conv_out_dir.mkdir(parents=True, exist_ok=True)

    for conv in conversations:
        messages = extract_messages(conv)
        write_markdown(conv, messages, conv_out_dir)

    write_index(conversations, conv_out_dir)

    print(f"[OK] Wrote markdown spine for {len(conversations)} conversations to: {conv_out_dir}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
