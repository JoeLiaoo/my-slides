页面片段写在 `slides/pages/<单元>.html`。只写这一页的内容，不要写整份演示文稿的外壳、翻页按钮或导航脚本。构建后打开 `slides/previews/<单元>.html` 查看版式。主题是浅色 editorial-light，字体用系统字体，不要外链样式或字体。

## 投资语义组件

组件样式属于 editorial-light，使用项目配置的品牌色和 `--mls-*` 主题 token。它们是静态 HTML/CSS；只在内容适合时选用，不为了复用而把不同信息塞进同一种布局。换成新的公司或项目时，只替换 HTML 内容，不新增专页 CSS。

### 竞争比较

输入：比较对象、同口径维度、各项证据、口径说明，以及有证据支撑时的判断。缺失的数据写“未提供”或省略该项，不写成 0，不排名。

```html
<div class="investment-comparison" aria-label="竞争比较">
  <article class="investment-comparison__item">
    <h3>公司 A</h3>
    <p><span class="investment-comparison__dimension">产品</span><br>已披露的产品定位与能力</p>
    <ul>
      <li>公开证据及其日期</li>
      <li><span class="investment-comparison__unknown">渠道数据未提供</span></li>
    </ul>
  </article>
  <article class="investment-comparison__item">
    <h3>公司 B</h3>
    <p><span class="investment-comparison__dimension">产品</span><br>同一口径下的产品定位与能力</p>
    <ul><li>公开证据及其日期</li></ul>
  </article>
</div>
```

比较对象较多、维度较多或文字较长时，使用普通表格并按内容拆页，不缩小字体或隐藏关键信息。判断只在证据充分时出现，并标明判断依据。

### 投资逻辑

输入：一条投资判断、支持判断的证据、成立条件；有实际反证时才展示反证。缺少其中一项时省略相应区域。

```html
<article class="investment-thesis">
  <p class="investment-thesis__claim">投资判断：有证据支持的一句话结论</p>
  <div class="investment-thesis__evidence">
    <span class="investment-thesis__label">支撑证据</span>
    <ul><li>可以追溯到本页来源的证据</li></ul>
  </div>
  <p class="investment-thesis__conditions">
    <span class="investment-thesis__label">成立条件</span>
    条件及其依据
  </p>
</article>
```

此组件不等同于默认的结论卡片；判断页是否需要作者观点仍按 Spec 的“章节收束页 / 关键页”规则决定。

### 风险分析

输入：真实提出的风险、触发条件、影响、待核实事项。没有证据来源的概率、评分和缓释结论不展示。

```html
<div class="investment-risk" aria-label="风险分析">
  <article class="investment-risk__item" data-severity="watch">
    <span class="investment-risk__label">风险</span>
    <h3>客户集中度</h3>
    <p><strong>触发条件：</strong>最大客户续约变化</p>
    <p><strong>影响：</strong>收入波动；量化影响待核实</p>
    <p><strong>待核实：</strong>客户收入占比与续约周期</p>
  </article>
</div>
```

`data-severity` 只控制已有文字所表达的视觉提示（`high` / `watch`）；它不表示量化风险评分。多个风险可并列；信息较多时使用表格或拆页。

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
