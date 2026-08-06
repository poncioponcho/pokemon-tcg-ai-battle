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

  // --- Chart 1: Top 15 Cards by Usage Rate ---
  var chart1 = echarts.init(document.getElementById('chart-topcards'), null, { renderer: 'svg' });
  chart1.setOption({
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      appendToBody: true,
      backgroundColor: bg2,
      borderColor: rule,
      textStyle: { color: ink }
    },
    grid: { left: 200, right: 60, top: 10, bottom: 30 },
    xAxis: {
      type: 'value',
      max: 100,
      axisLabel: { color: muted, formatter: '{value}%' },
      axisLine: { lineStyle: { color: rule } },
      splitLine: { lineStyle: { color: rule } }
    },
    yAxis: {
      type: 'category',
      data: [
        'フーディン (743)',
        'マリィのオーロンゲex (648)',
        'マリィのギモー (647)',
        'ボスの指令 (1182)',
        'ふしぎなアメ (1079)',
        '夜のタンカ (1097)',
        'マリィのベロバー (646)',
        'スパイクタウンジム (1259)',
        'マシマシラ (112)',
        'ロケット団のラムダ (1219)',
        'ポケパッド (1152)',
        'リーリエの決心 (1227)',
        'なかよしポフィン (1086)',
        '基本【悪】エネルギー (7)',
        'オーガポン みどりのめんex (96)'
      ].reverse(),
      axisLabel: { color: ink, fontSize: 11 },
      axisLine: { lineStyle: { color: rule } }
    },
    series: [{
      type: 'bar',
      data: [45.4, 37.8, 37.6, 41.2, 43.5, 45.3, 50.2, 50.4, 51.6, 54.1, 69.8, 69.9, 71.1, 63.7, 13.7].reverse().map(function(v, i) {
        return {
          value: v,
          itemStyle: { color: i >= 12 ? accent : (i >= 10 ? accent2 : muted) }
        };
      }),
      barWidth: 16,
      label: {
        show: true,
        position: 'right',
        color: ink,
        fontSize: 11,
        formatter: '{c}%'
      }
    }]
  });
  window.addEventListener('resize', function() { chart1.resize(); });

  // --- Chart 2: Win Rate Deviation ---
  var chart2 = echarts.init(document.getElementById('chart-winrate'), null, { renderer: 'svg' });
  var winrateData = [
    { name: 'マツバの確信 (1187)', value: 25.7, type: 'neg' },
    { name: 'ペロッパフ (247)', value: 36.0, type: 'neg' },
    { name: 'ハンドトリマー (1087)', value: 43.3, type: 'neg' },
    { name: '改造ハンマー (1081)', value: 44.7, type: 'neg' },
    { name: 'フーディン (743)', value: 45.4, type: 'neg' },
    { name: 'ガラスのラッパ (1098)', value: 56.8, type: 'pos' },
    { name: 'シアノ (1205)', value: 56.8, type: 'pos' },
    { name: 'プライムキャッチャー (1088)', value: 56.8, type: 'pos' },
    { name: 'ジャッジマン (1213)', value: 58.8, type: 'pos' },
    { name: 'オーガポン みどりのめんex (96)', value: 59.1, type: 'pos' },
    { name: 'エネルギー転送 (1119)', value: 61.2, type: 'pos' },
    { name: 'テラスタルオーブ (1127)', value: 64.1, type: 'pos' },
    { name: 'クラウン (1223)', value: 64.1, type: 'pos' },
    { name: 'エキサイトスタジアム (1251)', value: 64.1, type: 'pos' },
    { name: 'エネルギー回収 (1118)', value: 64.1, type: 'pos' }
  ];

  chart2.setOption({
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      appendToBody: true,
      backgroundColor: bg2,
      borderColor: rule,
      textStyle: { color: ink },
      formatter: function(params) {
        var p = params[0];
        return p.name + '<br/>胜率: ' + p.value + '%';
      }
    },
    grid: { left: 220, right: 60, top: 30, bottom: 30 },
    xAxis: {
      type: 'value',
      min: 20,
      max: 70,
      axisLabel: { color: muted, formatter: '{value}%' },
      axisLine: { lineStyle: { color: rule } },
      splitLine: { lineStyle: { color: rule } }
    },
    yAxis: {
      type: 'category',
      data: winrateData.map(function(d) { return d.name; }),
      axisLabel: { color: ink, fontSize: 10 },
      axisLine: { lineStyle: { color: rule } }
    },
    series: [{
      type: 'bar',
      data: winrateData.map(function(d) {
        return {
          value: d.value,
          itemStyle: { color: d.type === 'pos' ? accent3 : accent }
        };
      }),
      barWidth: 14,
      label: {
        show: true,
        position: 'right',
        color: ink,
        fontSize: 10,
        formatter: '{c}%'
      },
      markLine: {
        silent: true,
        symbol: 'none',
        lineStyle: { color: muted, type: 'dashed' },
        data: [{ xAxis: 50 }],
        label: { formatter: '50% (基准)', color: muted, fontSize: 10 }
      }
    }]
  });
  window.addEventListener('resize', function() { chart2.resize(); });

  // --- Chart 3: Deck Composition Comparison ---
  var chart3 = echarts.init(document.getElementById('chart-composition'), null, { renderer: 'svg' });
  chart3.setOption({
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      appendToBody: true,
      backgroundColor: bg2,
      borderColor: rule,
      textStyle: { color: ink }
    },
    legend: {
      data: ['当前卡组', 'Meta 平均', 'Top 1 (Majkel1337)', '玛俐暗系'],
      textStyle: { color: ink, fontSize: 11 },
      top: 0
    },
    grid: { left: 80, right: 40, top: 40, bottom: 30 },
    xAxis: {
      type: 'category',
      data: ['宝可梦', '训练家', '能量'],
      axisLabel: { color: ink, fontSize: 13 },
      axisLine: { lineStyle: { color: rule } }
    },
    yAxis: {
      type: 'value',
      max: 50,
      axisLabel: { color: muted },
      axisLine: { lineStyle: { color: rule } },
      splitLine: { lineStyle: { color: rule } }
    },
    series: [
      {
        name: '当前卡组',
        type: 'bar',
        data: [36, 0, 24],
        itemStyle: { color: accent },
        barWidth: 18
      },
      {
        name: 'Meta 平均',
        type: 'bar',
        data: [17, 33, 10],
        itemStyle: { color: accent2 },
        barWidth: 18
      },
      {
        name: 'Top 1 (Majkel1337)',
        type: 'bar',
        data: [18, 28, 14],
        itemStyle: { color: accent3 },
        barWidth: 18
      },
      {
        name: '玛俐暗系',
        type: 'bar',
        data: [20, 30, 10],
        itemStyle: { color: warn },
        barWidth: 18
      }
    ]
  });
  window.addEventListener('resize', function() { chart3.resize(); });

})();
