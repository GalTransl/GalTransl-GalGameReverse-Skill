# BlackRainbow / ArcIMP：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `IMP` / `GameRes.Formats.BlackRainbow.ImpOpener` | `imp` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ImpOpener.TryOpen` | `uint key = KnownSchemes[file.View.ReadUInt32 (0)];` |
| `ImpOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (4);` |
| `ImpOpener.TryOpen` | `uint next_offset = file.View.ReadUInt32 (index_offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.BlackRainbow.ImpArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly uint Key ;
```

#### ImpArchive

```csharp
public ImpArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, uint key)
    : base (arc, impl, dir) {
    Key = key;
}
```

### GameRes.Formats.BlackRainbow.ImpOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly Dictionary<uint, uint> KnownSchemes = new Dictionary<uint, uint> {
    { 0x3D66, 0xCE032ADB },
    { 0x59E8, 0xD36050EC },
}
```

#### ImpOpener

```csharp
public ImpOpener () {
    Signatures = KnownSchemes.Keys;
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint key = KnownSchemes[file.View.ReadUInt32 (0)];
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    uint base_offset = 0x404;
    uint offset = file.View.ReadUInt32 (4);
    uint index_offset = 8;
    var dir = new List<Entry>();
    for (int i = 0; i < 0xFF; ++i)
    {
        uint next_offset = file.View.ReadUInt32 (index_offset);
        uint size = next_offset - offset;
        if (size > 0x10)
        {
            var entry = new Entry {
                Name = string.Format ("{0}#{1:D3}", base_name, i),
                Type = "image",
                Offset = base_offset + offset,
                Size = size,
            };
            dir.Add (entry);
        }
        index_offset += 4;
        offset = next_offset;
    }
    if (0 == dir.Count)
        return null;
    return new ImpArchive (file, this, dir, key);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/BlackRainbow/ArcIMP.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
