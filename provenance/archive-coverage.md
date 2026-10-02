# 归档解包覆盖审计

审计日期：2026-10-01。范围是当前工作区的 95 个引擎/方言页面、实际 Python 源码和随包来源目录，包含尚未提交的模块。按实际接口和实现判断，不用目录名或 `unpack` 函数名推断支持；抛出 `NotImplementedError` 的入口不计作实现。没有执行商业游戏解包。

## 结论

- **49 个页面尚无归档模块**，当前只提供脚本、文本中间态、字段或脚本自身外壳的处理。下表列全；其中松散文件和中间态不能直接判定为“必须补一个 archives 才能提取”。
- **2 个页面已有归档局部算法，但缺少外层索引与成员提取链路**：SFA、SystemC。
- **另有 10 个页面已有容器索引或 writer，但通用成员解码仍有明确缺口**，单独列出，不能称为“只有脚本”。
- 其余 **34 个页面已有至少一种受限容器读取路线**；不代表覆盖全部版本、加密模式、剧本语义或游戏加载。

计数按页面而非厂商：Artemis 的 ASB、AST、SCP 是三个页面，共用 PFS。无归档模块的 49 项也不等于 49 个已证明需要归档的游戏格式。源码目录中的同族容器只作研究线索，不能据此认定当前脚本方言一定装在该包里。

## 尚无归档模块的 49 项

“待确认”指当前资料没有锁定该脚本方言的外层格式；不能拿同名、同后缀的其他引擎代替。

| 引擎页面 | 当前脚本侧能力 | 缺少的外层路线或需确认的条件 |
|---|---|---|
| [AGSI](../engines/agsi.md) | SB2 分段、CSTR 池读写 | 尚无容器读取；catalog 有 `PAK/AGSI` 线索，需匹配 SB2 方言 |
| [ANIM](../engines/anim.md) | DAT/SCE 滚动密钥与文本片段 | 外层包读取缺失，具体容器待确认；不能混用名称包含 ANIM 的动画格式 |
| [ArcGameEngine](../engines/arcgameengine.md) | AGE 字符串池 | 外层容器与完整 AGE VM 均未实现；具体归档待确认 |
| [AZSystem](../engines/azsystem.md) | ASB v1 包装与局部指令 | 缺归档读取；catalog 有 ARC/AZ 及加密变体线索 |
| [BlackRainbow](../engines/blackrainbow.md) | 分段脚本、文本 XOR、局部变长 | `script.dat` / `data.pak` 两种外层容器 |
| [BlueGale](../engines/bluegale.md) | BDT XOR 与 `indexwww.dat` 配套 | SNN/Inx 资源容器；脚本配套索引不是资源包解包器 |
| [Circus](../engines/circus.md) | MES token 子集 | DAT/PCK/CRM 容器 |
| [CScript](../engines/cscript.md) | 已解压 payload 的记录 | `scr.dat` 容器，以及尚未移植的脚本包装/LZSS；`unpack_script` 是拒绝入口 |
| [Cyberworks](../engines/cyberworks.md) | a0 的 S/T 长度块 | 本页 a0 块流可直接处理；若实际游戏另有 APP/DAT 等同族封装，须独立核对，不强行增加归档层 |
| [DigitalWorks](../engines/digitalworks.md) | 单条 TAK 文本指令 codec | TAK.BIN 读取、EXE 内索引定位及可能的 LZS 外壳 |
| [Entis GLS](../engines/entis-gls.md) | SRCXML 消息/选项 XML | NOA/DAT 容器；仅有 CSX 时还缺字节码转换 |
| [ExHibit](../engines/exhibit.md) | RLD op 子集、姓名表、有界 XOR | 先确认 RLD 是否为松散文件；GRP 是另一资源入口，不能当作必经剧本包 |
| [Favorite](../engines/favorite.md) | HCB 指令子集与地址修复 | 包内 HCB 需要 BIN/FVP 等匹配容器；外置 HCB 可绕过归档层 |
| [FrontWing](../engines/frontwing.md) | CSB 消息 | 资源 DAT 等外层容器，需核对具体版本 |
| [GSD](../engines/gsd.md) | 已 decode 的 v2 族 SPT 与姓名表 | GSP 解包及 SPT decode/encode；不能只补 GSP 就视作闭环 |
| [GxEngine](../engines/gxengine.md) | MWB 包装与字段 | GXP 索引、加密及成员读取 |
| [Hexenhaus](../engines/hexenhaus.md) | NORI 固定文本槽 | 归档读取；ARCC/WAG/BIN 等同族线索需匹配当前方言 |
| [ICE](../engines/ice.md) | 字表索引 token | GRP/HDJ 解包，以及配套字符表获取 |
| [Ivory](../engines/ivory.md) | fAGS OCB 分节与密码 | PK 归档 |
| [LiveMaker](../engines/livemaker.md) | 外部导出的 CSV | 原生 LSB 读取/编译与容器均缺；不是只差一次解包 |
| [Malie](../engines/malie.md) | 明文 UTF-16/data5 脚本 | LIB 等外包、Camellia 与游戏参数 |
| [Masys](../engines/masys.md) | MEG 表达式变换 | MGS 等归档 |
| [MED](../engines/med.md) | 已定位的 NUL 文本表 | 外层格式待确认；不能把 catalog 的同名资源格式自动认作本引擎 |
| [MoonHir](../engines/moonhir.md) | FBX 包装与文本块 | FPK 容器；FBX 解压仅是脚本成员外壳 |
| [Musica](../engines/musica.md) | SC 文本方言 | PAZ/PAK/DAT 的匹配容器读取 |
| [Mware](../engines/mware.md) | Squirrel literal 池与引用克隆计划 | 外层包待按游戏确认；完整 NUT 函数/引用解析也缺失 |
| [NekoSDK](../engines/nekosdk.md) | ADVSCRIPT2 显示与日志字段 | NEKOPACK |
| [NSystem](../engines/nsystem.md) | 地址表与独立消息记录 | 解包/解密未实现；FJSYS 是同族源码线索，不能与 VnSystem 混用 |
| [Overflow](../engines/overflow.md) | TextRes/Log XML 中间态 | 原始容器与二进制剧本转换；仅补归档仍不足 |
| [Propeller](../engines/propeller.md) | MSC 文本字段与样式 | 资源包未实现；MPK 等同族线索需核对，完整 MSC 指令解析也缺失 |
| [PureMail](../engines/puremail.md) | OBJ v1/v2 文本池 | DAT 容器与压缩；DAT 版本和 OBJ 版本分别确认 |
| [RealLive](../engines/reallive.md) | 引号 token 与消息片段 | SEEN 等封装、解压/解密；Siglus 的 `Scene.pck` 模块不能代替 |
| [RPG Maker](../engines/rpgmaker.md) | MV JSON / VX 转换中间态 | VX 等分支缺 RGSS 归档和原生 Marshal；松散 MV JSON 本身不要求归档解包 |
| [ScrPlayer](../engines/scrplayer.md) | SCR 字符串引用 | `pack` / `pac2` 容器及相应索引布局 |
| [ShSystem](../engines/shsystem.md) | 特定 scriptcall 消息 | 外层资源读取缺失；HIM4/HIM5 是同族线索，脚本 writer 也未实现 |
| [Silky](../engines/silky.md) | MAP 索引与 UTF-16 指针 | ARC/MFG 等容器；其他 MES 方言不在当前脚本实现中 |
| [StudioMiris](../engines/studiomiris.md) | SKMSd 文本资源表 | 从外包发现/解密 SKM 未实现，具体容器待确认 |
| [StudioPolaris](../engines/studiopolaris.md) | 明文 SCD_ 指令 | 外层资源包和加密未实现，具体容器待确认 |
| [SYSTEM-ε](../engines/system-epsilon.md) | 独立文本段和候选指针 | 容器、解密与完整记录定位均缺，外层待确认 |
| [SystemNNN](../engines/systemnnn.md) | NNN 定长槽、SPT 局部结构 | 没有资源归档读取；实际输入是否为松散脚本待确认 |
| [TmrHiro](../engines/tmrhiro.md) | TextScript i16 长度流 | 外层包未实现；catalog 有 PAC/TMR-HIRO，需核对游戏及 TextScript/CodeScript 配套 |
| [Triangle](../engines/triangle.md) | SD 的单条 TEXT/CHOICE | 外层资源包与全 SD 解析均缺，具体容器待确认 |
| [U-GOS](../engines/ugos.md) | `.o` 字节码引用与文本块 | DET 配对归档 |
| [Unison](../engines/unison.md) | VAL 分离字符串池 | VCT 容器 |
| [Unity/UTAGE](../engines/unity.md) | 提取后的 DAT 对齐字符串 | AssetBundle/serialized object 提取与对象还原；不是普通 DAT 归档 |
| [Violent BIN 规则](../engines/violent.md) | 只读 SJIS 候选扫描 | 尚未证明具体引擎/剧本语义，不能据此指定一个 archives 实现 |
| [Whale](../engines/whale.md) | 已解码文本行与 SELECT | 容器未实现，具体外层格式待确认 |
| [Yaneurao](../engines/yaneurao.md) | Itufuru 单条长度指令 | Itufuru 对应的归档索引/解码；不能混用所有 YaneSDK/Yaneurao 容器 |
| [Yuka](../engines/yuka.md) | YKS002 类型化文本池 | YKC/DAT 等外层归档，需核对实际版本 |

## 已有局部 archive 模块，但仍缺外层解包的 2 项

| 页面 | 已归入 archives 的实现 | 缺口 |
|---|---|---|
| [SFA](../engines/sfa.md) | FGA Huffman 单成员编解码 | FGA 链式索引块解析与成员枚举 |
| [SystemC](../engines/systemc.md) | ZLC2 literal 子集 | SystemB3 FPK 索引与真实 LZ 回指解码 |

## 有索引或 writer，成员解码仍不完整的 10 项

| 页面 | 已有归档能力 | 明确缺口 |
|---|---|---|
| [Ail](../engines/ail.md) | 大小表/stored 枚举、literal 封包 | 通用 Ail LZSS 解码 |
| [AST](../engines/ast.md) | ARC1/ARC2 索引与 stored | 成员压缩/编码层；不是 Artemis AST |
| [EmonEngine](../engines/emonengine.md) | 零密钥 Subtype=3 writer 与索引 | 通用 EME 解密/成员解压与其他 subtype |
| [HCSystem](../engines/hcsystem.md) | 索引与 raw 封包 | 压缩成员 LZSS |
| [Kaguya](../engines/kaguya.md) | LINK6 索引、flags=0 成员读取及保留头部的重封包 | 压缩/加密成员和其他 LINK 方言；独立 message.dat ver4 不必先经过 LINK |
| [Leaf](../engines/leaf.md) | KCAP 索引与 raw 封包 | 压缩成员 LZSS；SDT 剧本语义是另一缺口 |
| [M no Violet](../engines/mnoviolet.md) | DAT 索引、CScript 头部检查 | stored 成员的实际解压 |
| [NEJII](../engines/nejii.md) | CDT 索引/raw 封包、BIN 记录 | 压缩成员读取 |
| [SakanaGL](../engines/sakanagl.md) | 字密码、成员 key、明文索引解析 | SX/SXStorage 的 Zstandard、外层 key 与分卷衔接 |
| [U-MeSoft](../engines/umesoft.md) | PK 尾索引、literal 编解码 | 真实 LZ 回指解码 |

## 已有受限解包路线，未列入“只有脚本”

Artemis 三方言共用 PFS；BGI、CatSystem2 INT、Escu:de、Kirikiri XP3、Majiro、NScripter、Ren'Py RPA、Siglus 均已有对应归档实现。当前工作区新增的 **NeXAS PAC** 和 **QLIE FilePackVer3.0** 也已计入，不能按旧引擎页或未刷新目录误判为缺失；具体 codec、版本与密钥条件以当前引擎页为准。

**EAGLS** 已补 SCPACK.idx/PAK 的显式长/短偏移索引、尺寸/连续性检查和重封包，配套提取器处理选中成员；已从“只有归档局部算法”移出。**YU-RIS、WillPlus/AdvHD、Softpal** 本轮新增的读取范围见下节。

其余有受限读取路线的页面：AdvSys3、ARCX、FlyingShine、HotSoup、IKURA、Melonpan、Mirai、NonColor、Patisserie、Ransel、ScenePlayer、SLGSystem、Succubus、Tanaka、Winters、Xuse、Yatagarasu。它们可能仅支持明文、特定 key、无遮罩或某个版本，不能升级成全引擎支持。

## 本次模块整理

已将 **19 个纯归档模块**从 `python/engines/` 移入 `python/archives/`：advsys3、ail、arcx、ast、catsystem2_int、emonengine、hcsystem、hotsoup、ikura、leaf、mirai、noncolor、patisserie、ransel、sakanagl、sceneplayer、slgsystem、succubus、yatagarasu。

已拆分 **11 个混合模块**：eagls、flyingshine、melonpan、mnoviolet、nejii、sfa、systemc、tanaka、umesoft、winters、xuse。归档索引、成员 codec、封包进入 archives；脚本解析、正文变换及回填留在 engines。EAGLS 两层共用的 PRNG 由归档模块提供，脚本模块显式导入；归档层不反向依赖脚本层。

脚本自己的外壳仍随脚本模块保留，例如 AZSystem ASB、MoonHir FBX、GxEngine MWB；BlueGale 的 `indexwww.dat` 是 BDT 配套数据，不是 SNN 容器索引。

文档、源码调用、测试、catalog 和 provenance 已同步到新路径，没有保留旧位置的空转发模块。外部调用者需要更新 import；旧提取产物中的 `reference` 字段属于历史记录，不应靠目录迁移擅自改写。

## 首批常见引擎归档补充

本轮按“视觉小说中较常遇到，且已有脚本侧算法”选择三族，不将选择顺序当作市场份额排名。

| 引擎 | 新增归档能力 | 仍缺失的范围 |
|---|---|---|
| [YU-RIS](../engines/yuris.md) | YPF 七个明确版本、显式名字密钥/置换表、目录 extra 保留、raw/zlib、可选 CRC32/Adler32 | 其他方案、Snappy、EXE/YSER、自动猜 key、writer；YBN VM 仍为脚本侧缺口 |
| [WillPlus/AdvHD](../engines/willplus.md) | ARC v1 两种名字宽度、ARC/AR2 v2 UTF-16LE 索引；raw、ROR2、PSP 解码 | 自动识别、其他加密、writer；归档版本不证明 WS2 版本/尾部 |
| [Softpal](../engines/softpal.md) | PAC v1 的 16/32 字节名、PAC v2、raw/显式 `$` 成员解码 | VAFS、writer、完整 Sv20 与 TEXT 明文证明 |

三个模块均在 `python/archives/`，详细规则在各引擎页；`guides/` 未加入引擎专有内容，主 Skill 只刷新生成的目录标题。文件级出处见 [common-archives-v1.json](common-archives-v1.json)。

49 + 2 + 10 + 34 = 95 页。具体格式条件以各引擎页、模块源码及对应测试为准。
