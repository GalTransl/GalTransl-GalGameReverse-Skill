# NeXAS：PAC 尾索引与 BIN 字符串池回填

## 入口与范围

检查 PAC 前三字节 `PAC`、偏移 4 的成员数、偏移 8 的压缩类型及尾部索引。第四字节不一定为零，不能仅匹配 `PAC\0`。

- [PAC 读写](../python/archives/nexas.py)：64 字节名称、Huffman 尾索引方言；成员类型 0/5 原始、2 Huffman、3/4 zlib、6/7 Zstandard。尚不支持前置索引、旧版反码 PAC 或类型 1 LZSS。
- [BIN 读写](../python/engines/nexas_bin.py)：extras_count、extras、commands_count、8 字节指令对、strings_count、CP932 NUL 字符串、trailer。语义导出限定现有 `aikiss3-extras-v1` profile（代码标识，按下文指令形状匹配），未知 opcode、消息参数形状或控制码明确拒绝。
- [批量 CLI](../python/engines/nexas_extract.py)：按显式优先级读取多个包，导出 JSON、manifest、原文往返 PAC，并支持译文重封包。
- [旧 ASM 编辑器](../python/engines/nexas.py)：继续支持 SExtractor 根目录反汇编器的 ASM，其 assemble_bin() 仍未实现；新 BIN writer 不接受任意 ASM。

PAC 6/7 的 Zstandard 压缩读写需要可选 Python 包 **zstandard**（可用 python -m pip install zstandard 安装）；类型 7 的未压缩成员仍可直接读取。其他层使用标准库，导入模块或只读 PAC 索引不要求安装它。不调用游戏 EXE、补丁 DLL、GUI 或外部封包程序。静态检查器仅在本 PAC 模块中允许这一明确声明的可选依赖，并要求函数内延迟导入及 `ImportError` 处理；缺包时只在调用 Zstandard 功能时给出清楚的错误，不影响其他压缩类型。

## 核对补丁和 BIN 方言

先只读各 PAC 索引，不要为查剧本解压 Voice/Visual。read_index(stream) 不读取成员内容；选定条目再用 read_member(stream, index, entry)，有单项解压预算。

根据 `Config.pac` 中的 `packlist.dat` 等配置和实际文件核对加载顺序，再显式传入归档优先级。不要凭更新包编号猜测未存在的包或部署目标。

BIN 方言与 PAC 压缩类型没有对应关系。含 extras 的布局必须按 `extras_count` 读取完整字段，不假定首字为零，也不擅自添加或删除填充字。

## 导出与回封

从 skill 根目录运行，替换下面的示意路径。输出目录必须不存在，已存在时改用新名字。

~~~text
python -m python.engines.nexas_extract extract /path/to/game --output /path/to/game/game_extract --archives Script.pac Update3.pac
~~~

--archives 从低优先级到高优先级，后者覆盖同名成员，必须显式提供。输出目录包含：

| 目录 | 内容 |
|---|---|
| gt_input/ | 平铺的原剧本名.json，只输出有文本的脚本 |
| gt_output/ | GalTransl 译文，文件名和数组顺序不变 |
| original/archives/ | 所选输入 PAC 的完整副本 |
| original/scripts/ | 按覆盖顺序选出的原始 BIN |
| metadata/ | JSON 对应哈希、指令引用、字段和控制码契约 |
| roundtrip/ | 经过 BIN writer 和 PAC writer 的原文往返包 |
| reports/ | 索引、来源映射、逐包验证和 packlist 原始证据 |

译文按同名文件放回 `gt_output` 后告诉 agent，由 agent 校验并回写：

~~~text
python -m python.engines.nexas_extract pack /path/to/game/game_extract --output /path/to/game/game_extract/rebuilt
~~~

pack 验证原 PAC 哈希，并重新从 PAC 解析原文、定位器和 manifest；按文件名读取译文，缺少译文的成员保持原压缩 payload，未匹配 JSON 列入报告。译文只写回成员实际所属的高优先级包；底包旧版本不会被改成补丁版本。每个生成 PAC 都重读索引、解压被替换成员并比对，其余成员的压缩 payload 逐字节核对。--translations 只用于显式测试目录，正常流程使用 gt_output。

只生成副本，不覆盖安装目录。roundtrip 是原文验证产物，rebuilt 才是用户译文的候选包，两者都不自动部署或启动游戏。没有译文时 changed_scripts=0，不应称为汉化包。

## 语义与字符串引用

按指令调用点确定字段，不把短日文猜作人名，不把所有 LOAD_STRING 当对白：

| 指令形状 | 导出 |
|---|---|
| 两个 op=5,arg=1 单字符串参数，随后 FUNC 0x4006F | 姓名与正文，空姓名省略 |
| FUNC 0x4006F 前的已验证复合串接模式 | custom-message，保留 effect 和纯控制后缀 |
| 单字符串随后 FUNC 0x10071 | 追加对白，不猜姓名 |
| PUSH / LOAD_STRING / PUSH，随后 FUNC 0x30066 | 选项，数值参数保留 |
| op=0xE,arg 高字节=0x80 的单字符串参数 | special-text，空值和纯控制串不输出 |
| FUNC 0x20023/0x20075/0x20015/0x10017 的单字符串实参 | 已核对的 UI 提示 |

资源调用如 0x501D5 中的日文音效名、0xA004B 中的剧本文件名不会进入翻译队列。special-text 与 custom-message 可能引用同一原文但用于不同指令；保留每次引用，**不按正文去重**，翻译时注意保持这些副本文意一致。报告条数是可回填记录数，不是去重对白数。

BIN writer 不重排原字符串池、指令或 EXTRA 表。原文回填重新解析并序列化所有字符串，保留原 CP932 字节，避免 CP932 重复映射造成无修改也变字节。修改时追加新字符串，只改变对应 op=0 前缀的字符串 ID；其他资源引用相同旧槽时不会被连带修改。命令区长度和条目序号不变，跳转无需重定位。尾部数据按字符串表结束位置读取并整体保留，不能丢弃 dat0 对应内容，也不能把尾部调试变量名当对白。

## 控制码与编码

- JSON 保留 @v 八位语音号、@t 四位延时、@h 资源标识、@n/@k/@d、@m 两位参数、@i 两位参数；回填校验**完整序列与参数**，禁止增删或重排。
- @h 参数可为空，不能吞掉紧随其后的正文。
- 不把真实 CR/LF、TAB、NUL 写进字符串，换行用 @n。本 profile 未验证 Ruby 等其他标签，遇到时核查，不猜测跳过。
- 新文本须严格 CP932 编码且可反向解码为同一 Unicode 文本，不替换、不截断。中文字符集、字体与运行时适配是另一个阶段；已有汉化 EXE 不证明 writer 可以直接改用 GBK。
- 纯 name/message JSON 必须保持数组顺序，条数相同的重排无法自动证明身份正确。

## 验证

- [合成测试](../tests/test_nexas.py) 覆盖压缩、坏数据、共享引用、CP932 原字节、控制码/manifest 拒绝、补丁优先级与不覆盖输出。运行 python -m unittest discover -s tests -p test_nexas.py -v。

未启动游戏验证显示、换行、字体、存档兼容或运行时加载。成功范围是格式与文本往返，不能称为已验证可运行的中文补丁。

## 旧 ASM 路线与来源

旧 nexas.extract_fields() / replace_fields() 只改带地址标签、TAB 和已知助记符的字符串内部跨度。其姓名分类是上下文启发式，不能代替 BIN 语义。保留单引号、TAB、真实 CR/LF、NUL 的拒绝规则及字面量 \n；ASM、dat0、未匹配 JSON 和转换器须配套。不能改后缀得到 BIN，不能丢失上游 JSON 的 true/false 标记。

- GARbro-Mod [ArcPAC.cs](https://github.com/nanami5270/GARbro-Mod/blob/bc26d991ef5cdc0e1ecb32122ee9a48c3375750c/ArcFormats/Nexas/ArcPAC.cs) 与同提交 ArcFormats/HuffmanCompression.cs：PAC 布局、反码尾索引及压缩类型。morkt MIT 通知见 [MIT-GARbro](../provenance/licenses/MIT-GARbro.txt)。writer 和严格边界检查为本项目实现。
- BIN 布局和控制码资料来源为 SExtractor 的 NeXAS 工具，含 masagrator/NXGameScripts 来源链，按 GPL-3.0-only 保留归属；见 [许可与来源](../provenance/NOTICE.md)。
