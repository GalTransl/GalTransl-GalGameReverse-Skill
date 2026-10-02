# Livemaker：外部导出的 Original text CSV 方言

## 能力边界
- 状态：`partial / converted-text-roundtrip`。
- Python：`python/engines/livemaker.py`。
- 仅覆盖来源 `CSV_Livemaker` 规则对应的 CSV 中间格式。
- 不处理原生 LSB 二进制、容器、脚本编译或游戏部署。
- 模块独立使用标准库 csv，不依赖 pandas 或 GalTransl。

## 输入识别
- 表头必须恰好有一列名为 `Original text`。
- 其右边必须存在目标列，对应来源 `writeOffset=1`。
- 所有行必须保持相同列数。
- 接受逗号 CSV 或显式制表符分隔符。
- 输入是已解码 Unicode 文本，最大八百万字符。
- 解析遵守引号和单元格内换行，不能按简单 split 拆逗号。

## 容器到中间格式
- 必须先用独立验证的 Livemaker 工具导出此 CSV。
- 不知道导出器版本或列语义时，不自动创建假表头。
- 源码规则仅提供二次文本提取路线，没有原生编译器。
- 本模块不会读取外部 `.lsb`、缓存或参考仓库。
- 需要保持导出记录与原剧本之间的 ID/顺序关系。

## 提取 name / message
- `extract_csv` 只读 `Original text` 列。
- 若单元格起始是 `【名字】`，拆为 name 和其余 message。
- 仅接受首部姓名括号，不从正文中间任意提取角色。
- 没有该前缀时输出空 name，表示当前方言中的旁白。
- 多行、逗号和引号都是单元格内容，不是记录分隔符。
- 输出 `row` 为从零开始的数据行号，不包含表头。
- `original` 保留完整单元格，方便外部审查和变更检测。

## 回填独有算法
- `rewrite_csv` 接收 `{row: {message, 可选 name}}`。
- 使用原始单元格的姓名结构重建目标单元格。
- 写入右邻列，绝不覆盖 `Original text`。
- 目标列即使已有过期文字，也不拿其字符位置当新定位基准。
- 禁止为原旁白凭空添加名字，避免导出方言被改变。
- 原 ID、其他列和未改行保持单元格语义相同。
- csv writer 正确引用含逗号、双引号与换行的字段。
- 文本级 quoting/换行可能重新格式化，不保证字节完全一致。

## Python 示例
```python
from python.engines.livemaker import extract_csv, rewrite_csv
csv_text = 'ID,Original text,Translation\r\n1,【仮名】試験,\r\n'
records = extract_csv(csv_text)
rebuilt = rewrite_csv(csv_text, {records[0]["row"]: {"message": "合成試験"}})
```
- `line_ending` 可显式选择 LF 或 CRLF。
- 输出仍是 Unicode CSV，外部写盘编码须和导入器约定一致。

## 控制码与部署条件
- 本模块只了解姓名前缀和 CSV 引用规则。
- 剧本内控制码、转义、ruby、等待或变量格式需要导出器契约。
- 不能把 CSV 能写回宣传为原生 LSB 已可回填。
- 缺少 CSV→LSB 编译、容器重封和版本兼容性验证。
- 字体、名字显示、换行与选择项均未进行真实游戏验证。
- 应先通过外部无改写导出/导入，再验证翻译链路。

## 来源、许可与测试
- SExtractor 提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 主要规则：`src/reg.yaml` 的 `CSV_Livemaker`。
- 右邻列写入语义：`src/extract_CSV.py`。
- 来源仓库 GPL-3.0，保留 satan53x / SExtractor 贡献者归属。
- 去除了 pandas、全局 ExVar 和项目配置依赖。
- 合成测试覆盖姓名、多行带逗号字段、原文列和其他列不变。
- 另测缺少目标列、为旁白加名字和空回填路径。
- 测试：`tests/test_engines_tools_b.py`，无原游戏数据或网络。
