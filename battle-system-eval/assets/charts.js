// 战斗系统评估报告 — 数据图表
(function () {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  // --- 图1: 终局奖赏卡差距分布 (300场) ---
  var el1 = document.getElementById('chart-prize');
  if (el1) {
    var c1 = echarts.init(el1, null, { renderer: 'svg' });
    c1.setOption({
      animation: false,
      tooltip: { trigger: 'axis', appendToBody: true },
      grid: { left: 50, right: 20, top: 30, bottom: 40 },
      xAxis: {
        type: 'category',
        data: ['0 (均势)', '1', '2', '3', '4', '5', '6 (碾压)'],
        axisLine: { lineStyle: { color: rule } },
        axisLabel: { color: muted }
      },
      yAxis: {
        type: 'value',
        name: '对局数',
        axisLine: { lineStyle: { color: rule } },
        axisLabel: { color: muted },
        splitLine: { lineStyle: { color: rule, type: 'dashed' } }
      },
      series: [{
        type: 'bar',
        data: [5, 40, 61, 60, 57, 38, 39],
        itemStyle: {
          color: function (p) { return p.dataIndex >= 4 ? accent : accent2; },
          borderRadius: [3, 3, 0, 0]
        },
        label: { show: true, position: 'top', color: ink, fontSize: 11 }
      }]
    });
    window.addEventListener('resize', function () { c1.resize(); });
  }

  // --- 图2: 我方对局步数分布 (13期) ---
  var el2 = document.getElementById('chart-steps');
  if (el2) {
    var c2 = echarts.init(el2, null, { renderer: 'svg' });
    c2.setOption({
      animation: false,
      tooltip: { trigger: 'axis', appendToBody: true },
      grid: { left: 50, right: 20, top: 30, bottom: 60 },
      xAxis: {
        type: 'category',
        data: ['rec1', 'rec2', 'rec3', 'rec4', 'rec5', 'rec6', 'rec7', 'rec8', 'rec9', 'rec10', 'rec11', 'rec12', 'rec13'],
        axisLabel: { color: muted, rotate: 40 },
        axisLine: { lineStyle: { color: rule } }
      },
      yAxis: {
        type: 'value',
        name: '步数',
        axisLine: { lineStyle: { color: rule } },
        axisLabel: { color: muted },
        splitLine: { lineStyle: { color: rule, type: 'dashed' } }
      },
      series: [{
        type: 'bar',
        data: [
          { value: 227, itemStyle: { color: accent } },
          { value: 132, itemStyle: { color: accent } },
          { value: 162, itemStyle: { color: accent } },
          { value: 86, itemStyle: { color: accent } },
          { value: 23, itemStyle: { color: accent2 } },
          { value: 168, itemStyle: { color: accent } },
          { value: 163, itemStyle: { color: accent2 } },
          { value: 152, itemStyle: { color: accent } },
          { value: 75, itemStyle: { color: accent2 } },
          { value: 169, itemStyle: { color: accent2 } },
          { value: 111, itemStyle: { color: accent2 } },
          { value: 181, itemStyle: { color: accent } },
          { value: 123, itemStyle: { color: accent } }
        ],
        itemStyle: { borderRadius: [3, 3, 0, 0] },
        label: { show: true, position: 'top', color: ink, fontSize: 10 }
      }]
    });
    window.addEventListener('resize', function () { c2.resize(); });
  }

  // --- 图3: 攻击动作分布 Top12 ---
  var el3 = document.getElementById('chart-attack');
  if (el3) {
    var c3 = echarts.init(el3, null, { renderer: 'svg' });
    c3.setOption({
      animation: false,
      tooltip: { trigger: 'axis', appendToBody: true },
      grid: { left: 70, right: 30, top: 20, bottom: 40 },
      xAxis: {
        type: 'value',
        name: '次数',
        axisLine: { lineStyle: { color: rule } },
        axisLabel: { color: muted },
        splitLine: { lineStyle: { color: rule, type: 'dashed' } }
      },
      yAxis: {
        type: 'category',
        data: ['937', '1225', '120', '1072', '115', '479', '153', '531', '1226', '154', '323', '1092'],
        axisLine: { lineStyle: { color: rule } },
        axisLabel: { color: muted }
      },
      series: [{
        type: 'bar',
        data: [3735, 3205, 2624, 2031, 1849, 947, 943, 854, 833, 829, 820, 575],
        itemStyle: { color: accent2, borderRadius: [0, 3, 3, 0] },
        label: { show: true, position: 'right', color: ink, fontSize: 10 }
      }]
    });
    window.addEventListener('resize', function () { c3.resize(); });
  }
})();
