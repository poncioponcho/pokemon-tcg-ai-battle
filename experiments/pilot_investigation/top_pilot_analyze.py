"""top_pilot_analyze.py — 参数化行为 diff 解析器 (top_pilot_diff_plan Step2)

一套解析器通吃两边 (规格 §1: player_name 作参数, 格式零漂移):
  --source top  → top_pilot_replays/, player ∈ TARGETS (一局含两个目标选手则双边都收)
  --source ours → live_replays/, player='Daniel1547' (我们 config A 的 42 局, 重点 22 败局)
  --source probe → live_replays_probe/, player='Daniel1547' (探针 55468450; A 补丁 A3, 走 ours 通道分组)
  默认 --source all = top+ours (与 08-12 历史行为逐字节一致; --source 旗标 08-13 才补上, 此前 docstring 漂移)

每局打标四字段 (规格 §2): player / outcome(该 player 胜败) / seat / mirror_flag
镜像局 (TeamNames 双同名) → flag, 不进 us-vs-them 分组 (#132 教训)
事件流: #132 新鲜窗口规则 (lg != prev_lg), 单侧视角

阶段:
  --stage explore : 事件类型分布 + 每类型 sample payload (先学词汇表再定维度映射)
  --stage diff    : 6 维度聚合, 出 [他们胜 vs 我们败] + [他们胜 vs 他们负] 两表 (规格 §3)
产物: experiments/runs/top_pilot_diff.json + stdout
删 raw: --delete-raw (只在 diff 产物确认后手动加; 方案护栏)
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
sys.path.insert(0, str(PROJ / 'experiments'))
import arena_runner as ar  # noqa: E402

TARGETS = ['Sixth Sense', 'Dipam Chakraborty', 'やる気元気ミワハルキ']
DIRS = {'top': ('experiments/runs/top_pilot_replays', TARGETS),
        'ours': ('experiments/runs/live_replays', ['Daniel1547']),
        # 探针 replay 的我方 TeamName=可抽奖的冰棒 (08-13 实证: 显示名已改;
        # episode json 的 opp 字段与 replay TeamNames 交叉一致)。双名并列防名漂移。
        'probe': ('experiments/runs/live_replays_probe', ['Daniel1547', '可抽奖的冰棒'])}

mod = ar.load_module(PROJ / 'experiments/runs/_configA/main_configA_pristine.py')
CT = mod.card_table


def pval(cid):
    e = CT.get(cid)
    return (3 if e.megaEx else (2 if e.ex else 1)) if e else None


def name(cid):
    e = CT.get(cid)
    return e.name if e else str(cid)


def parse(fp, player):
    """单侧视角解析. 返回打标 + 事件度量; 座位找不到返回 None.

    情境维度 (08-12 二刀):
      Boss's Orders(1182): type4=打出; 同窗口内对手 5→4 移动=gust 目标 (pending 配对)
      能量挂载 type11: serial→area 追踪器定 cardIdTarget 在 active(4)/bench(5)
      retreat 仪器修正: 4→5 不存在; 真实签名=5→4 (bench→active)
      switch 三分解 (08-12 三刀): postko=active被KO后强制升场(非决策) /
        gust=对手Boss拉的受害者(非决策) / vol=自愿换位·retreat(真决策, 另记pre-KO)
    """
    d = json.load(open(fp))
    teams = d.get('info', {}).get('TeamNames') or []
    mirror = len(teams) == 2 and teams[0] == teams[1]
    us = next((i for i, t in enumerate(teams) if t == player), None)
    if us is None:
        return None
    them = 1 - us
    rewards = d.get('rewards') or []
    g = {'player': player, 'seat': us, 'mirror': mirror,
         'outcome': (rewards[us] if us < len(rewards) else None),
         'opp': teams[them] if len(teams) == 2 else '?',
         'steps': len(d['steps']),
         'events_type': Counter(),        # explore 用: 全类型计数
         'type_samples': defaultdict(list),
         # diff 度量 (按绝对 side 索引, agg 用 g['seat'] 取 us 侧)
         'atk': [0, 0], 'prizes': [0, 0],
         'switch': [0, 0],                # 5→4 (bench→active: 升场/换位/gust)
         'sw_postko': [0, 0],             # 5→4 分解: active被KO后强制升场 (非决策)
         'sw_gust': [0, 0],               # 5→4 分解: 对手Boss gust 受害者 (非决策)
         'sw_vol': [0, 0],                # 5→4 分解: 自愿换位/retreat (真决策)
         'sw_vol_pre': [0, 0],            # 自愿换位中发生在首次KO/丢奖前 (setup期)
         't8': [0, 0],                    # type8 swap (active↔bench): 真·自愿换位载体
         'sw8_gust': [0, 0],              # type8 分解: 对手Boss gust 受害者 (非决策)
         'sw8_vol': [0, 0],               # type8 分解: 自愿换位/retreat (真决策)
         'sw8_vol_pre': [0, 0],           # 自愿 type8 中发生在首次KO/丢奖前
         'sw8_atk': [0, 0],               # 自愿换位后换上来的怪当回合即攻击 (换位质量)
         'hand_play': [0, 0],             # 2→4/5 (手牌打出)
         'boss': [0, 0],                  # Boss's Orders(1182) 打出次数
         'boss_tgt_pv': [[], []],         # gust 目标奖品值
         'boss_tgt_id': [[], []],         # gust 目标 cardId (676=Solrock 引擎)
         'nrg': [0, 0], 'nrg_active': [0, 0], 'nrg_bench': [0, 0],
         'nrg_pre': [0, 0], 'nrg_pre_act': [0, 0], 'nrg_pre_bench': [0, 0],  # 首次KO/丢奖前
         'ko_victim_pv': [[], []],        # 每侧 KO 的受害者奖品值序列 (=mapping 偏好)
         'ko_victim_name': [[], []],
         }
    prev = None
    last_atk = {0: None, 1: None}
    loc = {}                               # (side, serial) -> area 追踪器
    pending_boss = {0: False, 1: False}    # Boss 打出待配对 gust
    pending_ko = {0: False, 1: False}      # 该侧 active 被 KO, 下一次 5→4 = 强制升场
    pending_vol8 = {0: None, 1: None}      # 自愿 type8 换上来的 cardId, 待配对下一次攻击
    evt_i = 0                              # 事件序号 (新鲜窗口内单调)
    first_ko_i = None                      # 任一方首次 KO/丢奖 的事件序号 (防伪刀界)
    for step in d['steps']:
        if us >= len(step):
            continue
        lg = step[us].get('observation', {}).get('logs') or []
        if lg == prev:
            continue
        prev = lg
        for e in lg:
            evt_i += 1
            t = e.get('type')
            side = e.get('playerIndex')
            g['events_type'][t] += 1
            if len(g['type_samples'][t]) < 2:
                g['type_samples'][t].append({k: v for k, v in e.items()
                                             if k in ('cardId', 'fromArea', 'toArea',
                                                      'playerIndex', 'damage', 'targetId')})
            if side not in (0, 1):
                continue
            if t == 15:
                g['atk'][side] += 1
                last_atk[side] = e.get('cardId')
                if pending_vol8[side] is not None:      # 自愿换位后换上来的怪即攻击?
                    if e.get('cardId') == pending_vol8[side]:
                        g['sw8_atk'][side] += 1
                    pending_vol8[side] = None
            elif t == 4 and e.get('cardId') == 1182:
                g['boss'][side] += 1
                pending_boss[side] = True
            elif t == 8:                                # active↔bench swap: 真·自愿换位载体
                g['t8'][side] += 1
                if pending_boss[1 - side]:              # 对手 Boss gust: 我是受害者
                    g['sw8_gust'][side] += 1
                    g['boss_tgt_pv'][1 - side].append(pval(e.get('cardIdBench')))
                    g['boss_tgt_id'][1 - side].append(e.get('cardIdBench'))
                    pending_boss[1 - side] = False
                else:                                   # 自愿换位/retreat (真决策)
                    g['sw8_vol'][side] += 1
                    if first_ko_i is None:
                        g['sw8_vol_pre'][side] += 1
                    pending_vol8[side] = e.get('cardIdBench')
            elif t == 11:
                g['nrg'][side] += 1
                area = loc.get((side, e.get('serialTarget')))
                if area == 4:
                    g['nrg_active'][side] += 1
                elif area == 5:
                    g['nrg_bench'][side] += 1
                if first_ko_i is None:                     # 防伪刀: 首次KO/丢奖前
                    g['nrg_pre'][side] += 1
                    if area == 4:
                        g['nrg_pre_act'][side] += 1
                    elif area == 5:
                        g['nrg_pre_bench'][side] += 1
            elif t in (6, 7):
                fa, ta, cid = e.get('fromArea'), e.get('toArea'), e.get('cardId')
                se = e.get('serial')
                if se is not None and ta is not None:
                    loc[(side, se)] = ta
                if first_ko_i is None and ((ta == 3 and fa in (4, 5))
                                           or (fa == 6 and ta == 2)):
                    first_ko_i = evt_i
                if ta == 3 and fa in (4, 5):               # KO: 受害者=side 的cid
                    g['ko_victim_pv'][1 - side].append(pval(cid))  # 记在攻击方账上
                    g['ko_victim_name'][1 - side].append(name(cid))
                    if fa == 4:                              # active 被打死 → 强制升场待配对
                        pending_ko[side] = True
                elif fa == 6 and ta == 2:
                    g['prizes'][side] += 1
                elif fa == 5 and ta == 4:
                    g['switch'][side] += 1
                    if pending_ko[side]:                     # KO 后强制升场 (非决策)
                        g['sw_postko'][side] += 1
                        pending_ko[side] = False
                    elif pending_boss[1 - side]:             # 对手 Boss 的 gust 落点 (受害者, 非决策)
                        g['boss_tgt_pv'][1 - side].append(pval(cid))
                        g['boss_tgt_id'][1 - side].append(cid)
                        g['sw_gust'][side] += 1
                        pending_boss[1 - side] = False
                    else:                                    # 自愿换位/retreat (真决策)
                        g['sw_vol'][side] += 1
                        if first_ko_i is None:
                            g['sw_vol_pre'][side] += 1
                elif fa == 2 and ta in (4, 5):
                    g['hand_play'][side] += 1
    return g


def collect(source):
    dname, players = DIRS[source]
    games = []
    for fp in sorted((PROJ / dname).glob('*.json')):
        teams = (json.load(open(fp)).get('info', {}).get('TeamNames') or [])
        for p in players:
            if p in teams:
                g = parse(fp, p)
                if g:
                    games.append(g)
    return games


def grp_key(g, source):
    """分组标签: top 源按 (player, 胜/负); ours 源按 (us, 胜/负)."""
    o = {1: 'W', -1: 'L', 0: 'D'}.get(g['outcome'], '?')
    return ('ours' if source == 'ours' else g['player']) + '_' + o


def diff_stage(games_top, games_ours):
    def agg(gs):
        n = max(1, len(gs))
        # 数组按绝对座位索引 → 必须用 g['seat'] 取该 player 侧 (seat=1 的局直接取反会翻转)
        su = lambda k: sum(g[k][g['seat']] for g in gs)          # noqa: E731
        st = lambda k: sum(g[k][1 - g['seat']] for g in gs)      # noqa: E731
        kv = [pv for g in gs for pv in g['ko_victim_pv'][g['seat']] if pv]
        bt = [v for g in gs for v in g['boss_tgt_pv'][g['seat']] if v]
        bids = [c for g in gs for c in g['boss_tgt_id'][g['seat']] if c]
        nrg_t = su('nrg')
        pn = su('nrg_pre')
        return {
            'n': len(gs),
            'steps': round(sum(g['steps'] for g in gs) / n, 1),
            'atk_pg': round(su('atk') / n, 2),
            'prizes_pg': round(su('prizes') / n, 2),
            'opp_prizes_pg': round(st('prizes') / n, 2),
            'switch_pg': round(su('switch') / n, 2),
            'sw_postko_pg': round(su('sw_postko') / n, 2),
            'sw_gust_pg': round(su('sw_gust') / n, 2),
            'sw_vol_pg': round(su('sw_vol') / n, 2),
            'sw_vol_pre_pg': round(su('sw_vol_pre') / n, 2),
            't8_pg': round(su('t8') / n, 2),
            'sw8_gust_pg': round(su('sw8_gust') / n, 2),
            'sw8_vol_pg': round(su('sw8_vol') / n, 2),
            'sw8_vol_pre_pg': round(su('sw8_vol_pre') / n, 2),
            'sw8_atk_pg': round(su('sw8_atk') / n, 2),
            'hand_play_pg': round(su('hand_play') / n, 2),
            'boss_pg': round(su('boss') / n, 2),
            'boss_pv': round(sum(bt) / len(bt), 2) if bt else None,
            'boss_676%': round(sum(1 for c in bids if c == 676) / len(bids) * 100, 1) if bids else None,
            'nrg_pg': round(nrg_t / n, 2),
            'nrg_act%': round(su('nrg_active') / nrg_t * 100, 1) if nrg_t else None,
            'nrg_bench%': round(su('nrg_bench') / nrg_t * 100, 1) if nrg_t else None,
            'nrg_pre_n': pn,
            'pre_act%': round(su('nrg_pre_act') / pn * 100, 1) if pn else None,
            'pre_bench%': round(su('nrg_pre_bench') / pn * 100, 1) if pn else None,
            'ko_pg': round(sum(len(g['ko_victim_pv'][g['seat']]) for g in gs) / n, 2),
            'ko_victim_pv_mean': round(sum(kv) / len(kv), 2) if kv else None,
            'ko_hi_target%': round(sum(1 for v in kv if v >= 2) / len(kv) * 100, 1) if kv else None,
        }
    groups = defaultdict(list)
    for g in games_top:
        if not g['mirror']:
            groups[grp_key(g, 'top')].append(g)
    for g in games_ours:
        if not g['mirror']:
            groups[grp_key(g, 'ours')].append(g)
    table = {k: agg(v) for k, v in sorted(groups.items())}
    print(f'{"group":<24}{"n":>4}{"steps":>7}{"atk":>6}{"prize":>6}{"oppPrz":>7}'
          f'{"swtch":>6}{"boss":>6}{"bosPV":>7}{"bos676":>7}{"nrg":>6}{"nrgA%":>7}'
          f'{"nrgB%":>7}{"ko":>6}{"koPV":>6}{"hiTgt%":>7}'
          f'{"preN":>6}{"preA%":>7}{"preB%":>7}')
    for k, a in table.items():
        print(f'{k:<24}{a["n"]:>4}{a["steps"]:>7}{a["atk_pg"]:>6}{a["prizes_pg"]:>6}'
              f'{a["opp_prizes_pg"]:>7}{a["switch_pg"]:>6}{a["boss_pg"]:>6}'
              f'{a["boss_pv"]!s:>7}{a["boss_676%"]!s:>7}{a["nrg_pg"]:>6}'
              f'{a["nrg_act%"]!s:>7}{a["nrg_bench%"]!s:>7}'
              f'{a["ko_pg"]:>6}{a["ko_victim_pv_mean"]!s:>6}{a["ko_hi_target%"]!s:>7}'
              f'{a["nrg_pre_n"]:>6}{a["pre_act%"]!s:>7}{a["pre_bench%"]!s:>7}')
    print('\n--- switch 三分解 (每局均次): postKO=强制升场 / gust=Boss受害者 / vol=自愿换位(决策) ---')
    print(f'{"group":<24}{"n":>4}{"swtch":>7}{"postKO":>8}{"gust":>7}{"vol":>7}{"volPre":>8}{"vol%":>7}')
    for k, a in table.items():
        volpct = (a['sw_vol_pg'] / a['switch_pg'] * 100) if a['switch_pg'] else None
        print(f'{k:<24}{a["n"]:>4}{a["switch_pg"]:>7}{a["sw_postko_pg"]:>8}'
              f'{a["sw_gust_pg"]:>7}{a["sw_vol_pg"]:>7}{a["sw_vol_pre_pg"]:>8}'
              f'{round(volpct,1)!s:>7}')
    print('\n--- type8 换位 (真·自愿决策载体): vol=自愿 / gust=Boss受害 / volPre=setup期 / volAtk=换上即攻 ---')
    print(f'{"group":<24}{"n":>4}{"t8":>7}{"gust":>7}{"vol":>7}{"volPre":>8}{"volAtk":>8}{"atk%":>7}')
    for k, a in table.items():
        atkpct = round(a['sw8_atk_pg'] / a['sw8_vol_pg'] * 100, 1) if a['sw8_vol_pg'] else None
        print(f'{k:<24}{a["n"]:>4}{a["t8_pg"]:>7}{a["sw8_gust_pg"]:>7}'
              f'{a["sw8_vol_pg"]:>7}{a["sw8_vol_pre_pg"]:>8}{a["sw8_atk_pg"]:>8}{atkpct!s:>7}')
    return table


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stage', default='explore', choices=['explore', 'diff'])
    ap.add_argument('--source', default='all', choices=['all', 'top', 'ours', 'probe'],
                    help='all=top+ours (历史默认); probe=探针 55468450 replay, 走 ours 通道分组')
    ap.add_argument('--delete-raw', action='store_true')
    args = ap.parse_args()

    src = args.source
    games_top = collect('top') if src in ('all', 'top') else []
    games_ours = []
    if src in ('all', 'ours') and (PROJ / 'experiments/runs/live_replays').exists():
        games_ours = collect('ours')
    elif src == 'probe' and (PROJ / 'experiments/runs/live_replays_probe').exists():
        games_ours = collect('probe')
    print(f'parsed: src={src} top={len(games_top)} ours={len(games_ours)} '
          f'(mirror: top={sum(1 for g in games_top if g["mirror"])} '
          f'ours={sum(1 for g in games_ours if g["mirror"])})')

    if args.stage == 'explore':
        allc = Counter()
        for g in games_top + games_ours:
            allc.update(g['events_type'])
        print('事件类型分布:', dict(allc.most_common()))
        for g in games_top[:2] + games_ours[:2]:
            print(f'\n-- {g["player"]} vs {g["opp"]} samples:')
            for t, s in sorted(g['type_samples'].items(), key=lambda x: str(x[0])):
                print(f'  type{t}: {s}')
        return

    table = diff_stage(games_top, games_ours)
    out = {'groups': table,
           'per_game': [{k: (dict(v) if k == 'events_type' else v)
                         for k, v in g.items() if k != 'type_samples'}
                        for g in games_top + games_ours]}
    for g in out['per_game']:
        g['events_type'] = dict(g['events_type'])
    # A3 修补: probe 源写独立文件, 防覆盖 configA 归档件 (08-13 冒烟曾误覆盖, 从
    # pilot_investigation/artifacts/ 恢复; top replay raw 已删, runs/ 件不可再生)
    out_name = 'top_pilot_diff_probe.json' if src == 'probe' else 'top_pilot_diff.json'
    (PROJ / f'experiments/runs/{out_name}').write_text(
        json.dumps(out, ensure_ascii=False, indent=1))
    print(f'\nsaved -> experiments/runs/{out_name}')

    if args.delete_raw:
        n = 0
        for fp in (PROJ / 'experiments/runs/top_pilot_replays').glob('*.json'):
            fp.unlink()
            n += 1
        print(f'delete-raw: 清掉 {n} 个 replay 原包')


if __name__ == '__main__':
    main()
