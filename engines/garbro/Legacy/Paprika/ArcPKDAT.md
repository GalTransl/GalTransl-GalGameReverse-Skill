# Paprika / ArcPKDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/PAPRIKA` / `GameRes.Formats.Paprika.PkDatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PkDatOpener.TryOpen` | `uint index_pos = scn.ReadUInt32();` |
| `PkDatOpener.TryOpen` | `byte num = scn.ReadUInt8();` |
| `PkDatOpener.TryOpen` | `long offset = scn.ReadUInt32();` |
| `PkDatOpener.TryOpen` | `uint size = scn.ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Paprika.PkDatOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
string[] KnownPkList = new[] { null, null, null, "PICPK", "AVIPK", "MUSPK", "WAVPK" }
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var scn_name = VFS.ChangeFileName (file.Name, "SCNPK.DAT");
    if (!VFS.FileExists (scn_name))
        return null;
    var arc_name = Path.GetFileName (file.Name).ToUpperInvariant();
    var base_name = Path.GetFileNameWithoutExtension (arc_name);
    if (!char.IsDigit (base_name, base_name.Length - 1))
        return null;
    int arcId;
    for (arcId = 3; arcId < KnownPkList.Length; ++arcId)
    {
        if (KnownPkList[arcId] != null && arc_name.StartsWith (KnownPkList[arcId]))
            break;
    }
    if (arcId == KnownPkList.Length)
        return null;
    int arc_num = base_name[base_name.Length-1] - '0';
    var base_ext = arc_name.Substring (0, 3);
    using (var scn = VFS.OpenBinaryStream (scn_name))
    {
        scn.Position = arcId * 4;
        uint index_pos = scn.ReadUInt32();
        if (0 == index_pos)
            return null;
        scn.Position = index_pos;
        var dir = new List<Entry>();
        long last_offset = -1;
        int i = 0;
        while (scn.PeekByte() != -1)
        {
            ++i;
            byte num = scn.ReadUInt8();
            long offset = scn.ReadUInt32();
            uint size = scn.ReadUInt32();
            if (num != arc_num)
                continue;
            if (offset < last_offset)
                break;
            var name = string.Format ("{0:D4}.{1}", i - 1,  base_ext);
            var entry = Create<Entry> (name);
            entry.Offset = offset;
            entry.Size = size;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
            last_offset = offset;
        }
        if (dir.Count == 0)
            return null;
        return new ArcFile (file, this, dir);
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Paprika/ArcPKDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
