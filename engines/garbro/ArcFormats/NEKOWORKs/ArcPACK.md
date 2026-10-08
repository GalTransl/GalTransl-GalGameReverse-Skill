# NEKOWORKs / ArcPACK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PACK/EXFS` / `GameRes.Formats.NEKOWORKs.NekoWorksPackOpener` | `pack` | `45584653` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| 辅助算法 | 不独立读取索引；见调用入口和下面的变换步骤 |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.NEKOWORKs.NekoWorksPackOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    if (file.MaxOffset < EXFSHeader.Size())
    {
        return null;
    }

    using (ArcViewStream stream = file.CreateStream())
    {
        stream.ReadStruct(out EXFSHeader hdr);
        if (hdr.Signature != 0x53465845u)
        {
            return null;
        }
        if (hdr.ReaderVersion == 0u)
        {
            return null;
        }

        stream.Position = hdr.HeaderSize;
        byte[] entryTableBytes = new byte[hdr.EntryTableSize];
        byte[] pathTableBytes = new byte[hdr.PathTableSize];
        if (stream.Read(entryTableBytes) != entryTableBytes.Length)
        {
            return null;
        }
        if (stream.Read(pathTableBytes) != pathTableBytes.Length)
        {
            return null;
        }

        ReadOnlySpan<EXFSFileEntry> exfsEntries = MemoryMarshal.Cast<byte, EXFSFileEntry>(entryTableBytes);

        List<Entry> dir = new List<Entry>((int)hdr.FileCount);
        for (uint i = 0; i < hdr.FileCount; ++i)
        {
            EXFSFileEntry fe = exfsEntries[(int)i];
            string fn = Encoding.UTF8.GetString(pathTableBytes, (int)fe.FilePathOffset, (int)fe.FilePathSize);

            Entry entry = Create<Entry>(fn);
            entry.Offset = hdr.ResourceTableOffset + fe.FileOffset;
            entry.Size = (uint)fe.FileSize;

            if (!entry.CheckPlacement(file.MaxOffset))
            {
                return null;
            }

            dir.Add(entry);
        }
        return new ArcFile(file, this, dir);
    }
}
```

### GameRes.Formats.NEKOWORKs.NekoWorksPackOpener.EXFSHeader

#### FieldOffset

```csharp
[FieldOffset(0x00)]
public uint Signature ;
```

#### FieldOffset

```csharp
[FieldOffset(0x04)]
public uint ReaderVersion ;
```

#### FieldOffset

```csharp
[FieldOffset(0x08)]
public uint WriterVersion ;
```

#### FieldOffset

```csharp
[FieldOffset(0x0C)]
public uint FileCount ;
```

#### FieldOffset

```csharp
[FieldOffset(0x10)]
public long HeaderSize ;
```

#### FieldOffset

```csharp
[FieldOffset(0x18)]
public long EntryTableSize ;
```

#### FieldOffset

```csharp
[FieldOffset(0x20)]
public long PathTableSize ;
```

#### FieldOffset

```csharp
[FieldOffset(0x28)]
public long ResourceTableOffset ;
```

#### FieldOffset

```csharp
[FieldOffset(0x30)]
public long Reserve1 ;
```

#### FieldOffset

```csharp
[FieldOffset(0x38)]
public long Reserve2 ;
```

#### FieldOffset

```csharp
[FieldOffset(0x40)]
public long Reserve3 ;
```

#### FieldOffset

```csharp
[FieldOffset(0x48)]
public long Reserve4 ;
```

#### Size

```csharp
public unsafe static int Size() {
    return Unsafe.SizeOf<EXFSHeader>();
}
```

### GameRes.Formats.NEKOWORKs.NekoWorksPackOpener.EXFSFileEntry

#### FieldOffset

```csharp
[FieldOffset(0x00)]
public long FilePathOffset ;
```

#### FieldOffset

```csharp
[FieldOffset(0x08)]
public long FilePathSize ;
```

#### FieldOffset

```csharp
[FieldOffset(0x10)]
public long FileOffset ;
```

#### FieldOffset

```csharp
[FieldOffset(0x18)]
public long FileSize ;
```

#### Size

```csharp
public unsafe static int Size() {
    return Unsafe.SizeOf<EXFSFileEntry>();
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/NEKOWORKs/ArcPACK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
