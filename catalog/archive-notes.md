# 归档格式与解密资料

本入口收录 GARbro-Mod 各格式的布局和算法资料，包含尚无随包实现的格式。资料存在不代表 Python 已支持，更不代表剧情提取、回填、重封包或游戏显示已验证。使用时仍需按主 Skill 的预算、路径与新目录输出约定实施。

[完整格式索引](garbro-archive-index.md)覆盖来源版本的 681 个归档注册项，含 ArcFormats、Legacy 和 Experimental；每项链接包含字段读取表达式、读取/解密步骤及配套算法。先读 [算法摘录约定](../engines/garbro/reading.md)。

## 已补充的格式说明

| 格式族 | 随包说明 | 资料范围 |
|---|---|---|
| F&C / FC01 | [MRG、mrg0 与 MRG/2](../engines/fc01/archives.md) | 索引、key 派生、旋转/XOR、LZSS 和 range 解码；无随包实现 |
| AGSI | [PAK](../engines/agsi.md#pak-归档格式资料) | PACK 两种索引、DES 成员、LZSS；RLE 来源入口未实现 |
| BlueGale | [SNN/Inx](../engines/bluegale.md#snninx-归档格式资料) | 配套索引、名称编码、绝对跨度 |
| Circus | [DAT/PCK/CRM](../engines/circus.md#datpckcrm-归档格式资料) | 首/尾索引、名称表、偏移差分；CRM 为图像归档 |
| Favorite | [BIN/FVP 与 ACPXPK](../engines/favorite.md#binfvp-与-acpxpk-归档格式资料) | 两种索引、ACP 的变宽 LZW |
| Hexenhaus | [ARCC/ODIO/WAG](../engines/hexenhaus.md#arccodiowag-归档格式资料) | 结构块、名称 XOR、ROR4 与图像/音频边界 |

上表为另外整理的中文说明；完整格式与算法摘录见上方索引。中文说明来源及许可见 [记录](../provenance/garbro-archive-notes.json)，算法摘录的逐文件通知见 [出处](../provenance/garbro-archive-excerpts.json)。当前运行能力以各引擎页和实际模块为准。
