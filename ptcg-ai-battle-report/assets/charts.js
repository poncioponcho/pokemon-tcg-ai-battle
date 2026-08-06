// charts.js — Pokémon TCG AI Battle Challenge 报告图表
(function() {
  'use strict';

  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();
  var bg = style.getPropertyValue('--bg').trim();

  // ================================================================
  // Chart 1: 卡组使用率饼图 (chart-meta)
  // ================================================================
  var metaChart = echarts.init(document.getElementById('chart-meta'), null, { renderer: 'svg' });
  metaChart.setOption({
    title: {
      text: '天梯环境卡组使用率分布',
      left: 'center',
      textStyle: { color: ink, fontSize: 16, fontWeight: 600, fontFamily: 'BricolageGrotesque, sans-serif' }
    },
    tooltip: { trigger: 'item', appendToBody: true,
      formatter: function(p) { return '<strong>' + p.name + '</strong><br/>使用率: ' + p.percent.toFixed(1) + '%'; }
    },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['50%', '55%'],
      avoidLabelOverlap: true,
      padAngle: 2,
      itemStyle: { borderRadius: 6, borderColor: bg, borderWidth: 2 },
      label: { show: true, formatter: '{b}\n{d}%', color: ink, fontSize: 12, fontWeight: 500 },
      emphasis: { label: { show: true, fontSize: 16, fontWeight: 'bold' } },
      data: [
        { value: 60.0, name: 'マリィ/オーロンゲex (恶系)', itemStyle: { color: '#4a1a4a' } },
        { value: 12.5, name: 'リザードンex (火系)', itemStyle: { color: accent } },
        { value: 8.2, name: 'ミュウツーV-UNION (超能系)', itemStyle: { color: accent2 } },
        { value: 6.8, name: 'パルキアVSTAR (水系)', itemStyle: { color: '#0077be' } },
        { value: 12.5, name: 'その他 (其他卡组)', itemStyle: { color: muted } }
      ]
    }]
  });
  window.addEventListener('resize', function() { metaChart.resize(); });

  // ================================================================
  // Chart 2: 卡组使用率与胜率对比 (chart-meta-distribution)
  // ================================================================
  var metaDistChart = echarts.init(document.getElementById('chart-meta-distribution'), null, { renderer: 'svg' });
  metaDistChart.setOption({
    title: {
      text: '卡组使用率与胜率对比',
      left: 'center',
      textStyle: { color: ink, fontSize: 16, fontWeight: 600, fontFamily: 'BricolageGrotesque, sans-serif' }
    },
    tooltip: { trigger: 'axis', appendToBody: true,
      formatter: function(ps) {
        var s = '<strong>' + ps[0].axisValue + '</strong><br/>';
        ps.forEach(function(p) { s += p.marker + ' ' + p.seriesName + ': ' + p.value + '%<br/>'; });
        return s;
      }
    },
    legend: {
      data: ['使用率', '胜率'],
      top: 40,
      textStyle: { color: muted }
    },
    grid: { left: 60, right: 40, top: 80, bottom: 60 },
    xAxis: {
      type: 'category',
      data: ['恶系', '火系', '超能系', '水系', '其他'],
      axisLabel: { color: muted, fontSize: 12, interval: 0, rotate: 0 },
      axisLine: { lineStyle: { color: rule } },
      axisTick: { alignWithLabel: true }
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 70,
      axisLabel: { color: muted, formatter: '{value}%' },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } }
    },
    series: [
      {
        name: '使用率',
        type: 'bar',
        barWidth: '28%',
        barGap: '20%',
        itemStyle: { color: accent, borderRadius: [4, 4, 0, 0] },
        data: [60.0, 12.5, 8.2, 6.8, 12.5]
      },
      {
        name: '胜率',
        type: 'bar',
        barWidth: '28%',
        itemStyle: { color: accent2, borderRadius: [4, 4, 0, 0] },
        data: [50.25, 48.30, 52.10, 47.85, 45.20]
      }
    ]
  });
  window.addEventListener('resize', function() { metaDistChart.resize(); });

  // ================================================================
  // Chart 3: 卡组构成演化 (chart-deck-evolution)
  // ================================================================
  var deckChart = echarts.init(document.getElementById('chart-deck-evolution'), null, { renderer: 'svg' });
  deckChart.setOption({
    title: {
      text: '卡组构成演化（宝可梦 / 能量 / 训练家卡）',
      left: 'center',
      textStyle: { color: ink, fontSize: 16, fontWeight: 600, fontFamily: 'BricolageGrotesque, sans-serif' }
    },
    tooltip: { trigger: 'axis', appendToBody: true,
      formatter: function(ps) {
        var s = '<strong>' + ps[0].axisValue + '</strong><br/>';
        ps.forEach(function(p) { s += p.marker + ' ' + p.seriesName + ': ' + p.value + ' 张<br/>'; });
        return s;
      }
    },
    legend: {
      data: ['宝可梦', '能量', '训练家卡'],
      top: 40,
      textStyle: { color: muted }
    },
    grid: { left: 60, right: 40, top: 80, bottom: 60 },
    xAxis: {
      type: 'category',
      data: ['v10', 'v11', 'v12', 'v13'],
      axisLabel: { color: muted, fontSize: 13, fontWeight: 600 },
      axisLine: { lineStyle: { color: rule } },
      axisTick: { alignWithLabel: true }
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 50,
      axisLabel: { color: muted, formatter: '{value}' },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } }
    },
    series: [
      {
        name: '宝可梦',
        type: 'bar',
        stack: 'total',
        itemStyle: { color: accent2, borderRadius: [0, 0, 0, 0] },
        emphasis: { focus: 'series' },
        data: [12, 36, 14, 14]
      },
      {
        name: '能量',
        type: 'bar',
        stack: 'total',
        itemStyle: { color: accent, borderRadius: [0, 0, 0, 0] },
        emphasis: { focus: 'series' },
        data: [44, 24, 14, 14]
      },
      {
        name: '训练家卡',
        type: 'bar',
        stack: 'total',
        itemStyle: { color: '#4a1a4a', borderRadius: [4, 4, 0, 0] },
        emphasis: { focus: 'series' },
        data: [4, 0, 32, 32]
      }
    ]
  });
  window.addEventListener('resize', function() { deckChart.resize(); });

  // ================================================================
  // Chart 4: Bug 影响范围分析 (chart-bug-impact)
  // ================================================================
  var bugChart = echarts.init(document.getElementById('chart-bug-impact'), null, { renderer: 'svg' });
  bugChart.setOption({
    title: {
      text: 'Bug 影响范围分析（受影响模块严重程度）',
      left: 'center',
      textStyle: { color: ink, fontSize: 16, fontWeight: 600, fontFamily: 'BricolageGrotesque, sans-serif' }
    },
    tooltip: { trigger: 'item', appendToBody: true,
      formatter: function(p) {
        var severity = p.value === 3 ? '严重' : p.value === 2 ? '中等' : '低';
        return '<strong>' + p.name + '</strong><br/>严重程度: ' + severity + ' (' + p.value + '/3)';
      }
    },
    radar: {
      indicator: [
        { name: 'State Parser\n状态解析', max: 3 },
        { name: 'State Evaluator\n局势评估', max: 3 },
        { name: 'Decision Gate\n决策门控', max: 3 },
        { name: 'AttackHandler\n攻击处理', max: 3 },
        { name: 'TrainerHandler\n训练家处理', max: 3 },
        { name: '日志系统\n日志输出', max: 3 }
      ],
      center: ['50%', '55%'],
      radius: '65%',
      axisName: { color: ink, fontSize: 11, fontWeight: 500 },
      splitArea: { areaStyle: { color: [bg2 + '44', bg2 + '88'] } },
      axisLine: { lineStyle: { color: rule } },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } }
    },
    series: [{
      type: 'radar',
      data: [
        {
          value: [3, 3, 3, 2, 2, 1],
          name: '受影响程度',
          areaStyle: { color: accent + '33' },
          lineStyle: { color: accent, width: 2 },
          itemStyle: { color: accent }
        }
      ]
    }]
  });
  window.addEventListener('resize', function() { bugChart.resize(); });

  // ================================================================
  // Chart 5: 决策质量对比 (chart-decision-quality)
  // ================================================================
  var qualityChart = echarts.init(document.getElementById('chart-decision-quality'), null, { renderer: 'svg' });
  qualityChart.setOption({
    title: {
      text: 'Agent vs 人类玩家 — 动作类型一致率对比',
      left: 'center',
      textStyle: { color: ink, fontSize: 16, fontWeight: 600, fontFamily: 'BricolageGrotesque, sans-serif' }
    },
    tooltip: { trigger: 'axis', appendToBody: true,
      formatter: function(ps) {
        var s = '<strong>' + ps[0].axisValue + '</strong><br/>';
        ps.forEach(function(p) { s += p.marker + ' ' + p.seriesName + ': ' + p.value + '%<br/>'; });
        return s;
      }
    },
    legend: {
      data: ['Agent 一致率', '随机基准 (16.7%)'],
      top: 40,
      textStyle: { color: muted }
    },
    grid: { left: 60, right: 40, top: 80, bottom: 60 },
    xAxis: {
      type: 'category',
      data: ['攻击', '进化', '能量附着', '训练家卡', '撤退', '结束回合'],
      axisLabel: { color: muted, fontSize: 12, interval: 0, rotate: 0 },
      axisLine: { lineStyle: { color: rule } },
      axisTick: { alignWithLabel: true }
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 50,
      axisLabel: { color: muted, formatter: '{value}%' },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } }
    },
    series: [
      {
        name: 'Agent 一致率',
        type: 'bar',
        barWidth: '35%',
        itemStyle: {
          color: function(p) {
            var colors = [accent, accent2, accent, accent2, accent, accent2];
            return colors[p.dataIndex] || accent;
          },
          borderRadius: [4, 4, 0, 0]
        },
        data: [42, 40, 38, 35, 30, 45]
      },
      {
        name: '随机基准 (16.7%)',
        type: 'line',
        lineStyle: { color: muted, type: 'dashed', width: 2 },
        itemStyle: { color: muted },
        symbol: 'none',
        data: [16.7, 16.7, 16.7, 16.7, 16.7, 16.7]
      }
    ]
  });
  window.addEventListener('resize', function() { qualityChart.resize(); });

  // ================================================================
  // Chart 6: 性能综合指标 (chart-performance)
  // ================================================================
  var perfChart = echarts.init(document.getElementById('chart-performance'), null, { renderer: 'svg' });
  perfChart.setOption({
    title: {
      text: 'Agent 综合性能指标概览',
      left: 'center',
      textStyle: { color: ink, fontSize: 16, fontWeight: 600, fontFamily: 'BricolageGrotesque, sans-serif' }
    },
    tooltip: { trigger: 'item', appendToBody: true,
      formatter: function(p) {
        return '<strong>' + p.name + '</strong><br/>' + p.value;
      }
    },
    radar: {
      indicator: [
        { name: '运行稳定性', max: 100 },
        { name: '决策一致性', max: 100 },
        { name: '动作合法性', max: 100 },
        { name: '攻击效率', max: 100 },
        { name: '能量管理', max: 100 },
        { name: '进化策略', max: 100 }
      ],
      center: ['50%', '55%'],
      radius: '65%',
      axisName: { color: ink, fontSize: 11, fontWeight: 500 },
      splitArea: { areaStyle: { color: [bg2 + '44', bg2 + '88'] } },
      axisLine: { lineStyle: { color: rule } },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } }
    },
    series: [
      {
        type: 'radar',
        data: [
          {
            value: [100, 36, 100, 42, 38, 40],
            name: 'Agent 性能',
            areaStyle: { color: accent + '33' },
            lineStyle: { color: accent, width: 2 },
            itemStyle: { color: accent }
          }
        ]
      }
    ]
  });
  window.addEventListener('resize', function() { perfChart.resize(); });
})();