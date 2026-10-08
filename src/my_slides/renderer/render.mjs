import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

const input = JSON.parse(readFileSync(0, 'utf8'));
const runtime = process.env.MY_SLIDES_RENDERER_HOME;
if (!runtime) throw new Error('MY_SLIDES_RENDERER_HOME is not set');
const brandColor = /^#[0-9a-fA-F]{6}$/.test(input.brandColor || '') ? input.brandColor : '#A6192E';
const require = createRequire(`${runtime}/package.json`);
const echarts = require('echarts');

function finiteValues(values, name) {
  if (!Array.isArray(values) || values.length === 0) throw new Error(`${name} must be a non-empty array`);
  if (values.some(value => typeof value !== 'number' || !Number.isFinite(value))) {
    throw new Error(`${name} must contain only finite numeric values; missing values cannot be converted to zero`);
  }
}

function buildOption(spec, themeColor) {
  const { type, categories, series, values, unit = '', xUnit = '', yUnit = '' } = spec;
  const base = {
    animation: false,
    backgroundColor: 'transparent',
    aria: { enabled: true, decal: { show: false } },
    textStyle: { fontFamily: 'Arial, Microsoft YaHei, sans-serif', color: '#27272a' },
    title: spec.title ? { text: spec.title, left: 'center', textStyle: { fontSize: 18, fontWeight: 600 } } : undefined,
    tooltip: { trigger: type === 'scatter' || type === 'time-scatter' ? 'item' : 'axis' },
    grid: { left: 68, right: 36, top: spec.title ? 66 : 36, bottom: 62, containLabel: true },
    legend: series?.length > 1 ? { bottom: 4, type: 'scroll' } : undefined,
    xAxis: undefined,
    yAxis: undefined,
    series: [],
  };
  const categoryAxis = { type: 'category', data: categories, axisLabel: { interval: 0, hideOverlap: true }, axisLine: { lineStyle: { color: '#a1a1aa' } } };
  const valueAxis = { type: 'value', name: unit, nameLocation: 'end', splitLine: { lineStyle: { color: '#e4e4e7' } } };

  if (['bar', 'dot', 'line'].includes(type)) {
    if (!Array.isArray(categories) || categories.length === 0) throw new Error('categories must be a non-empty array');
    finiteValues(values, 'values');
    if (categories.length !== values.length) throw new Error('categories and values must have the same length');
    if (type === 'bar') {
      base.xAxis = categoryAxis; base.yAxis = valueAxis;
      base.series = [{ type: 'bar', data: values, barMaxWidth: 42, itemStyle: { color: themeColor, borderRadius: [3, 3, 0, 0] }, label: { show: true, position: 'top' } }];
    } else if (type === 'line') {
      base.xAxis = categoryAxis; base.yAxis = valueAxis;
      base.series = [{ type: 'line', data: values, smooth: false, showSymbol: true, symbolSize: 8, lineStyle: { color: themeColor, width: 3 }, itemStyle: { color: themeColor } }];
    } else {
      base.xAxis = valueAxis; base.yAxis = { ...categoryAxis, inverse: true };
      base.series = [{ type: 'scatter', data: values.map((value, i) => [value, categories[i]]), symbolSize: 13, itemStyle: { color: themeColor }, label: { show: true, position: 'right', formatter: p => String(p.value[0]), rich: { c: { color: '#52525b' } } } }];
    }
  } else if (['multi-line', 'stacked-bar'].includes(type)) {
    if (!Array.isArray(categories) || categories.length === 0 || !Array.isArray(series) || series.length === 0) throw new Error('categories and series must be non-empty arrays');
    for (const item of series) {
      finiteValues(item.values, `series ${item.name}`);
      if (item.values.length !== categories.length) throw new Error(`series ${item.name} length does not match categories`);
      if (item.unit !== undefined && item.unit !== unit) throw new Error(`unit mismatch in series ${item.name}`);
    }
    base.xAxis = categoryAxis; base.yAxis = valueAxis;
    base.series = series.map((item, i) => ({ name: item.name, type: type === 'multi-line' ? 'line' : 'bar', data: item.values, ...(type === 'multi-line' ? { showSymbol: true, symbolSize: 6, lineStyle: { width: 2 } } : { stack: 'total', barMaxWidth: 44 }), itemStyle: { color: [themeColor, '#2563A6', '#4F7A64', '#D18A3A', '#8064A2'][i % 5] } }));
  } else if (type === 'scatter' || type === 'time-scatter') {
    if (!Array.isArray(spec.points) || spec.points.length === 0) throw new Error('points must be a non-empty array');
    for (const point of spec.points) {
      if (typeof point.y !== 'number' || !Number.isFinite(point.y)) throw new Error('scatter y coordinates must be finite numbers');
      if (type === 'scatter' && (typeof point.x !== 'number' || !Number.isFinite(point.x))) throw new Error('scatter x coordinates must be finite numbers');
      if (type === 'time-scatter' && (!point.date || Number.isNaN(Date.parse(point.date)))) throw new Error('time-scatter points require a valid date');
    }
    base.xAxis = { type: type === 'time-scatter' ? 'time' : 'value', name: xUnit, splitLine: { lineStyle: { color: '#e4e4e7' } } };
    base.yAxis = { ...valueAxis, name: yUnit };
    base.series = [{ type: 'scatter', data: spec.points.map(p => type === 'time-scatter' ? [p.date, p.y, p.name || ''] : [p.x, p.y, p.name || '']), symbolSize: 12, itemStyle: { color: themeColor, opacity: 0.84 }, label: { show: Boolean(spec.labelPoints), formatter: p => p.value[2] || '' } }];
  } else if (type === 'waterfall') {
    if (!Array.isArray(categories) || !Array.isArray(values) || categories.length !== values.length || !categories.length) throw new Error('waterfall categories and values must have equal non-empty lengths');
    if (values.some(v => typeof v !== 'number' || !Number.isFinite(v))) throw new Error('waterfall values must be finite numbers');
    const totals = Array.isArray(spec.totals) ? spec.totals : [];
    const helper = []; const increase = []; const decrease = [];
    let running = 0;
    values.forEach((value, i) => {
      if (totals.includes(i)) {
        helper.push(0); increase.push(value); decrease.push('-'); running = value;
      } else if (value >= 0) {
        helper.push(running); increase.push(value); decrease.push('-'); running += value;
      } else {
        helper.push(running + value); increase.push('-'); decrease.push(-value); running += value;
      }
    });
    base.xAxis = categoryAxis; base.yAxis = valueAxis;
    base.series = [
      { type: 'bar', stack: 'waterfall', itemStyle: { color: 'transparent' }, emphasis: { itemStyle: { color: 'transparent' } }, data: helper },
      { name: '增加', type: 'bar', stack: 'waterfall', data: increase, itemStyle: { color: '#4F7A64' } },
      { name: '减少', type: 'bar', stack: 'waterfall', data: decrease, itemStyle: { color: themeColor } },
    ];
  } else {
    throw new Error(`unsupported chart type: ${type}`);
  }
  return base;
}

function renderChart(spec, themeColor) {
  const width = Number.isInteger(spec.width) ? spec.width : 1100;
  const height = Number.isInteger(spec.height) ? spec.height : 560;
  if (width < 320 || width > 1800 || height < 240 || height > 1000) throw new Error('chart dimensions are outside the allowed range');
  const chart = echarts.init(null, null, { renderer: 'svg', ssr: true, width, height });
  try {
    chart.setOption(buildOption(spec, themeColor), { notMerge: true });
    return chart.renderToSVGString();
  } finally { chart.dispose(); }
}

function renderIcon(spec, themeColor) {
  const iconName = String(spec.name || '');
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(iconName)) throw new Error('Lucide icon name must be kebab-case');
  const entry = require.resolve('lucide-static');
  const root = entry.replace(/[\\/]dist[\\/].*$/, '');
  const path = `${root}/icons/${iconName}.svg`;
  let svg;
  try { svg = readFileSync(path, 'utf8'); } catch { throw new Error(`unknown Lucide icon: ${iconName}`); }
  const size = Number.isInteger(spec.size) ? Math.min(96, Math.max(12, spec.size)) : 24;
  if (spec.color && !/^#[0-9a-fA-F]{6}$/.test(spec.color)) throw new Error('Lucide icon color must be #RRGGBB');
  const color = spec.color || themeColor;
  const strokeWidth = Number.isFinite(spec.strokeWidth) ? Math.min(3, Math.max(1, spec.strokeWidth)) : 2;
  return svg.replace(/<svg\b([^>]*)>/, (_match, attrs) => {
    const clean = attrs.replace(/\s(?:width|height|stroke|stroke-width|class|style)="[^"]*"/g, '');
    return `<svg${clean} width="${size}" height="${size}" stroke="${color}" stroke-width="${strokeWidth}" role="img" aria-label="${iconName}">`;
  });
}

const output = {};
for (const asset of input.assets) {
  output[asset.id] = asset.kind === 'chart' ? renderChart(asset.spec, brandColor) : renderIcon(asset.spec, brandColor);
}
process.stdout.write(JSON.stringify({ rendered: output }));
