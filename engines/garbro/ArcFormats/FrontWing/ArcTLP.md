# FrontWing / ArcTLP：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAC/TLP` / `GameRes.Formats.FrontWing.TlpOpener` | `pac` | `544c505f` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `TlpOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "DAT"))` |
| `TlpOpener.TryOpen` | `int count = file.View.ReadInt32 (0x10);` |
| `TlpOpener.TryOpen` | `var index = file.View.ReadBytes (0x20, (uint)index_size);` |
| `TlpOpener.TryOpen` | `byte type = file.View.ReadByte (0x18);` |
| `TlpOpener.TryOpen` | `entry.Offset = LittleEndian.ToUInt32 (index, index_offset + 0x104);` |
| `TlpOpener.TryOpen` | `entry.UnpackedSize = LittleEndian.ToUInt32 (index, index_offset + 0x108);` |
| `TlpOpener.TryOpen` | `entry.Size = LittleEndian.ToUInt32 (index, index_offset + 0x10C);` |
| `TlpOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `TlpOpener.OpenEntry` | `byte type = arc.File.View.ReadByte (0x18);` |
| `TlpOpener.OpenEntry` | `int len = Math.Min (arc.File.View.ReadByte (0x19) >> 1, data.Length);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.FrontWing.TlpOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "DAT"))
        return null;

    int count = file.View.ReadInt32 (0x10);
    if (!IsSaneCount (count))
        return null;

    int index_size = 0x110 * count;
    var index = file.View.ReadBytes (0x20, (uint)index_size);
    byte type = file.View.ReadByte (0x18);
    Decrypt (index, index_size, type);

    var first_name = Binary.GetCString (index, 0, 0x104);
    if (first_name != "data/ajfkur3h45n56d7u78a7nh9u7iI8ny0fau6i4al27we4hfuelnrg")
        return null;

    int index_offset = 0x110;
    var dir = new List<Entry> (count - 1);
    for (int i = 1; i < count; i++)
    {
        var name = Binary.GetCString (index, index_offset, 0x104);
        var entry = Create<PackedEntry> (name);
        entry.Offset = LittleEndian.ToUInt32 (index, index_offset + 0x104);
        entry.UnpackedSize = LittleEndian.ToUInt32 (index, index_offset + 0x108);
        entry.Size = LittleEndian.ToUInt32 (index, index_offset + 0x10C);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        index_offset += 0x110;
        dir.Add (entry);
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    byte type = arc.File.View.ReadByte (0x18);
    int len = Math.Min (arc.File.View.ReadByte (0x19) >> 1, data.Length);
    Decrypt (data, len, type);
    return new ZLibStream (new MemoryStream (data), CompressionMode.Decompress);
}
```

#### Decrypt

```csharp
void Decrypt (byte[] buffer, int length, byte type = 0) {
    if (type == 0)
    {
        byte key = 0xcb;
        for (int i = 0; i < length; i++)
        {
            buffer[i] = Binary.RotByteR ((byte)(buffer[i] ^ key), 1);
            key = 1;
        }
    }

    else
    {
        throw new System.NotImplementedException ("decryption type not implemented");
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/FrontWing/ArcTLP.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
