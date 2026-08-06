/* TopRatedEpisodes 数据分析报告 — ECharts 图表 */
(function () {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();
  var good = style.getPropertyValue('--good').trim();
  var bad = style.getPropertyValue('--bad').trim();
  var warn = style.getPropertyValue('--warn').trim();

  var AXIS = {
    axisLine: { lineStyle: { color: rule } },
    axisLabel: { color: muted },
    axisTick: { show: false },
    splitLine: { lineStyle: { color: rule, opacity: .5 } }
  };
  var LEGEND = { textStyle: { color: muted }, top: 0, right: 0 };
  var TIP = {
    appendToBody: true,
    backgroundColor: bg2,
    borderColor: rule,
    textStyle: { color: ink, fontSize: 13 }
  };

  /* ---------- 01 各版本决策样本量 ---------- */
  var elSamples = document.getElementById('chart-samples');
  if (elSamples) {
    var c = echarts.init(elSamples, null, { renderer: 'svg' });
    c.setOption({
      animation: false,
      tooltip: TIP,
      grid: { left: 60, right: 24, top: 40, bottom: 40 },
      xAxis: Object.assign({}, AXIS, { type: 'category', data: ['0701', '0708', '0712', '0719', '0731'] }),
      yAxis: Object.assign({}, AXIS, { type: 'value', name: '样本数', nameTextStyle: { color: muted } }),
      series: [{
        type: 'bar',
        data: [
          { value: 14607, itemStyle: { color: accent + '77' } },
          { value: 63196, itemStyle: { color: accent + '77' } },
          { value: 35800, itemStyle: { color: accent + '77' } },
          { value: 86265, itemStyle: { color: accent + '77' } },
          { value: 196221, itemStyle: { color: accent } }
        ],
        barWidth: 56,
        label: { show: true, position: 'top', color: ink, fontFamily: 'Outfit', fontSize: 13 }
      }]
    });
    window.addEventListener('resize', function () { c.resize(); });
  }

  /* ---------- 02 装备道具组合 ---------- */
  var elTools = document.getElementById('chart-tools');
  if (elTools) {
    var c = echarts.init(elTools, null, { renderer: 'svg' });
    c.setOption({
      animation: false,
      tooltip: TIP,
      legend: LEGEND,
      grid: { left: 60, right: 24, top: 40, bottom: 40 },
      xAxis: Object.assign({}, AXIS, { type: 'category', data: ['0701', '0708', '0712', '0719', '0731'] }),
      yAxis: Object.assign({}, AXIS, { type: 'value', name: '648 场上占比', nameTextStyle: { color: muted } }),
      series: [
        { name: '无道具', type: 'bar', stack: 't', data: [50.0, 72.4, 86.7, 86.7, 93.1], itemStyle: { color: bg2 } },
        { name: '1159 ヒーローマント', type: 'bar', stack: 't', data: [31.0, 5.2, 12.6, 0, 0], itemStyle: { color: accent2 } },
        { name: '1161 サーキュレーター', type: 'bar', stack: 't', data: [6.0, 4.0, 0.7, 13.3, 6.9], itemStyle: { color: accent } }
      ]
    });
    window.addEventListener('resize', function () { c.resize(); });
  }

  /* ---------- 03 版本迁移准确率 ---------- */
  var elTrans = document.getElementById('chart-transfer');
  if (elTrans) {
    var c = echarts.init(elTrans, null, { renderer: 'svg' });
    var cats = ['B0 仅0701', 'B1 仅0708', 'B2 仅0712', 'B3 仅0719', 'B 仅旧数据', 'A 仅0731', 'C 全版本'];
    var vals = [0.4612, 0.4924, 0.5017, 0.5239, 0.5120, 0.5211, 0.5261];
    var cols = [bad, bad, warn, warn, accent2 + '99', accent + '99', accent];
    c.setOption({
      animation: false,
      tooltip: TIP,
      grid: { left: 56, right: 24, top: 40, bottom: 60 },
      xAxis: Object.assign({}, AXIS, {
        type: 'category', data: cats,
        axisLabel: { color: muted, rotate: 30, fontSize: 12 }
      }),
      yAxis: Object.assign({}, AXIS, {
        type: 'value', min: 0.44, max: 0.54,
        axisLabel: { color: muted, formatter: function (v) { return v.toFixed(2); } }
      }),
      series: [{
        type: 'bar',
        data: vals.map(function (v, i) { return { value: v, itemStyle: { color: cols[i] } }; }),
        barWidth: 40,
        label: { show: true, position: 'top', color: ink, fontFamily: 'Outfit', formatter: function (p) { return p.value.toFixed(4); } }
      }]
    });
    window.addEventListener('resize', function () { c.resize(); });
  }

  /* ---------- 04 门控曲线 ---------- */
  var elGate = document.getElementById('chart-gate');
  if (elGate) {
    var c = echarts.init(elGate, null, { renderer: 'svg' });
    var thr = ['0.5', '0.6', '0.7', '0.8'];
    c.setOption({
      animation: false,
      tooltip: TIP,
      legend: LEGEND,
      grid: { left: 64, right: 64, top: 40, bottom: 40 },
      xAxis: Object.assign({}, AXIS, { type: 'category', data: thr }),
      yAxis: [
        Object.assign({}, AXIS, { type: 'value', name: '覆盖率 %', nameTextStyle: { color: muted }, max: 60 }),
        Object.assign({}, AXIS, { type: 'value', name: '准确率', nameTextStyle: { color: muted }, min: 0.6, max: 1 })
      ],
      series: [
        { name: 'A 覆盖率', type: 'line', data: [46.9, 23.4, 11.4, 7.0], itemStyle: { color: accent + '99' }, lineStyle: { width: 2 }, symbolSize: 6 },
        { name: 'B 覆盖率', type: 'line', data: [42.7, 19.8, 9.8, 6.3], itemStyle: { color: accent2 + '99' }, lineStyle: { width: 2, type: 'dashed' }, symbolSize: 6 },
        { name: 'C 覆盖率', type: 'line', data: [47.8, 24.0, 11.6, 6.8], itemStyle: { color: accent }, lineStyle: { width: 3 }, symbolSize: 7 },
        { name: 'A 准确率', type: 'line', yAxisIndex: 1, data: [0.671, 0.787, 0.909, 0.989], itemStyle: { color: good }, lineStyle: { width: 2, type: 'dotted' }, symbolSize: 6 },
        { name: 'C 准确率', type: 'line', yAxisIndex: 1, data: [0.676, 0.776, 0.908, 0.992], itemStyle: { color: warn }, lineStyle: { width: 2, type: 'dotted' }, symbolSize: 6 }
      ]
    });
    window.addEventListener('resize', function () { c.resize(); });
  }

  /* ---------- 05 卡牌使用率 ---------- */
  var elCards = document.getElementById('chart-cards');
  if (elCards) {
    var c = echarts.init(elCards, null, { renderer: 'svg' });
    var cards = [
      ['1086 ポフィン', 94.4, true], ['1227 リーリエ', 93.9, true], ['1182 ボス指令', 92.1, true],
      ['1152 ポケパッド', 88.0, true], ['1097 夜のタンカ', 83.7, true], ['1080 スタンプ', 74.3, true],
      ['1122 ポケギア', 72.7, true], ['1231 ヒカリ', 71.6, false], ['1079 ふしぎなアメ', 67.9, true],
      ['1219 ラムダ', 67.2, true], ['860+104 ユキメノコ', 61.7, false], ['646-648 オーロンゲ', 61.9, true],
      ['1137 スクラッパー', 60.1, true], ['1225 トウコ', 34.0, false], ['1121 ハイパーボール', 29.0, false]
    ];
    c.setOption({
      animation: false,
      tooltip: TIP,
      grid: { left: 180, right: 40, top: 10, bottom: 40 },
      xAxis: Object.assign({}, AXIS, { type: 'value', max: 100, axisLabel: { color: muted, formatter: '{value}%' } }),
      yAxis: Object.assign({}, AXIS, { type: 'category', data: cards.map(function (x) { return x[0]; }) }),
      series: [{
        type: 'bar',
        data: cards.map(function (x) { return { value: x[1], itemStyle: { color: x[2] ? accent + '88' : accent2 } }; }),
        barWidth: 16,
        label: { show: true, position: 'right', color: muted, formatter: function (p) { return p.value.toFixed(1) + '%'; } }
      }]
    });
    window.addEventListener('resize', function () { c.resize(); });
  }

  /* ---------- 05.5 meta 演化趋势 ---------- */
  var elMeta = document.getElementById('chart-meta-trend');
  if (elMeta) {
    var c = echarts.init(elMeta, null, { renderer: 'svg' });
    c.setOption({
      animation: false,
      tooltip: TIP,
      grid: { left: 56, right: 56, top: 40, bottom: 40 },
      xAxis: Object.assign({}, AXIS, { type: 'category', data: ['0701', '0708', '0712', '0719', '0731'] }),
      yAxis: Object.assign({}, AXIS, { type: 'value', max: 70, name: '648 卡组占比 %', nameTextStyle: { color: muted }, axisLabel: { color: muted, formatter: '{value}%' } }),
      series: [{
        type: 'line',
        data: [14.7, 16.7, 9.5, 27.2, 61.9],
        itemStyle: { color: accent },
        lineStyle: { width: 3 },
        symbolSize: 9,
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: accent + '55' }, { offset: 1, color: accent + '05' }] } },
        label: { show: true, position: 'top', color: ink, fontFamily: 'Outfit', formatter: function (p) { return p.value.toFixed(1) + '%'; } }
      }]
    });
    window.addEventListener('resize', function () { c.resize(); });
  }

  /* ---------- 06 对阵胜率 ---------- */
  var elMu = document.getElementById('chart-matchup');
  if (elMu) {
    var c = echarts.init(elMu, null, { renderer: 'svg' });
    var data = [
      ['vs 648 镜像', 50.2, 3254], ['vs メガ+マント+トウコ', 54.5, 376],
      ['vs キチキギス+ノコ+ヒカリ+トウコ', 61.7, 227], ['vs トウコ系', 42.0, 250],
      ['vs ヒーローマント系', 36.4, 343], ['vs キチキギス+メガ', 34.9, 86],
      ['vs ノココッチ+トウコ', 39.8, 236], ['vs キチキギス+ヒカリ', 45.2, 239],
      ['vs キチキギス+ノコ+マシマシラ', 44.1, 68], ['vs other', 51.7, 60]
    ];
    data.sort(function (a, b) { return b[1] - a[1]; });
    c.setOption({
      animation: false,
      tooltip: Object.assign({}, TIP, { formatter: function (p) { return p.name + '<br>胜率 <b>' + p.value + '%</b><br>样本 ' + data[p.dataIndex][2] + ' 场'; } }),
      grid: { left: 250, right: 60, top: 10, bottom: 40 },
      xAxis: Object.assign({}, AXIS, { type: 'value', max: 70, axisLabel: { color: muted, formatter: '{value}%' } }),
      yAxis: Object.assign({}, AXIS, { type: 'category', data: data.map(function (x) { return x[0]; }) }),
      series: [{
        type: 'bar',
        data: data.map(function (x) {
          var col = x[1] >= 50 ? good : (x[1] >= 44 ? warn : bad);
          return { value: x[1], itemStyle: { color: col } };
        }),
        barWidth: 16,
        label: { show: true, position: 'right', color: muted, formatter: function (p) { return p.value.toFixed(1) + '%'; } }
      }]
    });
    window.addEventListener('resize', function () { c.resize(); });
  }

  /* ---------- 07 Bench 曲线 ---------- */
  var elBench = document.getElementById('chart-bench');
  if (elBench) {
    var c = echarts.init(elBench, null, { renderer: 'svg' });
    var T = [1, 2, 3, 4, 5, 6, 7, 8];
    c.setOption({
      animation: false,
      tooltip: TIP,
      legend: LEGEND,
      grid: { left: 50, right: 24, top: 40, bottom: 40 },
      xAxis: Object.assign({}, AXIS, { type: 'category', data: T.map(function (t) { return 'T' + t; }) }),
      yAxis: Object.assign({}, AXIS, { type: 'value', min: 2, max: 5, name: 'Bench 数量', nameTextStyle: { color: muted } }),
      series: [
        { name: '胜方', type: 'line', data: [2.60, 3.78, 4.32, 4.50, 4.48, 4.41, 4.38, 4.41], itemStyle: { color: good }, lineStyle: { width: 3 }, symbolSize: 7, areaStyle: { color: good + '22' } },
        { name: '负方', type: 'line', data: [2.48, 3.52, 3.97, 4.00, 3.81, 3.69, 3.70, 3.89], itemStyle: { color: bad }, lineStyle: { width: 3, type: 'dashed' }, symbolSize: 7 }
      ]
    });
    window.addEventListener('resize', function () { c.resize(); });
  }

  /* ---------- 08 奖赏+能量轨迹 ---------- */
  var elPrize = document.getElementById('chart-prize');
  if (elPrize) {
    var c = echarts.init(elPrize, null, { renderer: 'svg' });
    var T = [1, 2, 3, 4, 5, 6, 7, 8];
    c.setOption({
      animation: false,
      tooltip: TIP,
      legend: LEGEND,
      grid: { left: 50, right: 56, top: 44, bottom: 40 },
      xAxis: Object.assign({}, AXIS, { type: 'category', data: T.map(function (t) { return 'T' + t; }) }),
      yAxis: [
        Object.assign({}, AXIS, { type: 'value', min: 0, max: 7, name: '奖赏剩余', nameTextStyle: { color: muted } }),
        Object.assign({}, AXIS, { type: 'value', min: 0, max: 2.5, name: 'active 能量', nameTextStyle: { color: muted } })
      ],
      series: [
        { name: '奖赏·胜', type: 'line', data: [6.0, 6.0, 5.56, 4.66, 3.66, 2.92, 2.61, 2.59], itemStyle: { color: good }, lineStyle: { width: 3, type: 'dashed' }, symbolSize: 6 },
        { name: '奖赏·负', type: 'line', data: [6.0, 6.0, 5.73, 5.21, 4.61, 4.02, 3.75, 3.71], itemStyle: { color: bad }, lineStyle: { width: 3, type: 'dashed' }, symbolSize: 6 },
        { name: '能量·胜', type: 'line', yAxisIndex: 1, data: [0.18, 1.02, 1.64, 1.96, 2.00, 1.93, 1.81, 1.66], itemStyle: { color: accent }, lineStyle: { width: 3 }, symbolSize: 6 },
        { name: '能量·负', type: 'line', yAxisIndex: 1, data: [0.25, 0.93, 1.57, 1.83, 1.87, 1.76, 1.56, 1.43], itemStyle: { color: muted }, lineStyle: { width: 2 }, symbolSize: 5 }
      ]
    });
    window.addEventListener('resize', function () { c.resize(); });
  }

  /* ---------- 09 奖赏节奏 ---------- */
  var elPrize2 = document.getElementById('chart-prize2');
  if (elPrize2) {
    var c = echarts.init(elPrize2, null, { renderer: 'svg' });
    c.setOption({
      animation: false,
      tooltip: TIP,
      legend: LEGEND,
      grid: { left: 50, right: 24, top: 40, bottom: 40 },
      xAxis: Object.assign({}, AXIS, { type: 'category', data: ['第1张', '第2张', '第3张', '第4张', '第5张'] }),
      yAxis: Object.assign({}, AXIS, { type: 'value', min: 3, max: 7.5, name: '入手回合', nameTextStyle: { color: muted } }),
      series: [
        { name: '胜方', type: 'line', data: [3.91, 4.68, 5.35, 5.94, 6.37], itemStyle: { color: good }, lineStyle: { width: 3 }, symbolSize: 7, label: { show: true, color: ink, fontFamily: 'Outfit' } },
        { name: '负方', type: 'line', data: [4.24, 5.02, 5.69, 6.26, 6.91], itemStyle: { color: bad }, lineStyle: { width: 3, type: 'dashed' }, symbolSize: 7, label: { show: true, color: ink, fontFamily: 'Outfit' } }
      ]
    });
    window.addEventListener('resize', function () { c.resize(); });
  }

  /* ---------- 10 门控接管对比 ---------- */
  var elGate2 = document.getElementById('chart-gate2');
  if (elGate2) {
    var c = echarts.init(elGate2, null, { renderer: 'svg' });
    c.setOption({
      animation: false,
      tooltip: TIP,
      legend: LEGEND,
      grid: { left: 50, right: 24, top: 40, bottom: 40 },
      xAxis: Object.assign({}, AXIS, { type: 'category', data: ['种子123', '种子999'] }),
      yAxis: Object.assign({}, AXIS, { type: 'value', min: 0, max: 80, name: '专家一致率 %', nameTextStyle: { color: muted } }),
      series: [
        { name: 'v19 规则', type: 'bar', data: [34.5, 38.2], itemStyle: { color: bad }, barWidth: 40 },
        { name: 'v20 仅0731', type: 'bar', data: [65.9, 62.2], itemStyle: { color: accent + '99' }, barWidth: 40 },
        { name: 'v21 全版本', type: 'bar', data: [66.4, 62.9], itemStyle: { color: accent }, barWidth: 40 }
      ]
    });
    window.addEventListener('resize', function () { c.resize(); });
  }
})();
