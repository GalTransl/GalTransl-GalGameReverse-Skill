# Will / ArcPulltop：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/WillV2` / `GameRes.Formats.Will.Arc2Opener` | `arc`, `ar2` | 无固定签名或来源表达式未解析 | `True` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Arc2Opener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `Arc2Opener.TryOpen` | `uint index_size = file.View.ReadUInt32 (4);` |
| `Arc2Opener.TryOpen` | `uint size = file.View.ReadUInt32 (index_offset);` |
| `Arc2Opener.TryOpen` | `long offset = (long)base_offset + file.View.ReadUInt32 (index_offset+4);` |
| `Arc2Opener.TryOpen` | `char c = (char)file.View.ReadUInt16 (index_offset);` |
| `Arc2Opener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `Arc2Opener.OpenPsp` | `int unpacked_size = input.ReadInt32();` |
| `Arc2Opener.OpenPsp` | `int ctl = input.ReadByte();` |
| `Arc2Opener.OpenPsp` | `byte b = input.ReadUInt8();` |
| `Arc2Opener.OpenPsp` | `int hi = input.ReadByte();` |
| `Arc2Opener.OpenPsp` | `int lo = input.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Will.Arc2Opener

继承/接口：`ArchiveFormat`。

#### Arc2Opener

```csharp
public Arc2Opener () {
    Extensions = new string[] { "arc", "ar2" };
    ContainedFormats = new[] { "PNG", "PNA", "PSB", "OGG", "SCR" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = 8;
    uint index_size = file.View.ReadUInt32 (4);
    uint base_offset = index_offset + index_size;
    if (index_size > base_offset || base_offset >= file.MaxOffset)
        return null;
    file.View.Reserve (index_offset, index_size);

    var dir = new List<Entry> (count);
    var name_buffer = new StringBuilder (0x40);
    for (int i = 0; i < count; ++i)
    {
        if (index_offset >= base_offset)
            return null;
        uint size = file.View.ReadUInt32 (index_offset);
        long offset = (long)base_offset + file.View.ReadUInt32 (index_offset+4);
        index_offset += 8;
        name_buffer.Clear();
        for (;;)
        {
            if (index_offset >= base_offset)
                return null;
            char c = (char)file.View.ReadUInt16 (index_offset);
            index_offset += 2;
            if (0 == c)
                break;
            name_buffer.Append (c);
        }
        if (0 == name_buffer.Length)
            return null;
        var name = name_buffer.ToString();
        var entry = Create<Entry> (name);
        entry.Offset = offset;
        entry.Size = size;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
    }
    if (index_offset != base_offset)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (!IsScriptFile (entry.Name) || Path.GetFileName (arc.File.Name).Contains ("Model"))
    {
        if (entry.Name.HasExtension (".PSP"))
            return OpenPsp (arc, entry);
        return base.OpenEntry (arc, entry);
    }
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    for (int i = 0; i < data.Length; ++i)
    {
        data[i] = Binary.RotByteR (data[i], 2);
    }
    return new BinMemoryStream (data, entry.Name);
}
```

#### OpenPsp

```csharp
Stream OpenPsp (ArcFile arc, Entry entry) {
    using (var input = arc.File.CreateStream (entry.Offset, entry.Size))
    {
        int unpacked_size = input.ReadInt32();
        var output = new byte[unpacked_size];
        int dst = 0;
        var frame = new byte[0x1000];
        int frame_pos = 1;
        while (dst < unpacked_size)
        {
            int ctl = input.ReadByte();
            for (int bit = 1; dst < unpacked_size && bit != 0x100; bit <<= 1)
            {
                if (0 != (ctl & bit))
                {
                    byte b = input.ReadUInt8();
                    output[dst++] = frame[frame_pos++ & 0xFFF] = b;
                }
                else
                {
                    int hi = input.ReadByte();
                    int lo = input.ReadByte();
                    int offset = hi << 4 | lo >> 4;
                    for (int count = 2 + (lo & 0xF); count != 0; --count)
                    {
                        byte v = frame[offset++ & 0xFFF];
                        output[dst++] = frame[frame_pos++ & 0xFFF] = v;
                    }
                }
            }
        }
        return new BinMemoryStream (output, entry.Name);
    }
}
```

#### IsScriptFile

```csharp
static bool IsScriptFile (string name) {
    return name.HasAnyOfExtensions ("ws2", "json");
}
```

#### CopyScript

```csharp
void CopyScript (Stream input, Stream output) {
    var buffer = new byte[81920];
    for (;;)
    {
        int read = input.Read (buffer, 0, buffer.Length);
        if (0 == read)
            break;
        for (int i = 0; i < read; ++i)
        {
            buffer[i] = Binary.RotByteL (buffer[i], 2);
        }
        output.Write (buffer, 0, read);
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Will/ArcPulltop.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
