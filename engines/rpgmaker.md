# RPG Maker：MV JSON 与 VX Marshal 转换中间态

## 版本与目录识别
- 本页合并 SExtractor `Engine_RPGMV` 与 `Engine_RPGVX`，但保留两者差异。
- MV 常见 `data/*.json`，随 NW.js 部署时也可能位于 `www/data/`。
- 文件应具有事件列表、code/parameters 等真实结构，不以扩展名独断。
- VX Ace 常见 `.rvdata2`，VX 为 `.rvdata`，XP 为 `.rxdata`。
- 这些不是 JSON；它们使用 Ruby Marshal 对象序列化。
- 上游工具 README 只确认 rvdata2 测试，rvdata/rxdata 标为未测试。
- 本页不把 MV 支持扩展为所有 MZ 插件或全部 Ruby 世代。
- 外层 RGSS 加密容器/资源解密不在本 leaf 范围。

## VX 必需的转换阶段
- `tools/RPGMakerVX/rvdata_to_json.py` 使用 rubymarshal reader/writer。
- 从二进制 `reader.loads` 得对象，再 `to_dict` 转换为中间 JSON。
- 写回须反向 `from_dict` 恢复 Ruby 对象后再 `writer.writes`。
- 中间 JSON 必须保留 `ruby_class`、`class`、Symbol 和对象属性。
- Ruby 属性通常带 `@`，事件字段因而是 `@code/@parameters`。
- Table/Color/Tone 明确配置为保留 bytes，不能当 UTF-8 台词解码。
- 无法作为 UTF-8 的字节数据可表示为 base64 `bytes` 包装。
- 可作为 UTF-8 的原 bytes 可表示为 `bytes_str`，该包装也不能丢。
- 源工具跳过 `Scripts` 文件，不能把游戏 Ruby 程序作为普通台词翻译。
- [load_ruby_marshal](../python/engines/rpgmaker.py#L174) 与 [dump_ruby_marshal](../python/engines/rpgmaker.py#L178) 在此明确拒绝。
- leaf 没有对象链接/符号表/类还原 codec，绝不把 json.dumps 输出冒充 rvdata。

## 类型保持的提取
- [extract_fields](../python/engines/rpgmaker.py#L61) 输入 JSON-native dict/list 树。
- `variant='mv'` 使用 code/parameters，`variant='vx'` 使用带 @ 前缀的字段。
- 路径保留字符串 key 和整数 list index 的类型，不拼成含糊的点路径。
- 事件 code 必须是 int，不把 bool 误当 int。
- 事件 parameters 必须保持 list，choice 参数必须保持嵌套 list。
- 非字符串、None、数值参数、indent 与原事件顺序不改动。
- 默认只提取经核实的安全槽位，不照搬上游所有被标记为文本的 code。
- code 401 / 405：parameters[0]，分别为显示文本与滚动文本。
- code 102：parameters[0] 中的选择字符串。
- code 320 / 324：parameters[1]，改名/昵称事件的文本值。
- 102 的取消分支、默认项和位置等数值参数不能一起翻译。
- code 101 可能带脸图文件名，默认不翻译。
- code 355/655 是脚本代码，108/408 是注释，默认不翻译。
- 上游表对这些 code 的提取标记不是“可以无条件交给翻译器”的保证。
- 非事件数据库文字通过显式 keys，例如 name/description/nickname 选择。
- Ruby Symbol 的 name 是类型元数据，不能因 keys 包含 name 而提取。
- `bytes` 包装保持不透明；目标字段的 `bytes_str` 可提取内部文本而保留包装。

## name/message 与控制码
- 401 通常是 message，不能仅因短句就自动改成姓名。
- 源 MV 预设还通过 `姓名：` 的形式拆 name，这是可选文本策略。
- VX 源预设使用颜色控制段中的名字形式，不能跨所有游戏套用。
- `\V[n]`、`\N[n]`、`\C[n]`、图标和等待控制需按原文保留。
- leaf 不解释或执行事件内容，也不自动清理这些控制串。
- 源临时 `<code401>` 标签仅用于提取展示，不存在于原 JSON。
- 因而不能把这些标签写进译文，也不能把事件 code 丢掉只存台词数组。

## 安全修改结构树
- [apply_translations](../python/engines/rpgmaker.py#L121) 接受 typed path 到 str 的映射。
- 仅允许修改本次提取白名单内路径，不允许替换 code、indent 或未选参数。
- 函数复制输入，不原地改变调用者的原树。
- 新值必须保持 str，数字、字典或 list 不能作为译文写入。
- 最大深度及节点数有限，循环结构或非 JSON 对象会被拒绝。
- 大多数场景返回的仍是 JSON 数据结构，落盘序列化属于公共层职责。

## 插件中的“JSON 字符串”
- 一些字段本身是 str，却保存一段 JSON 对象或数组文本。
- 这种 encoded JSON 与原生 dict/list 类型不可混淆。
- [expand_json_strings](../python/engines/rpgmaker.py#L140) 只展开显式给定路径。
- 先处理外层再处理其内部路径，同时记录每个原始 str 边界。
- 每个边界保存原词法文本与解码树，不对所有形似 JSON 的字符串自动处理。
- [restore_json_strings](../python/engines/rpgmaker.py#L161) 按最深边界优先恢复。
- 只把当初确实是 str 的节点重新序列化为 str。
- 原生数组中的 dict 仍是 dict，不会全部被递归转成字符串。
- 没有改变的边界直接恢复原文本，保留其空白排版。
- 根类型被改坏时拒绝；改过的边界以标准 JSON 严格序列化。
- 这是针对源递归 `dumps` 可能改变原生容器类型的明确修正。

## 调用示意
```python
from python.engines import rpgmaker
fields = rpgmaker.extract_fields(tree, variant="mv", keys=("name", "description"))
new_tree = rpgmaker.apply_translations(tree, {fields[0].path: "译文"},
                                      variant="mv", keys=("name", "description"))
```
- VX 调用必须传 variant='vx'，并保存完整转换中间态，不抽成纯台词表。
- 对 embedded JSON 应先显式展开、编辑，再按 boundaries 恢复。
- 原始 JSON 词法排版与结构语义是不同层；非 embedded 根树不保证字节级同排版。

## 部署与缺口
- MV 输出应返回原 data 层对应文件，不能破坏 null 占位和数据库 ID。
- VX 输出仍是 converter JSON，必须交给匹配 Ruby Marshal writer。
- 必须检查 Marshal 往返的 class/symbol/bytes/对象引用语义，失败则停止。
- 本包不包含 Ruby Marshal writer 或 RGSS archive writer。
- 保存事件 code 和 JSON 类型不等于保证游戏插件/私有 Marshal 类已支持。
- 无真实游戏端到端测试；不宣称能直接生成可运行 rvdata。

## 验证与来源
- 合成测试验证事件 code、数值参数、嵌套 choices、输入不变及受保护字段。
- 验证多层 encoded JSON 恢复时原生 list/dict 不变，未改边界词法一致。
- VX 测试保留 ruby_class、bytes_str、Table bytes 和 Symbol name。
- 测试明确拒绝坏事件类型、非法边界以及未实现 Marshal API。
- SExtractor commit `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 来源：`src/extract_RPGMV.py`、`extract_RPGVX.py`、`engine.ini`、`reg.yaml`。
- 转换来源：`tools/RPGMakerVX/rvdata_to_json.py` 与 `rubymarshal/classes.py`。
- 原 README 归属 [d9pouces/RubyMarshal](https://github.com/d9pouces/RubyMarshal)，其独立许可需另核实。
- [固定提取源码](https://github.com/satan53x/SExtractor/blob/8d8d976fd04ae54e7c677705af937273d04a376a/src/extract_RPGMV.py)。
- 本 Python 改编按 SExtractor GPLv3 标 GPL-3.0-only；未内置 RubyMarshal 第三方库。
- 精确符号及范围见 [provenance](../provenance/sextractor-core.json)。
