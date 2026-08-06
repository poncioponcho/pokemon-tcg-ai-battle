(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var accent3 = style.getPropertyValue('--accent3').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();
  var warn = style.getPropertyValue('--warn').trim();
  var success = style.getPropertyValue('--success').trim();
  var danger = style.getPropertyValue('--danger').trim();

  // === Chart 1: Prize Card Progression ===
  var chartPrize = echarts.init(document.getElementById('chart-prize'), null, { renderer: 'svg' });
  chartPrize.setOption({
    title: { text: '奖赏卡剩余数量变化', left: 'center', textStyle: { color: muted, fontSize: 13 } },
    legend: { data: ['v15 我方剩余', 'v15 对方剩余', 'v16 我方剩余', 'v16 对方剩余'], bottom: 0, textStyle: { color: muted, fontSize: 11 } },
    grid: { left: 50, right: 30, top: 50, bottom: 60 },
    xAxis: { type: 'category', name: 'Step', nameTextStyle: { color: muted }, axisLabel: { color: muted, fontSize: 10 }, axisLine: { lineStyle: { color: rule } }, splitLine: { show: false } },
    yAxis: { type: 'value', name: '剩余奖赏卡', nameTextStyle: { color: muted }, min: 0, max: 6, axisLabel: { color: muted }, axisLine: { lineStyle: { color: rule } }, splitLine: { lineStyle: { color: rule, type: 'dashed' } } },
    tooltip: { trigger: 'axis', appendToBody: true },
    animation: false,
    series: [
      {
        name: 'v15 我方剩余', type: 'line', smooth: true,
        data: [[0, 6], [55, 6], [57, 5], [73, 5], [74, 4], [84, 4], [85, 3], [93, 3], [94, 2], [162, 2]],
        itemStyle: { color: success }, lineStyle: { color: success, width: 2 }
      },
      {
        name: 'v15 对方剩余', type: 'line', smooth: true,
        data: [[0, 6], [56, 6], [57, 5], [73, 5], [74, 4], [84, 4], [85, 3], [134, 3], [135, 2], [145, 2], [146, 1], [159, 1], [160, 0], [162, 0]],
        itemStyle: { color: accent2 }, lineStyle: { color: accent2, width: 2, type: 'dashed' }
      },
      {
        name: 'v16 我方剩余', type: 'line', smooth: true,
        data: [[0, 6], [42, 6], [43, 5], [102, 5], [103, 4], [151, 4]],
        itemStyle: { color: warn }, lineStyle: { color: warn, width: 2 }
      },
      {
        name: 'v16 对方剩余', type: 'line', smooth: true,
        data: [[0, 6], [125, 6], [126, 5], [132, 5], [133, 4], [141, 4], [142, 3], [148, 3], [149, 2], [151, 2]],
        itemStyle: { color: accent }, lineStyle: { color: accent, width: 2, type: 'dashed' }
      }
    ]
  });
  window.addEventListener('resize', function() { chartPrize.resize(); });

  // === Chart 2: Radar Chart ===
  var chartRadar = echarts.init(document.getElementById('chart-radar'), null, { renderer: 'svg' });
  chartRadar.setOption({
    title: { text: '决策质量多维度对比', left: 'center', textStyle: { color: muted, fontSize: 13 } },
    legend: { data: ['v15 (rec7)', 'v16 (rec8)'], bottom: 0, textStyle: { color: muted } },
    tooltip: { appendToBody: true },
    animation: false,
    radar: {
      indicator: [
        { name: '合法率(%)', max: 50 },
        { name: '决策多样性(%)', max: 100 },
        { name: '进化次数', max: 5 },
        { name: '攻击次数', max: 6 },
        { name: 'KO次数', max: 5 },
        { name: '训练家卡使用', max: 8 }
      ],
      axisName: { color: ink, fontSize: 11 },
      splitLine: { lineStyle: { color: rule } },
      splitArea: { areaStyle: { color: [bg2, 'transparent'] } },
      axisLine: { lineStyle: { color: rule } }
    },
    series: [{
      type: 'radar',
      data: [
        {
          value: [36.4, 15.4, 4, 0, 4, 7],
          name: 'v15 (rec7)',
          itemStyle: { color: success },
          areaStyle: { color: 'rgba(78,201,168,0.12)' },
          lineStyle: { color: success, width: 2 }
        },
        {
          value: [37.7, 46.9, 0, 5, 1, 3],
          name: 'v16 (rec8)',
          itemStyle: { color: accent2 },
          areaStyle: { color: 'rgba(232,93,117,0.12)' },
          lineStyle: { color: accent2, width: 2 }
        }
      ]
    }]
  });
  window.addEventListener('resize', function() { chartRadar.resize(); });

  // === Chart 3: Tactical Actions Bar Chart ===
  var chartActions = echarts.init(document.getElementById('chart-actions'), null, { renderer: 'svg' });
  chartActions.setOption({
    title: { text: '核心战术动作数量对比', left: 'center', textStyle: { color: muted, fontSize: 13 } },
    legend: { data: ['v15 (rec7)', 'v16 (rec8)'], bottom: 0, textStyle: { color: muted } },
    grid: { left: 60, right: 30, top: 50, bottom: 50 },
    xAxis: {
      type: 'category',
      data: ['攻击', '进化', '贴能(active)', '贴能(bench)', '训练家卡', '宝可梦卡', '撤退', '特性', 'KO'],
      axisLabel: { color: muted, fontSize: 10, rotate: 25 },
      axisLine: { lineStyle: { color: rule } }
    },
    yAxis: { type: 'value', axisLabel: { color: muted }, axisLine: { lineStyle: { color: rule } }, splitLine: { lineStyle: { color: rule, type: 'dashed' } } },
    tooltip: { trigger: 'axis', appendToBody: true },
    animation: false,
    series: [
      {
        name: 'v15 (rec7)', type: 'bar',
        data: [0, 4, 5, 0, 7, 3, 2, 3, 4],
        itemStyle: { color: success, borderRadius: [4, 4, 0, 0] },
        barGap: '20%'
      },
      {
        name: 'v16 (rec8)', type: 'bar',
        data: [5, 0, 4, 3, 3, 9, 1, 2, 1],
        itemStyle: { color: accent2, borderRadius: [4, 4, 0, 0] }
      }
    ]
  });
  window.addEventListener('resize', function() { chartActions.resize(); });

})();
