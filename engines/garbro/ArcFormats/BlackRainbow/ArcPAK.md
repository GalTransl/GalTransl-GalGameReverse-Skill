# BlackRainbow / ArcPAK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAK/MELTY` / `GameRes.Formats.BlackRainbow.PakOpener` | `pak` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `int count = file.View.ReadInt32 (file.MaxOffset-8);` |
| `PakOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (file.MaxOffset-4);` |
| `PakOpener.TryOpen` | `uint offset = index.ReadUInt32();` |
| `PakOpener.TryOpen` | `uint packed_size = index.ReadUInt32();` |
| `PakOpener.TryOpen` | `uint unpacked_size = index.ReadUInt32();` |
| `PakOpener.TryOpen` | `int name_length = index.ReadInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.BlackRainbow.PakOpener

继承/接口：`ArchiveFormat`。

#### PakOpener

```csharp
public PakOpener () {
    Extensions = new string[] { "pak" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.MaxOffset <= 8)
        return null;
    int count = file.View.ReadInt32 (file.MaxOffset-8);
    if (!IsSaneCount (count))
        return null;
    uint index_size = file.View.ReadUInt32 (file.MaxOffset-4);
    if (index_size >= file.MaxOffset-8)
        return null;

    long index_offset = file.MaxOffset - 8 - index_size;
    using (var input = file.CreateStream (index_offset, index_size))
    using (var index = new BinaryReader (input, Encoding.Unicode))
    {
        char[] name_buffer = new char[0x40];
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            uint offset = index.ReadUInt32();
            uint packed_size = index.ReadUInt32();
            uint unpacked_size = index.ReadUInt32();
            int name_length = index.ReadInt32();
            if (name_length <= 0 || name_length > 0x100 )
                return null;
            if (name_length > name_buffer.Length)
                name_buffer = new char[name_length];
            if (name_length != index.Read (name_buffer, 0, name_length))
                return null;
            var name = new string (name_buffer, 0, name_length);
            var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
            entry.Offset = offset;
            entry.Size = packed_size;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            entry.IsPacked = uint.MaxValue != unpacked_size;
            entry.UnpackedSize = entry.IsPacked ? unpacked_size : packed_size;
            dir.Add (entry);
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return input;
    return new ZLibStream (input, CompressionMode.Decompress);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/BlackRainbow/ArcPAK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
