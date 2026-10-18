# VALKYRIA：DAT 容器与 SDT 文本片段

> 能力层级：`script-header-string-spans`。这是容器与文本片段级参考，不是完整 MICO VM 支持承诺。

## 识别与适用范围
- `.dat` 是固定 268 字节记录的归档；`.sdt` 是整文件 XOR 0xFF 的字节码脚本。
- 两者都没有可靠魔数：`.dat` 以“索引长度为 268 的整数倍”为首要条件，`.sdt` 以 XOR 后能
  连续命中 MICO 文本模式为条件；扩展名不能单独作为身份证明。
- 本页覆盖 DAT 目录读写与 SDT 的文本片段定位、定长回写。
- 不解释 MICO VM、不重建跳转地址、不处理图像/音频。

## DAT 容器
- 头部 `u32` 索引长度；必须非 0、可被 268 整除且不超过 4000 条。
- 每条记录：`char name[260]`（CP932，NUL 补齐）+ `u32 offset` + `u32 size`，均小端。
- `offset` 相对载荷起点；载荷起点为 `4 + 索引长度`。
- 名称必须在本记录内的 NUL 处结束；重名或越界成员拒绝。
- `build_dat` 按调用方顺序重算索引长度与相对偏移，重新解析并逐成员比对后才返回。
- 参考实现的打包路径把名称限制在 102 字节，本模块允许到 259 字节；更长的名称应实测。
- 不做：子目录、成员压缩、索引重排。

## SDT 脚本
- 整文件逐字节 XOR 0xFF；该变换自反，读写都只在内存副本上操作。
- 明文中的文本由四组双字节小端 opcode 携带：
  - `0xF1FE` + `u16 0xEEEE` + 4 字节 + NUL 结尾字符串：窗口正文。
  - `0xF58F` + `u16 0xF1FF` + NUL 结尾字符串：说话人姓名。
  - `0xF1FB` + 6 字节 + `u16 0xF1FF` + NUL 结尾字符串：带间接字段的姓名。
  - `0xF1E3` + `u32 0xFFFFFFFF` + 记录序列：每条为 1 个非零标记字节 + NUL 结尾字符串，
    遇到 0 标记结束；对应选择项。
- `0xF1FF` 不单独作为姓名扫描：参考实现的 `MSGWNDNAME` 分支因首字节不在扫描集合内而不可达。
- 未命中的字节逐个跳过；命中头部但字符串没有终止 NUL 时报错，不重同步。
- 因此输出是**候选片段集合**，必须结合上下文确认是否覆盖全部可见文本；不能把
  “扫描到 N 条”当作完整文本清单。
- 不做：指令语义、参数形状校验、跳转目标、选择分支结构、非 CP932 方言。

## 回写约束
- 只做定长替换：目标编码后不得长于原片段字节数，超长报错，不截断多字节字符。
- 短文本补 `0x20`；终止 NUL 保留在原位置。
- 空文本与含 NUL 的文本拒绝。
- 读取与写入编码必须由调用方保持一致（默认读取 CP932）；编码不一致时回读校验会失败，
  这是有意暴露配置错误，而不是静默接受乱码。
- 写入基于明文副本，重新 XOR 后输出；重新解析并比对片段种类、长度与文本。

## Python 接口
```python
from python.archives.valkyria import build_dat, open_dat, read_member
from python.engines.valkyria import open_sdt, write_sdt, xor_body

archive = open_dat(dat_bytes)
member = read_member(dat_bytes, archive.entries[0])
rebuilt = build_dat({"script.sdt": patched_sdt})

plain, spans = open_sdt(sdt_bytes)
patched = write_sdt(sdt_bytes, {0: "短い"}, write_encoding="cp932")
```

- `open_dat(data) -> DatArchive`；`read_member(data, entry) -> bytes`；`build_dat(members) -> bytes`。
- `xor_body(data) -> bytes`；`open_sdt(data, encoding="cp932") -> (plain, spans)`。
- `write_sdt(data, {span index: text}, read_encoding="cp932", write_encoding="gbk") -> bytes`。
- 函数不读写磁盘，不执行脚本。

## 部署条件
- DAT 成员名与顺序必须与原始索引一致，否则游戏可能找不到资源。
- SDT 片段长度由周围字节码决定，改长文本会移动全部后续指令，本模块不提供该能力。
- 编码成功不等于字体能显示；改编码不能解决缺字。
- 未确认 SDT 文本清单完整时，交付必须写明实际覆盖范围。

## 验证状态
- 合成测试覆盖 DAT 往返、相对偏移、索引长度与名称拒绝；SDT 四种片段形态、偏移定位、
  定长空格填充、超长拒绝、未终止字符串拒绝与 XOR 自反。
- 测试文件：[test_valkyria.py](../tests/test_valkyria.py)。
- 未使用真实 `.dat`/`.sdt` 样本，未运行游戏；测试通过不代表片段清单完整或显示正确。
- 未实现 MICO 指令语义、选择分支恢复、未知 opcode 形状。

## 来源与许可
- 依据：翻译肋手 v4.9D 的 `GameRes.VALKYRIA.ArcDAT` 与 `ArcSDT`（GARbro 派生）。
- 独立改写：显式 NUL 与边界检查、扫描失败不吞错、固定长度回写不截断；
  参考实现用 `IndexOf` 返回 -1 参与长度计算，本模块改为报错。
- 该来源未提供任何游戏内验证记录，格式细节仍需真实样本核对。
