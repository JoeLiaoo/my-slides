页面片段写在 `slides/pages/<单元>.html`。只写这一页的内容，不要写整份演示文稿的外壳、翻页按钮或导航脚本。构建后打开 `slides/previews/<单元>.html` 查看版式。主题是浅色 editorial-light，字体用系统字体，不要外链样式或字体。

使用下面这些静态结构。不要写点击事件，不要做翻转卡片。图表和图标继续用已批准 Spec 里的 JSON 标记，工具会把它们换成离线 SVG。

封面：

```html
<section class="slide" data-unit-id="单元ID" data-page-role="cover">
  <p class="slide-tag">章节名</p>
  <h1>页面标题</h1>
  <p>一句话结论</p>
  <script type="application/json" class="slide-notes">{"title":"页面标题","script":"口头要说的话","notes":["要点"]}</script>
</section>
```

指标卡：

```html
<section class="slide" data-unit-id="单元ID" data-page-role="content">
  <h2>关键指标</h2>
  <div class="stats-row">
    <div class="stat-card">
      <p class="stat-number blue">12%</p>
      <p class="stat-label">收入增速</p>
      <p class="stat-desc">来源与口径</p>
    </div>
  </div>
  <script type="application/json" class="slide-notes">{"title":"关键指标","script":"口头要说的话","notes":[]}</script>
</section>
```

双栏比较：

```html
<section class="slide" data-unit-id="单元ID" data-page-role="content">
  <h2>两种情形</h2>
  <div class="vs-container">
    <div class="vs-card card-left"><h3>情形 A</h3><p>说明</p></div>
    <div class="vs-card card-right"><h3>情形 B</h3><p>说明</p></div>
  </div>
  <script type="application/json" class="slide-notes">{"title":"两种情形","script":"口头要说的话","notes":[]}</script>
</section>
```

表格：

```html
<section class="slide" data-unit-id="单元ID" data-page-role="content">
  <h2>对照</h2>
  <div class="table-wrap">
    <table>
      <thead><tr><th>项目</th><th>数值</th></tr></thead>
      <tbody><tr><td>收入</td><td class="cell-highlight">10</td></tr></tbody>
    </table>
  </div>
  <script type="application/json" class="slide-notes">{"title":"对照","script":"口头要说的话","notes":[]}</script>
</section>
```

图表容器。标记内容必须与本页已批准 Spec 完全一致：

```html
<section class="slide" data-unit-id="单元ID" data-page-role="content">
  <h2>趋势</h2>
  <div class="chart-container">
    <script type="application/json" class="mls-echarts-spec">{"type":"bar","categories":["A"],"values":[1]}</script>
  </div>
  <script type="application/json" class="slide-notes">{"title":"趋势","script":"口头要说的话","notes":[]}</script>
</section>
```

小图标同样只放标记，不要自己写 SVG：

```html
<script type="application/json" class="mls-lucide-spec">{"name":"trending-up"}</script>
```
