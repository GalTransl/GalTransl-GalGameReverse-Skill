# Seraphim / ArcVoice：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `SERAPH/VOICE` / `GameRes.Formats.Seraphim.VoiceDatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `VoiceDatOpener.TryOpen` | `int count = file.View.ReadInt16 (0);` |
| `VoiceDatOpener.TryOpen` | `uint next_offset = file.View.ReadUInt32 (2);` |
| `VoiceDatOpener.ReadV1` | `uint next_offset = file.View.ReadUInt32 (index_offset);` |
| `VoiceDatOpener.ReadV1` | `next_offset = file.View.ReadUInt32 (index_offset);` |
| `VoiceDatOpener.ReadV2` | `Offset = file.View.ReadUInt32 (index_offset),` |
| `VoiceDatOpener.ReadV2` | `Size   = file.View.ReadUInt32 (index_offset+4),` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Seraphim.VoiceDatOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
public          bool   IsAmbiguous { get { return true; } }

static readonly Regex   VoiceRe = new Regex (@"^Voice(?:\d|pac)\.dat$", RegexOptions.IgnoreCase) ;
```

#### VoiceDatOpener

```csharp
public VoiceDatOpener () {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.MaxOffset > uint.MaxValue)
        return null;
    string name = Path.GetFileName (file.Name);
    if (!VoiceRe.Match (name).Success)
        return null;

    int count = file.View.ReadInt16 (0);
    if (!IsSaneCount (count))
        return null;

    uint data_offset = 2 + 4 * (uint)count;
    uint next_offset = file.View.ReadUInt32 (2);
    List<Entry> dir = null;
    if (next_offset < data_offset || next_offset >= file.MaxOffset)
        dir = ReadV2 (file, count);
    else
        dir = ReadV1 (file, count);
    if (null == dir)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### ReadV1

```csharp
List<Entry> ReadV1 (ArcView file, int count) {
    int index_offset = 2;
    uint next_offset = file.View.ReadUInt32 (index_offset);
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        index_offset += 4;
        var entry = new Entry { Name = string.Format ("{0:D5}.wav", i), Type = "audio" };
        entry.Offset = next_offset;
        if (i + 1 == count)
            next_offset = (uint)file.MaxOffset;
        else
            next_offset = file.View.ReadUInt32 (index_offset);
        if (next_offset <= entry.Offset)
            return null;
        entry.Size = next_offset - (uint)entry.Offset;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
    }
    return dir;
}
```

#### ReadV2

```csharp
List<Entry> ReadV2 (ArcView file, int count) {
    int index_offset = 6;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new Entry {
            Name = string.Format ("{0:D5}.ogg", i),
            Type = "audio",
            Offset = file.View.ReadUInt32 (index_offset),
            Size   = file.View.ReadUInt32 (index_offset+4),
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 12;
    }
    return dir;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Seraphim/ArcVoice.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
