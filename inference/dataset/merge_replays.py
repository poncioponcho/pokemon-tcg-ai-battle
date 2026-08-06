# -*- coding: utf-8 -*-
"""合并全部 replay 源 → 单一规范归档 all_replays.jsonl.zst（去重 by episode_id）。

数据源（只读）:
  1. inference/leaderboard_replay/raw/            leaderboard 爬取（episode-*-replay.json）
  2. inference/leaderboard_replay/archive/official_bulk_2026-07-30.jsonl.zst  官方数据集

输出:
  inference/leaderboard_replay/archive/all_replays.jsonl.zst
  inference/leaderboard_replay/archive/all_replays.jsonl.zst.manifest.json

同一 episode_id 多源出现时优先 raw（更新的爬取版本），并在 manifest 记录冲突。
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import zstandard as zstd

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / 'inference' / 'leaderboard_replay' / 'raw'
BULK = REPO / 'inference' / 'leaderboard_replay' / 'archive' / 'official_bulk_2026-07-30.jsonl.zst'
OUT = REPO / 'inference' / 'leaderboard_replay' / 'archive' / 'all_replays.jsonl.zst'
MANIFEST = OUT.with_suffix(OUT.suffix + '.manifest.json')

SCHEMA = 'ptcg-replay-jsonl-zstd-v2'


def _write_record(writer, episode_id: str, file: str, raw_json: str) -> int:
    prefix = (
        b'{"episode_id":'
        + json.dumps(episode_id, ensure_ascii=False).encode('utf-8')
        + b',"file":'
        + json.dumps(file, ensure_ascii=False).encode('utf-8')
        + b',"raw_json":'
    )
    encoded = json.dumps(raw_json, ensure_ascii=False).encode('utf-8')
    writer.write(prefix)
    writer.write(encoded)
    writer.write(b'}\n')
    return len(raw_json)


def main():
    t0 = time.time()
    seen: dict[str, str] = {}
    conflicts: list[tuple[str, str, str]] = []
    total_bytes = 0
    n_raw = 0
    n_bulk = 0

    cctx = zstd.ZstdCompressor(level=5)
    with cctx.stream_writer(open(OUT, 'wb')) as w:        # ---- 源 1: raw 目录（优先） ----
        files = sorted(RAW.glob('episode-*-replay.json'))
        print(f'raw dir: {len(files)} files')
        for p in files:
            ep = p.name.split('-')[1]
            try:
                raw = p.read_text(encoding='utf-8')
                json.loads(raw)  # 完整性校验
            except Exception as e:
                print(f'  [SKIP] {p.name}: {e}')
                continue
            if ep in seen:
                conflicts.append((ep, seen[ep], p.name))
                continue
            seen[ep] = p.name
            n_raw += 1
            total_bytes += _write_record(w, ep, p.name, raw)

        # ---- 源 2: 官方 bulk（仅补缺失） ----
        if BULK.exists():
            with zstd.open(BULK, 'rt') as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ep = str(rec.get('episode_id', ''))
                    if not ep or ep in seen:
                        continue
                    seen[ep] = rec.get('file', f'{ep}.json')
                    n_bulk += 1
                    total_bytes += _write_record(
                        w, ep, rec.get('file', f'{ep}.json'), rec.get('raw_json', ''))

    manifest = {
        'schema': SCHEMA,
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%S%z', time.gmtime()),
        'source_raw_dir': str(RAW),
        'source_bulk': str(BULK) if BULK.exists() else None,
        'records': len(seen),
        'from_raw': n_raw,
        'from_bulk': n_bulk,
        'conflicts': len(conflicts),
        'conflict_examples': conflicts[:10],
        'raw_json_bytes': total_bytes,
        'compressed_bytes': OUT.stat().st_size,
        'compression_ratio': round(total_bytes / OUT.stat().st_size, 3),
        'seconds': round(time.time() - t0, 1),
    }
    with open(MANIFEST, 'w') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(json.dumps(manifest, ensure_ascii=False))
    print(f'done: {len(seen)} episodes -> {OUT} in {manifest["seconds"]}s')


if __name__ == '__main__':
    main()
