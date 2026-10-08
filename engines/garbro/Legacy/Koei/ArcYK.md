# Koei / ArcYK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `YK/KOEI` / `GameRes.Formats.Koei.YkOpener` | `yk` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `YkOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Koei.YkArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly string YkName ;
```

#### YkArchive

```csharp
public YkArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, string name)
    : base (arc, impl, dir) {
    YkName = name;
}
```

### GameRes.Formats.Koei.YkEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public int Id ;
```

### GameRes.Formats.Koei.YkOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly byte[] RiffHeader = new byte[] {
    (byte)'R', (byte)'I', (byte)'F', (byte)'F', 0, 0, 0, 0,
    (byte)'W', (byte)'A', (byte)'V', (byte)'E', (byte)'f', (byte)'m', (byte)'t', (byte)' ',
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".YK"))
        return null;
    var name = Path.GetFileNameWithoutExtension (file.Name).ToUpperInvariant();
    List<Entry> dir = null;
    if ("DATA01" == name)
        dir = GetData01Index (file);
    else if (OffsetTable.ContainsKey (name))
        dir = GetDataIndex (file, OffsetTable[name], name);
    if (null == dir)
        return null;
    return new YkArchive (file, this, dir, name);
}
```

#### GetData01Index

```csharp
List<Entry> GetData01Index (ArcView file) {
    int count = (int)(file.MaxOffset / 0x4B400);
    if (!IsSaneCount (count) || count * 0x4B400 != file.MaxOffset)
        return null;
    uint offset = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new Entry {
            Name = string.Format ("{0:D5}.BMP", i),
            Type = "image",
            Offset = offset,
            Size = 0x4B400
        };
        dir.Add (entry);
        offset += 0x4B400;
    }
    return dir;
}
```

#### GetDataIndex

```csharp
List<Entry> GetDataIndex (ArcView file, uint[] offsets, string name) {
    var dir = new List<Entry> (offsets.Length);
    uint current_offset = 0;
    for (int i = 0; i < offsets.Length; ++i)
    {
        var entry = new YkEntry {
            Name = string.Format ("{0}#{1:D4}", name, i),
            Offset = current_offset,
            Size = offsets[i] - current_offset,
            Id = i
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        if ("DATA02" == name && (i >= 11 || Data02Images.ContainsKey (i)))
        {
            entry.Name += ".BMP";
            entry.Type = "image";
        }
        else if (IsAudio.Contains (name))
        {
            entry.Name += ".WAV";
            entry.Type = "audio";
        }
        dir.Add (entry);
        current_offset = offsets[i];
    }
    return dir;
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var yarc = (YkArchive)arc;
    if ("DATA03" == yarc.YkName)
    {
        var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
        DecryptData03 (data);
        return new BinMemoryStream (data, entry.Name);
    }
    else if (IsAudio.Contains (yarc.YkName))
        return OpenAudio (arc, entry);
    else
        return base.OpenEntry (arc, entry);
}
```

#### OpenAudio

```csharp
Stream OpenAudio (ArcFile arc, Entry entry) {
    var header = RiffHeader.Clone() as byte[];
    LittleEndian.Pack (entry.Size+8u, header, 4);
    var wave = arc.File.CreateStream (entry.Offset, entry.Size);
    return new PrefixStream (header, wave);
}
```

#### DecryptData03

```csharp
unsafe void DecryptData03 (byte[] data) {
    int count = data.Length >> 2;
    fixed (byte* data8 = &data[0])
    {
        uint* data32 = (uint*)data8;
        while (count --> 0)
        {
            *data32++ ^= 0x12C4D65u;
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Koei/ArcYK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
