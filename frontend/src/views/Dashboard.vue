<template>
  <div style="padding: 24px;  margin: 0 auto;">
    <!-- 标题与简介 -->
    <el-row :gutter="24">
      <el-col :span="24">
        <el-card shadow="never" style="margin-bottom: 24px;">
          <h2 style="margin: 0 0 8px 0;">📈 Strategy Forge 使用指南</h2>
          <p style="color: #606266; font-size: 15px; line-height: 1.8;">
            本平台用于<strong>黄金 ETF 联接基金（000217）的趋势择时策略</strong>研究。
            通过多源数据采集、因子工程、滚动 OLS 训练、回测评估与实盘模拟（含交易费用），
            帮助您量化验证交易思路，持续优化策略参数。
          </p>
        </el-card>
      </el-col>
    </el-row>

    <!-- 实验流程步骤条 -->
    <el-row :gutter="24">
      <el-col :span="24">
        <el-card shadow="never" style="margin-bottom: 24px;">
          <template #header>
            <span style="font-weight: 600; font-size: 16px;">🧪 实验流程动线</span>
          </template>
          <el-steps :active="activeStep" finish-status="success" align-center>
            <el-step v-for="(step, index) in steps" :key="index" :title="step.title"
              :description="step.shortDesc" @click.native="activeStep = index" style="cursor: pointer;" />
          </el-steps>

          <!-- 步骤详细信息 -->
          <div style="margin-top: 24px; background: #f9fafc; border-radius: 8px; padding: 20px;">
            <h4 style="margin-top: 0;">{{ steps[activeStep].title }} 详解</h4>
            <div style="font-size: 14px; color: #606266; line-height: 1.8;">
              <div v-html="steps[activeStep].detail"></div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 数据来源 -->
    <el-row :gutter="24">
      <el-col :span="24">
        <el-card shadow="never" style="margin-bottom: 24px;">
          <template #header>
            <span style="font-weight: 600; font-size: 16px;">📊 数据来源一览</span>
          </template>
          <el-table :data="dataSources" border stripe size="small">
            <el-table-column prop="name" label="数据项" width="200" />
            <el-table-column prop="source" label="来源 / 接口" width="250" />
            <el-table-column prop="desc" label="说明"  />
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 关键计算说明 -->
    <el-row :gutter="24">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header>
            <span style="font-weight: 600; font-size: 16px;">🔬 各阶段计算逻辑</span>
          </template>
          <el-collapse accordion>
            <el-collapse-item v-for="(calc, idx) in calculations" :key="idx" :title="calc.title">
              <div style="font-size: 14px; color: #606266; line-height: 1.8; white-space: pre-wrap;">{{ calc.content }}</div>
            </el-collapse-item>
          </el-collapse>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'Dashboard' })
import { ref } from 'vue'

const activeStep = ref(0)

const steps = [
  {
    title: '1. 数据采集',
    shortDesc: '多源数据更新',
    detail: `
      <p>从十余个数据源拉取黄金相关数据，支持全量/增量更新，后台异步执行。</p>
      <ul>
        <li>AU9999 分钟线 (5分钟线K线,华尔街见闻-上海金交所)<span class="file-tag">AU9999_SGE_10year_5min.csv</span> </li>
        <li>布伦特原油现货价格 (DCOILBRENTEU FRED API)<span class="file-tag">Brent_hist_df.csv</span> </li>
        <li>美债10年期利率 (DGS10 FRED API)<span class="file-tag">dgs10_hist_df.csv</span> </li>
        <li>美元指数 (DX-Y.NYB yfinance)<span class="file-tag">dxy_yfinance_hist_df.csv</span> </li>
        <li>ETF 518880日K线数据 (TickFlow)<span class="file-tag">fund_etf518880_tickflow.csv</span> </li>
        <li>国际金价日线数据 (gold-api.com)<span class="file-tag">gold_goldAPI_spot_hist_df.csv</span> </li>
        <li>华安黄金ETF联接C 000217 (AKshare)<span class="file-tag">huaan_gold_etf_c_hist_df.csv</span> </li>
        <li>SPDR黄金ETF持仓数据 (AKshare)<span class="file-tag">SPDR_Gold_Holdings.csv</span> </li>
        <li>中国黄金现货Au99.99 日线(AKshare)<span class="file-tag">spot_hist_sge.csv</span> </li>
        <li>美元兑人民币汇率 (CNY=X yfinance)<span class="file-tag">usdcny_df.csv</span> </li>
      </ul>
      <p>数据存储于 <code>1.OriginalData</code> 目录，更新后 WebSocket 实时通知。</p>
    `
  },
  {
    title: '2. 数据预处理',
    shortDesc: '清洗与重命名',
    detail: `
      <p>数据清洗：</p>
      <ul>
        <li>保留原始数据中可用的列</li>
        <li>对余下列重命名(日期列、数据列)</li>
        <li>提取价格列、计算 ETF 换算价格(ETF000217为1:270, ETF51880为1:100)</li>
      </ul>
      <p>数据存储于 <code>2.ProcessData</code>目录</p>
    `
  },
  {
    title: '3. 周频聚合',
    shortDesc: '因子计算',
    detail: `
      <p>
        <b>策略标的：华安黄金 ETF 联接 C（000217）</b>，
        其周度净值收益率 <span class="file-tag">nav_return</span> 是模型的预测目标（标签），
        所有因子均围绕该标的设计。
      </p>
      </br>
      <p>聚合流程：</p>
      <ul>
        <li>从AU9999 分钟线提取每日14时金价 <span class="file-tag">AU9999_SGE_10year_5min.csv</span></li>
        <li>从华安黄金ETF联接C数据提取标的000217的基金净值 <span class="file-tag">huaan_gold_etf_c_hist_df.csv</span></li>
        <li>加载其余宏观数据
          <span class="file-tag">gold_goldAPI_spot_hist_df.csv</span>
          <span class="file-tag">dxy_yfinance_hist_df.csv</span>
          <span class="file-tag">dgs10_hist_df.csv</span>
          <span class="file-tag">Brent_hist_df.csv</span>
          <span class="file-tag">SPDR_Gold_Holdings.csv</span>
        </li>
        <li>上述七项数据按照W-FRI进行聚合</li>
        <li>校验当周是否结束,移除不完整周的数据 (若聚合数据时未到周五,会将最后一天数据设置为本周周五,需要移除)</li>
        <li>前项填充低频数据
          <span class="file-tag">dxy</span>
          <span class="file-tag">us10y</span>
          <span class="file-tag">brent</span>
          <span class="file-tag">spdr_holdings</span>
        </li>
        <li>价格类周收益率参数计算
          <span class="file-tag">nav_return</span>
          <span class="file-tag">au_return</span>
          <span class="file-tag">gold_int_return</span>
        </li>
        <li>SPDR持仓变化量计算(并非变化率)
          <span class="file-tag">spdr_change</span>
        </li>
        <li>
          以
          <span class="file-tag">au_1400_price</span>
          计算趋势均线
          <span class="file-tag">au_ma26</span>
          进一步计算趋势信号
          <span class="file-tag">trend</span>
          (当周14:00金价是否高于其26周均线（周五14:00可知）)
        </li>
        <li>
          计算
          000217净值26周均线
          <span class="file-tag">nav_ma26</span>
          净值偏离度因子(当周nav与均线的偏离率)
          <span class="file-tag">deviation</span>
        </li>
        <li>
          创建新的实验或者覆盖更新旧实验周频数据
        </li>
      </ul>

      <p>因子总览（即模型实际使用的 <b>7 个因子</b> + 1 个辅助信号）：</p>
      <ul>
        <li>
          <b>趋势信号 <span class="file-tag">trend</span></b><br/>
          当周 14:00 金价是否高于其 26 周均线，<code>1</code>＝多头，<code>0</code>＝空头。
          用于在 Z‑Score 生成信号时过滤掉空头行情。
        </li>
        <li>
          <b>收益率类因子</b><br/>
          <span class="file-tag">au_return</span>（国内金价周收益率）、
          <span class="file-tag">gold_int_return</span>（国际金价周收益率）
        </li>
        <li>
          <b>宏观类因子</b><br/>
          <span class="file-tag">dxy</span>（美元指数）、
          <span class="file-tag">us10y</span>（10 年期美债利率）、
          <span class="file-tag">brent</span>（布伦特原油价格）
        </li>
        <li>
          <b>持仓类因子</b><br/>
          <span class="file-tag">spdr_change</span>（SPDR 黄金持仓每周变动量，非变动率）
        </li>
        <li>
          <b>估值类因子</b><br/>
          <span class="file-tag">deviation</span>＝(nav / nav_ma26 − 1) × 100，
          衡量联接基金净值偏离其 26 周均线的程度
        </li>
      </ul>

      <p>因子计算暂未用到数据:</p>
      <ul>
        <li>内场518880价格数据 来自TickFlow
          <span class="file-tag">fund_etf518880_tickflow.csv</span>
          518880价格与000217关联度不如现货AU9999 spot_hist_sge与000217高,目前用于后续金价展示页面
        </li>
        <li>AU9999日线数据 来自AKshare
          <span class="file-tag">spot_hist_sge.csv</span>
          AKshare现货接口不稳定,现有华尔街见闻的现货数据作为替代
        </li>
        <li>美元兑人民币汇率 来自yfinance
          <span class="file-tag">usdcny_df.csv</span>
          此前用于计算上海金相对于国际金价的折价溢价率因子，该因子与标的关联度较低已经不用,后续可以考虑用作国际金价换算
        </li>
      </ul>

      <p>输出到实验目录下 <code>3.Experiment/实验名/1.WeeklyData/weekly_data.csv</code></p>
    `
  },
  {
  title: '4. 训练/测试集划分',
  shortDesc: '构建因子 & 锁定分割日期',
  detail: `
      <p>对周频数据做特征工程并划分训练/测试集：</p>
      <ul>
        <li>
          加载实验目录下的周频数据
          <span class="file-tag">weekly_data.csv</span>
          ，读取全部历史周频记录。
        </li>
        <li>
          <b>构建滞后一期因子</b>：对以下7个因子列分别执行 <code>.shift(1)</code>，生成
          <span class="file-tag">{factor}_lag1</span> 列：
          <ul>
            <li><span class="file-tag">au_return</span> — 国内金价周收益率</li>
            <li><span class="file-tag">gold_int_return</span> — 国际金价周收益率</li>
            <li><span class="file-tag">dxy</span> — 美元指数</li>
            <li><span class="file-tag">us10y</span> — 美债利率</li>
            <li><span class="file-tag">brent</span> — 原油价格</li>
            <li><span class="file-tag">spdr_change</span> — SPDR 持仓周变化</li>
            <li><span class="file-tag">deviation</span> — 净值偏离度</li>
          </ul>
        </li>
        <li>
          <b>删除含有缺失值的行</b>：移除滞后产生的 NaN 行（含前25周因移动均线导致的空行），确保所有因子和标签
          <span class="file-tag">nav_return</span>
          完整。
        </li>
        <li>
          <b>锁定分割日期</b>：
          <ul>
            <li><b>首次划分</b>：按 <code>split_ratio</code>（默认70%）计算训练集索引，取训练集最后一天日期作为
              <span class="file-tag">split_cutoff_date</span> 存入数据库。
            </li>
            <li><b>增量更新</b>：后续调用时传入实验
              <span class="file-tag">exp_id</span>
              读取已存储的
              <span class="file-tag">split_cutoff_date</span>，按该日期严格划分：<b>训练集范围不变</b>，测试集自动扩展包含所有新数据。
            </li>
          </ul>
        </li>
        <li>
          输出训练集
          <span class="file-tag">train.csv</span>
          和测试集
          <span class="file-tag">test.csv</span>
          到实验的 <code>2.ModelData</code> 目录。
        </li>
        <li>
          更新数据库：记录分割路径、分割比例、因子列、标的、训练/测试集大小、训练/测试集起止日期、实验状态为“已分割”。
        </li>
      </ul>
      <p>标的列为 <span class="file-tag">nav_return</span>（联接基金周收益率），所有因子均已滞后一期，严格避免未来信息泄露。</p>
    `
  },
  {
    title: '5. 滚动 OLS 训练',
    shortDesc: '信号生成',
    detail: `
      <p>基于滚动窗口的普通最小二乘回归（OLS），对每个测试周预测联接基金周收益率，并通过 Z‑Score 与趋势过滤生成交易信号。</p>

      <p><b>核心参数（可配置）</b></p>
      <ul>
        <li>滚动窗口大小 <span class="file-tag">window</span>：控制每次训练使用的<b>最大</b>周数（默认 252 周，约 5 年）。若可用历史数据不足，则自动缩小为全部可用数据</li>
        <li>Z‑Score 窗口 <span class="file-tag">zscore_window</span>：用于标准化预测值的回溯周数（默认 52 周）</li>
        <li>买入阈值 <span class="file-tag">buy_threshold</span>：Z‑Score 高于此值且趋势为多头时买入</li>
        <li>卖出阈值 <span class="file-tag">sell_threshold</span>：Z‑Score 低于此值且趋势为多头时卖出</li>
        <li>强制全量训练 <span class="file-tag">force_full_train</span>：勾选后忽略已有模型，重新从头训练</li>
      </ul>

      <p><b>训练前准备</b></p>
      <ul>
        <li>从实验的 <code>2.ModelData</code> 获取数据集目录 <span class="file-tag">train.csv</span> 和 <span class="file-tag">test.csv</span>。</li>
        <li>判断是否增量训练</li>
        <ul>
            <li>校验是否启用全量训练</li>
            <li>校验分割日期<span class="file-tag">split_cutoff_date</span> 是否存在</li>
            <li>校验此前训练模型存储地址<span class="file-tag">train_model_dir</span> 是否存在</li>
            <li>校验旧预测集是否存在<span class="file-tag">predictions.csv</span> 是否存在</li>
          </ul>
      </ul>

      <p><b>全量训练流程</b></p>
      <ol>
        <li>提取因子列（所有 <span class="file-tag">{factor}_lag1</span> 列）和目标列 <span class="file-tag">nav_return</span>。</li>
        <li>最大滚动窗口校验, 防止超过训练集之和。</li>
        <li>对测试集中每一周（<b>滚动预测</b>）：
          <ul>
            <li>构建训练窗口：合并训练集 + 已预测的测试周（截至上周），若超过 <span class="file-tag">window</span> 则只保留最近数据。</li>
            <li>使用 <span class="file-tag">StandardScaler</span> 标准化特征，添加截距项。</li>
            <li>拟合 OLS 模型，预测当前周的 <span class="file-tag">predicted_return</span>。</li>
          </ul>
        </li>
        <li>计算 <b>Z‑Score</b>：对预测值序列，用过去 <span class="file-tag">zscore_window</span> 周的均值和标准差进行标准化。</li>
        <li>结合趋势列 <span class="file-tag">trend</span> 生成交易信号：
          <ul>
            <li>趋势为空头（trend=0）→ 信号置为 0（持有）</li>
            <li>Z‑Score > <span class="file-tag">buy_threshold</span> → 买入信号（1）</li>
            <li>Z‑Score < <span class="file-tag">sell_threshold</span> → 卖出信号（-1）</li>
            <li>否则 → 持有（0）</li>
          </ul>
        </li>
        <li>保存预测结果到 <span class="file-tag">predictions.csv</span>，最新一周信号到 <span class="file-tag">latest_signal.csv</span>。</li>
        <li>保存最终窗口的模型（标准化器 + 系数 + 最大训练窗口）到 <span class="file-tag">last_window_model.joblib</span>，用于增量训练。</li>
        <li>更新数据库：记录训练状态、训练阶段文件夹路径、模型文件路径、最大窗口大小、Zscore窗口大小、买/卖阈值、训练/测试样本数。</li>
      </ol>

      <p><b>增量训练流程</b>（当实验已锁定分割日期、已有模型文件且 predictions.csv 存在时自动触发）</p>
      <ol>
        <li>读取历史预测集 <span class="file-tag">predictions.csv</span>，得到最后预测日期 <span class="file-tag">last_pred_date</span>。</li>
        <li>从最新的 <span class="file-tag">test.csv</span> 中筛选出日期 > <span class="file-tag">last_pred_date</span> 的新数据。</li>
        <li>加载历史模型 <span class="file-tag">last_window_model.joblib</span>，构建历史窗口（训练集 + 已预测的测试集）。</li>
        <li>对新数据逐周执行与全量训练相同的滚动预测和信号生成。</li>
        <li>将新预测行追加到 <span class="file-tag">predictions.csv</span> 末尾，更新模型文件及数据库。</li>
        <li><b>关键优势</b>：历史信号完全不变，买卖点稳定，仅延伸未来信号。</li>
      </ol>

      <p>输出文件位于实验的 <code>2.ModelData</code> 目录，预测结果包含日期、趋势、预测值、Z‑Score、信号、净值、周收益率。</p>
    `
  },
  {
    title: '6. 回测评估',
    shortDesc: '绩效与净值',
    detail: `
      <p>基于滚动训练生成的预测信号，模拟周频策略交易，计算核心绩效指标并记录买卖点。</p>

      <p><b>回测流程</b></p>
      <ol>
        <li>
          从实验的 <code>2.ModelData</code> 目录读取
          <span class="file-tag">predictions.csv</span>，获取日期、信号
          <span class="file-tag">signal</span> 和周收益率
          <span class="file-tag">nav_return</span>。
        </li>
        <li>
          初始化策略净值 <code>strategy_nav = 1.0</code>，基准净值
          <code>benchmark_nav = 1.0</code>，起始仓位为空。
        </li>
        <li>
          <b>逐周模拟</b>：
          <ul>
            <li>计算<b>策略收益</b>：<code>strategy_ret = 当前仓位 × 本周收益率</code>，然后更新净值。</li>
            <li>计算<b>基准收益</b>：始终保持满仓，每周以全部净值参与收益。</li>
            <li>根据本周信号调整仓位：<br/>
              信号 = 1 → 满仓（1.0）<br/>
              信号 = -1 → 空仓（0.0）<br/>
              否则维持原仓位（0.0 或 1.0）。
            </li>
            <li>
              <b>记录买卖点</b>：当仓位发生改变时，记录交易日期和当时的策略净值。
              每笔买入和后续的第一笔卖出自动配对，生成交易对（含买入/卖出日期、价格、持有天数）。
            </li>
          </ul>
        </li>
        <li>
          回测完成后，生成净值曲线数据框，包含日期、
          <span class="file-tag">strategy_nav</span> 和
          <span class="file-tag">benchmark_nav</span>，
          保存为 <span class="file-tag">equity_curve.csv</span> 到实验的
          <code>3.BackTest</code> 目录。
        </li>
        <li>
          计算关键绩效指标（通过 <span class="file-tag">calc_performance</span> 函数）：
          <ul>
            <li>年化夏普比率（周收益均值 / 周收益标准差 × √52）</li>
            <li>最大回撤（净值 / 累计最高净值 − 1）</li>
            <li>年化收益率（(最终净值)^(52/总周数) − 1）</li>
          </ul>
          指标以 JSON 格式存入数据库的
          <span class="file-tag">backtest_performance_json</span> 字段。
        </li>
        <li>
          额外统计：交易次数（买入/卖出）、平均持有天数、当前仓位快照等，一并保存到数据库，供前端展示。
        </li>
      </ol>

      <p><b>重要说明</b></p>
      <ul>
        <li>
        信号由上周已知因子和本周才可知的趋势
        <span class="file-tag">trend</span>
        (当周14:00金价是否高于其26周均线（周五14:00可知）)
        共同产生，在回测中**本周信号即用于决定本周仓位**，符合实际交易逻辑（因子使用滞后值，无未来信息泄露）。</li>
        <li>买卖点使用策略净值记录，而非实际基金价格，方便与策略表现直接对比。</li>
      </ul>

      <p>回测结果可在前端“回测分析”页面查看，包括净值曲线、回撤曲线、绩效卡片和交易明细。</p>
    `
  },
  {
    title: '7. 实盘模拟',
    shortDesc: '真实交易成本',
    detail: `
      <p>模拟更贴近真实基金投资的资金曲线，考虑实际净值成交价格、赎回费用和先进先出（FIFO）卖出规则。</p>

      <p><b>前置条件</b></p>
      <ul>
        <li>实验必须已完成滚动OLS训练，且存在
          <span class="file-tag">predictions.csv</span>（预测信号）
          推荐执行回测后实盘，方便获取
          <span class="file-tag">equity_curve.csv</span>（回测净值曲线，用于三方对比）。
        </li>
      </ul>

      <p><b>模拟流程</b></p>
      <ol>
        <li>初始化：初始资金 默认<b>10,000 元</b>，份额为 0，空仓状态。</li>
        <li>逐周处理信号（与回测相同的周频数据）：
          <ul>
            <li>根据当前持仓份额和本周五的实际基金净值
              <span class="file-tag">nav</span>（从预测文件中提取），计算持仓市值和账户总资产。
            </li>
            <li>根据信号执行交易（全仓/空仓）：
              <ul>
                <li><b>买入信号（1）且现金充足</b>：用全部现金按当日净值买入份额，现金清零，记录买入日期、份额和净值到 FIFO 队列。</li>
                <li><b>卖出信号（-1）</b>：卖出所有<b>持有已满 7 天</b>的份额。
                  按 FIFO 顺序逐笔检查，对每一笔计算持有天数，并根据赎回费率扣除手续费：
                  <br/>• 持有 &lt; 7 天：1.5%
                  <br/>• 7 天 ≤ 持有 &lt; 30 天：0.1%
                  <br/>• 持有 ≥ 30 天：免费
                  <br/>手续费从卖出金额中扣除，剩余资金加回现金，同时减少相应份额。
                </li>
                <li>信号为 0 时维持原仓位。</li>
              </ul>
            </li>
            <li>记录本周五调仓完成后的账户快照（现金、份额、总资产），资产直接按照当天的净值价格计算，不会导致按收益率计算时错误将新买入份额计算收益的问题</li>
          </ul>
        </li>
        <li>模拟结束后，构建账户快照历史 DataFrame（日期、现金、份额、总资产，基准总资产），并计算每日<b>实盘净值</b>和<b>每日基准净值</b> = 资产 / 初始资金，</li>
      </ol>

      <p><b>绩效统计</b></p>
      <ul>
        <li>实盘净值序列的最终资产、最终净值、年化收益率、夏普比率、最大回撤、总手续费。</li>
        <li基准序列的最终资产、最终净值、年化收益率、夏普比率、最大回撤。</li>
        <li>回测模块的最终净值、回测模块的最终基准净值。</li>
      </ul>

      <p><b>交易统计与输出</b></p>
      <ul>
        <li>交易配对：按顺序将买入和卖出记录配对，计算每笔持有天数。若有尚未卖出的买入，作为“持仓中”单独记录。</li>
        <li>统计：买入/卖出次数、总交易次数、平均持仓天数、总手续费，以及信号分布（买入/卖出/持有各自周数）。</li>
        <li>生成最近 5 笔交易明细、最大回撤区间（起始日、结束日、回撤幅度）以及最终账户快照（现金、份额、总资产、仓位状态）。</li>
        <li>保存 CSV 文件：
          <span class="file-tag">account_snapshots.csv</span>（每周账户状态）和
          <span class="file-tag">all_trades.csv</span>（全部交易记录）。
        </li>
        <li>其余结构化的绩效、统计、回撤信息均存储到数据库（对应的 JSON 字段），供前端“实盘分析”页面直接展示。</li>
      </ul>

      <p>实盘分析页面支持查看实盘净值曲线、回撤曲线、现金与份额变化、基金净值走势（含买卖点），并可在净值曲线上叠加信号标注，完整呈现模拟结果。</p>
    `
  },
  {
    title: '8. 分析与优化',
    shortDesc: '信号时机 & 未来展望',
    detail: `
      <p><b>交易时机</b><br/>
      所有信号的生成依赖周五下午 14:00 的最新金价（以及其它截至该时点的数据）。
      因此，策略的<b>理论调仓窗口为周五 14:00 之后</b>。</p>

      <p><b>当前已实现</b><br/>
      每次增量训练后，系统会自动更新实验目录下的
      <span class="file-tag">latest_signal.csv</span>，
      其中包含最新一周的交易信号。您可以在前端实验文件浏览中直接查看，或通过后端 API 获取。</p>

      <p><b>下一步：实盘信号提醒模块（规划中）</b><br/>
      计划在仪表盘或独立页面中增加一个“本周信号”卡片：
      <ul>
        <li>在周五 14:00 后自动（或手动）触发增量训练；</li>
        <li>展示最新的信号（买入/卖出/持有）以及关键参考指标（如 Z‑Score、趋势方向）；</li>
        <li>提供音频或浏览器通知提醒，便于及时执行手工交易。</li>
      </ul>
      这一模块将使策略更贴近实际投资流程。</p>

      <p>此外，平台还支持：
      <ul>
        <li>通过回测/实盘分析页面，可视化净值曲线、回撤曲线、现金/份额变化、买卖点标记；</li>
        <li>实验总览对比不同参数组合的绩效（夏普、最大回撤、年化收益）；</li>
        <li>未来将接入大模型对话、智能调参等功能。</li>
      </ul></p>
    `
  }
]

const dataSources = [
  { name: 'AU9999 分钟线', source: '华尔街见闻（上海金交所）', desc: '5分钟K线，提取每日 14:00 金价' },
  { name: '布伦特原油现货价格', source: 'FRED API (DCOILBRENTEU)', desc: '每日价格' },
  { name: '美债10年期利率', source: 'FRED API (DGS10)', desc: '每日利率' },
  { name: '美元指数', source: 'yfinance (DX-Y.NYB)', desc: '每日收盘价' },
  { name: 'ETF 518880 日K线', source: 'TickFlow', desc: '场内 ETF 行情' },
  { name: '国际金价日线', source: 'gold-api.com', desc: '美元/盎司' },
  { name: '华安黄金ETF联接C (000217)', source: 'AKshare', desc: '联接基金单位净值' },
  { name: 'SPDR黄金ETF持仓', source: 'AKshare', desc: '每日总持有量（吨）' },
  { name: '中国黄金现货 Au99.99 日线', source: 'AKshare', desc: '每日收盘价（备用）' },
  { name: '美元兑人民币汇率', source: 'yfinance (CNY=X)', desc: '暂未用于模型，仅展示' },
]

const calculations = [
  {
    title: '趋势判断 (trend)',
    content: '计算金价 26 周简单移动平均线 (MA26)。\n当本周五 14:00 收盘价 > MA26 时，trend = 1（多头）；否则 trend = 0（空头）。'
  },
  {
    title: '净值偏离度 (deviation)',
    content: 'deviation = (nav / nav_ma26 - 1) × 100\n反映联接基金净值相对于其 26 周均线的偏离程度。'
  },
  {
    title: '滚动 OLS 与 Z-Score',
    content: '对每个测试周：\n1. 使用截至上周的数据（窗口大小可配）拟合 OLS 模型\n2. 预测本周的 nav_return\n3. 计算过去 zscore_window 周的均值与标准差，得到 Z-Score = (pred - μ) / σ\n4. 结合 trend 和买卖阈值生成信号（Z > 买入阈值 → 1；Z < 卖出阈值 → -1）'
  },
  {
    title: '买卖信号生成规则',
    content: '基于趋势信号 trend 和 Z-Score 生成最终交易信号：\n' +
      '1. 若 trend = 0（空头），直接输出信号 0（持有），避免在下跌趋势中交易。\n' +
      '2. 若 trend = 1（多头）：\n' +
      '   - 当 Z-Score > 买入阈值（默认 0.5）时，信号 = 1（买入）。\n' +
      '   - 当 Z-Score < 卖出阈值（默认 -0.5）时，信号 = -1（卖出）。\n' +
      '   - 否则信号 = 0（持有）。\n' +
      '买入/卖出阈值可通过前端参数配置调整。'
  },
  {
    title: '回测绩效指标',
    content: '策略净值 = (1 + 仓位 × 周收益率) 累乘\n基准净值 = 买入持有净值\n年化夏普 = (周收益均值 / 周收益标准差) × √52\n最大回撤 = min(净值 / 累计最高净值 - 1)'
  },
  {
    title: '实盘 FIFO 卖出规则',
    content: '按买入时间先后顺序卖出，每笔卖出计算持有天数，匹配赎回费率：\n持有 < 7天: 1.5%\n7天 ≤ 持有 < 30天: 0.1%\n持有 ≥ 30天: 0%'
  }
]
</script>

<style scoped>
/* 调整步骤条文字大小 */
:deep(.el-step__title) {
  font-size: 14px;
}
:deep(.el-step__description) {
  font-size: 12px;
}


</style>

<style>
.file-tag {
  /* 直接继承父级字体，和正文完全一致，无割裂感 */
  font-family: inherit;
  /* 字号仅比正文小1号，区分度适中不抢眼 */
  font-size: 12px;
  /* 淡灰背景，柔和不突兀 */
  background: #e2e5e7;
  color: #606266;
  /* 内边距收窄，更精致小巧 */
  padding: 1px 6px;
  border-radius: 3px;
  /* 行内块+基线对齐，和前后文字完美贴合 */
  display: inline-block;
  vertical-align: baseline;
  /* 左右留空隙，不和文字挤在一起 */
  margin: 0 4px;
  /* 避免文件名过长自动换行 */
  white-space: nowrap;
}
</style>