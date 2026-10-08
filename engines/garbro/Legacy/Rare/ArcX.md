# Rare / ArcX：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `X/RARE` / `GameRes.Formats.Rare.XOpener` | `x` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `XOpener.TryOpen` | `Offset = index.View.ReadUInt32 (index_offset),` |
| `XOpener.TryOpen` | `Size   = index.View.ReadUInt32 (index_offset+4),` |
| `XOpener.TryOpen` | `UnpackedSize = index.View.ReadUInt32 (index_offset+8),` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Rare.XOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!VFS.IsPathEqualsToFileName (file.Name, "PP.X"))
        return null;
    string full_exe_name = null;
    Tuple<uint, int> index_pos = null;
    foreach (var exe_name in KnownExeMap.Keys)
    {
        full_exe_name = VFS.ChangeFileName (file.Name, exe_name);
        if (VFS.FileExists (full_exe_name))
        {
            index_pos = KnownExeMap[exe_name];
            break;
        }
    }
    if (null == index_pos)
        return null;
    uint index_offset = index_pos.Item1;
    int count = index_pos.Item2;
    using (var index = VFS.OpenView (full_exe_name))
    {
        index.View.Reserve (index_offset, (uint)count * 12u);
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            var entry = new PackedEntry {
                Name = string.Format ("PP#{0:D5}.BMP", i),
                Type = "image",
                Offset = index.View.ReadUInt32 (index_offset),
                Size   = index.View.ReadUInt32 (index_offset+4),
                UnpackedSize = index.View.ReadUInt32 (index_offset+8),
                IsPacked = true,
            };
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
            index_offset += 12;
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = (PackedEntry)entry;
    using (var input = arc.File.CreateStream (entry.Offset, entry.Size))
    {
        var output = new byte[pent.UnpackedSize];
        Decompress (input, output);
        return new BinMemoryStream (output, entry.Name);
    }
}
```

#### Decompress

```csharp
internal static void Decompress (IBinaryStream input, byte[] output) {
    var frame = new byte[0x400];
    int frame_pos = 1;
    int dst = 0;
    using (var bits = new MsbBitStream (input.AsStream, true))
    {
        while (dst < output.Length)
        {
            int ctl = bits.GetNextBit();
            if (-1 == ctl)
                break;
            if (ctl != 0)
            {
                int v = bits.GetBits (8);
                output[dst++] = frame[frame_pos++ & 0x3FF] = (byte)v;
            }
            else
            {
                int offset = bits.GetBits (10);
                int count = bits.GetBits (5) + 2;
                while (count --> 0)
                {
                    byte v = frame[offset++ & 0x3FF];
                    output[dst++] = frame[frame_pos++ & 0x3FF] = v;
                }
            }
        }
    }
}
```

## 配套算法与外部条件

- [ArcFormats/BitStream.cs](../../ArcFormats/BitStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/Rare/ArcX.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
