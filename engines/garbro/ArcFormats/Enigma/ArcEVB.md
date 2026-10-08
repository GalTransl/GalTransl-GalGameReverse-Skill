# Enigma / ArcEVB：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `EVB` / `GameRes.Formats.Enigma.EvbPackOpener` | `exe` | `45564200`, `4d5a9000` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `EvbPackOpener.TryOpen` | `if (file.View.AsciiEqual(0, "MZ")) {` |
| `EvbPackOpener.TryOpen` | `else if (!file.View.AsciiEqual(0, "EVB"))` |
| `EvbPackOpener.TryOpen` | `uint index_size = file.View.ReadUInt32(base_offset + 0x40) + base_offset + 68;` |
| `EvbPackOpener.TryOpen` | `var counts = new List<uint> { file.View.ReadUInt32(base_offset + 0x4C) };` |
| `EvbPackOpener.TryOpen` | `uint item_count = file.View.ReadUInt32(index_offset + 12);` |
| `EvbPackOpener.TryOpen` | `char c = (char)file.View.ReadUInt16(index_offset);` |
| `EvbPackOpener.TryOpen` | `var type = (NodeTypes)file.View.ReadByte(index_offset);` |
| `EvbPackOpener.TryOpen` | `uint unpacked_size = file.View.ReadUInt32(index_offset + 2);` |
| `EvbPackOpener.TryOpen` | `uint size = file.View.ReadUInt32(index_offset + 49);` |
| `EvbPackOpener.OpenEntry` | `uint header_size = arc.File.View.ReadUInt32(pent.Offset);` |
| `EvbPackOpener.OpenEntry` | `uint chunk_size = arc.File.View.ReadUInt32(pent.Offset + i);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### 枚举值

```csharp
enum NodeTypes {
        AbsoluteDrive = 1,
        File = 2,
        Folder = 3,
    }
```

### GameRes.Formats.Enigma.EvbPackOpener

继承/接口：`ArchiveFormat`。

#### EvbPackOpener

```csharp
public EvbPackOpener() {
    Signatures = new uint[] { 0x425645, 0x905a4d, 0 };
    Extensions = new[] { "exe" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    uint base_offset = 0;
    if (file.View.AsciiEqual(0, "MZ")) {
        var exe = new ExeFile(file);
        var sig = new byte[] { 0x45, 0x56, 0x42, 0x00 };
        if (exe.ContainsSection(".enigma1")) {
            var ofs = exe.FindString(exe.Sections[".enigma1"], sig);
            if (ofs != -1)
                base_offset = (uint)ofs;
        }
        if (base_offset == 0)
            return null;
    }
    else if (!file.View.AsciiEqual(0, "EVB"))
        return null;

    uint index_size = file.View.ReadUInt32(base_offset + 0x40) + base_offset + 68;
    uint index_offset = base_offset + 0x4F;
    uint file_offset = index_size;

    var dir = new List<Entry>();
    var name_buffer = new StringBuilder();
    var counts = new List<uint> { file.View.ReadUInt32(base_offset + 0x4C) };
    var names = new List<string> { "" };

    while (index_offset < index_size - 4) {
        uint item_count = file.View.ReadUInt32(index_offset + 12);
        index_offset += 16;
        name_buffer.Clear();
        while (true) {
            char c = (char)file.View.ReadUInt16(index_offset);
            index_offset += 2;
            if (c == 0)
                break;
            name_buffer.Append(c);
        }
        if (name_buffer.Length == 0)
            return null;
        var name = name_buffer.ToString();
        var type = (NodeTypes)file.View.ReadByte(index_offset);
        index_offset++;
        counts[counts.Count - 1]--;
        if (type == NodeTypes.File) {
            var entry = Create<PackedEntry>(Path.Combine(names.Concat(new[] { name }).ToArray()));
            uint unpacked_size = file.View.ReadUInt32(index_offset + 2);
            uint size = file.View.ReadUInt32(index_offset + 49);
            entry.IsPacked = unpacked_size != size;
            entry.Offset = file_offset;
            entry.UnpackedSize = unpacked_size;
            entry.Size = size;
            file_offset += size;
            if (!entry.CheckPlacement(file.MaxOffset))
                return null;
            dir.Add(entry);
            index_offset += 53;
        }
        else if (type == NodeTypes.Folder) {
            counts.Add(item_count);
            names.Add(name);
            index_offset += 25;
        }
        else if (type == NodeTypes.AbsoluteDrive) {
            counts.Add(item_count);
            names.Add(name[0].ToString());
            index_offset -= 4;
        }
        else
            return null;
        while (counts.Count > 0 && counts[counts.Count - 1] == 0) {
            counts.RemoveAt(counts.Count - 1);
            names.RemoveAt(names.Count - 1);
        }
    }

    return new ArcFile(file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry(ArcFile arc, Entry entry) {
    var pent = entry as PackedEntry;
    if (pent.IsPacked) {
        uint header_size = arc.File.View.ReadUInt32(pent.Offset);
        uint offset = header_size;
        Stream input = null;

        for (uint i = 8; i < header_size; i += 12) {
            uint chunk_size = arc.File.View.ReadUInt32(pent.Offset + i);
            var chunk = new aPLibStream(
                arc.File.CreateStream(pent.Offset + offset, chunk_size)
            );
            if (input != null)
                input = new ConcatStream(input, chunk);
            else
                input = chunk;
            offset += chunk_size;
        }

        return input;
    }
    else
        return arc.File.CreateStream(pent.Offset, pent.Size);
}
```

## 配套算法与外部条件

- [ArcFormats/ExeFile.cs](../ExeFile.md)：本页引用的随包算法资料。
- [ArcFormats/aPLibStream.cs](../aPLibStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Enigma/ArcEVB.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
