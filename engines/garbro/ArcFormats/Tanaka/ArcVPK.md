# Tanaka / ArcVPK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `VPK1` / `GameRes.Formats.Will.VpkOpener` | `vpk` | `56504b31`, `56504b30` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `VpkOpener.TryOpen` | `uint data_size = file.View.ReadUInt32 (4);` |
| `VpkOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `VpkOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (0xC);` |
| `VpkOpener.TryOpen` | `int version = file.View.ReadByte (3) - '0';` |
| `VpkOpener.TryOpen` | `var name = index.ReadCString (name_length);` |
| `VpkOpener.TryOpen` | `uint n1 = index.ReadUInt16();` |
| `VpkOpener.TryOpen` | `uint n2 = index.ReadUInt16();` |
| `VpkOpener.TryOpen` | `uint n3 = index.ReadUInt32();` |
| `VpkOpener.TryOpen` | `uint n2 = index.ReadUInt32();` |
| `VpkOpener.TryOpen` | `entry.Offset = index.ReadUInt32();` |
| `VpkOpener.TryOpen` | `entry.Size   = index.ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Will.VpkOpener

继承/接口：`ArchiveFormat`。

#### VpkOpener

```csharp
public VpkOpener () {
    Extensions = new string[] { "vpk" };
    Signatures = new uint[] { 0x314B5056, 0x304B5056 };
    ContainedFormats = new[] { "WAV" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint data_size = file.View.ReadUInt32 (4);
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count))
        return null;

    uint index_offset = 0x20;
    uint index_size = file.View.ReadUInt32 (0xC);
    if (data_size + index_size != file.MaxOffset)
        return null;
    long data_offset = index_offset + index_size;
    if (data_offset >= file.MaxOffset || data_offset <= index_offset)
        return null;
    int version = file.View.ReadByte (3) - '0';
    int name_length = version > 0 ? 4 : 2;
    using (var index = file.CreateStream (index_offset, index_size))
    {
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            var name = index.ReadCString (name_length);
            if (0 == name.Length)
                return null;
            uint n1 = index.ReadUInt16();
            if (version > 0)
            {
                uint n2 = index.ReadUInt16();
                uint n3 = index.ReadUInt32();
                name = string.Format ("{0}_{1:D2}_{2}_{3:D3}.wav", name, n1, n2, n3);
            }
            else
            {
                uint n2 = index.ReadUInt32();
                name = string.Format ("{0}_{1:D2}_{2:D3}.wav", name, n1, n2);
            }
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Offset = index.ReadUInt32();
            entry.Size   = index.ReadUInt32();
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        return new ArcFile (file, this, dir);
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Tanaka/ArcVPK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
