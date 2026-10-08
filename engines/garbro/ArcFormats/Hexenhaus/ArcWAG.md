# Hexenhaus / ArcWAG：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `WAG/IAF` / `GameRes.Formats.Hexenhaus.WagOpener` | `wag` | `4941465f` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `WagOpener.TryOpen` | `int type = file.View.ReadUInt16 (4);` |
| `WagOpener.TryOpen` | `int count = file.View.ReadInt32 (6);` |
| `WagOpener.TryOpen` | `offsets[i] = index.ReadUInt32();` |
| `WagOpener.TryOpen` | `uint signature = index.ReadUInt32();` |
| `WagOpener.TryOpen` | `int section_count = index.ReadInt32();` |
| `WagOpener.TryOpen` | `index.ReadInt16();` |
| `WagOpener.TryOpen` | `signature = index.ReadUInt32();` |
| `WagOpener.TryOpen` | `uint imgd_size = index.ReadUInt32();` |
| `WagOpener.TryOpen` | `int name_length = index.ReadInt32()-2;` |
| `WagOpener.TryOpen` | `var section_size = index.ReadUInt32();` |
| `Ror4EncryptedStream.ReadByte` | `public override int ReadByte () {` |
| `Ror4EncryptedStream.ReadByte` | `int b = BaseStream.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Hexenhaus.WagOpener

继承/接口：`ArchiveFormat`。

#### WagOpener

```csharp
public WagOpener () {
    Extensions = new string[] { "wag" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int type = file.View.ReadUInt16 (4);
    int count = file.View.ReadInt32 (6);
    if (!IsSaneCount (count))
        return null;

    using (var enc = file.CreateStream())
    using (var dec = new Ror4EncryptedStream (enc))
    using (var index = new BinaryReader (dec))
    {
        dec.Position = 0x4A;
        var offsets = new uint[count];
        for (int i = 0; i < count; ++i)
        {
            offsets[i] = index.ReadUInt32();
        }
        var name_buffer = new byte[0x100];
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            index.BaseStream.Position = offsets[i];
            uint signature = index.ReadUInt32();
            if (signature != 0x41544144)
                continue;
            int section_count = index.ReadInt32();
            index.ReadInt16();
            var entry = new Entry { Offset = offsets[i] };
            for (int s = 0; s < section_count; ++s)
            {
                signature = index.ReadUInt32();
                if (0x44474D49 == signature)
                {
                    entry.Offset = index.BaseStream.Position - 4;
                    uint imgd_size = index.ReadUInt32();
                    entry.Size = imgd_size + 0x10;
                    index.BaseStream.Seek (imgd_size + 2, SeekOrigin.Current);
                }
                else if (0x454E4E46 == signature)
                {
                    int name_length = index.ReadInt32()-2;
                    index.ReadInt16();
                    if (name_length > name_buffer.Length)
                        name_buffer = new byte[name_length];
                    index.Read (name_buffer, 0, name_length);
                    entry.Name = Encodings.cp932.GetString (name_buffer, 0, name_length);
                    entry.Type = FormatCatalog.Instance.GetTypeFromName (entry.Name);
                    index.ReadInt16();
                }
                else
                {
                    var section_size = index.ReadUInt32();

                    index.BaseStream.Seek (section_size+2, SeekOrigin.Current);
                    if (0x415A4F4D != signature)
                        Trace.WriteLine (string.Format ("Unknown section 0x{0:X8}", signature), "[WAG/IAF]");
                }
            }
            if (entry.Size > 0 && !string.IsNullOrEmpty (entry.Name))
                dir.Add (entry);
        }
        if (0 == dir.Count)
            return null;
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    return new Ror4EncryptedStream (input);
}
```

### GameRes.Formats.Hexenhaus.Ror4EncryptedStream

继承/接口：`InputProxyStream`。

#### Read

```csharp
public override int Read (byte[] buffer, int offset, int count) {
    int read = BaseStream.Read (buffer, offset, count);
    for (int i = 0; i < read; ++i)
        buffer[offset+i] = Binary.RotByteR (buffer[offset+i], 4);
    return read;
}
```

#### ReadByte

```csharp
public override int ReadByte () {
    int b = BaseStream.ReadByte();
    if (b != -1)
        b = Binary.RotByteR ((byte)b, 4);
    return b;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Hexenhaus/ArcWAG.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
