# SquadraD / ArcPLA：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PLA` / `GameRes.Formats.SquadraD.PlaOpener` | `pla` | `506c612e` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PlaOpener.TryOpen` | `uint arc_size = file.View.ReadUInt32 (4);` |
| `PlaOpener.TryOpen` | `if (arc_size != file.MaxOffset \|\| file.View.ReadUInt32 (0x10) != 2)` |
| `PlaOpener.TryOpen` | `if (check != file.View.ReadUInt32 (8))` |
| `PlaOpener.TryOpen` | `int count = file.View.ReadUInt16 (0xE);` |
| `PlaOpener.TryOpen` | `Id = index.ReadInt32()` |
| `PlaOpener.TryOpen` | `entry.n1 = index.ReadInt32();` |
| `PlaOpener.TryOpen` | `entry.SampleRate = index.ReadUInt32();` |
| `PlaOpener.TryOpen` | `entry.Channels = index.ReadInt32();` |
| `PlaOpener.TryOpen` | `entry.n2 = index.ReadUInt8();` |
| `PlaOpener.TryOpen` | `entry.n3 = index.ReadUInt8();` |
| `PlaOpener.TryOpen` | `index.ReadInt16();` |
| `PlaOpener.TryOpen` | `entry.Offset = index.ReadUInt32();` |
| `PlaOpener.TryOpen` | `entry.Data[j] = index.ReadInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.SquadraD.PlaEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public  int Id ;

public  int n1 ;

public uint SampleRate ;

public  int Channels ;

public byte n2 ;

public byte n3 ;

public int[] Data ;
```

### GameRes.Formats.SquadraD.PlaOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint arc_size = file.View.ReadUInt32 (4);
    if (arc_size != file.MaxOffset || file.View.ReadUInt32 (0x10) != 2)
        return null;
    uint check = (arc_size & 0xD5555555u) << 1 | arc_size & 0xAAAAAAAAu;
    if (check != file.View.ReadUInt32 (8))
        return null;
    int count = file.View.ReadUInt16 (0xE);
    if (!IsSaneCount (count))
        return null;

    var dir = new List<Entry> (count);
    using (var index = file.CreateStream())
    {
        index.Position = 0x14;
        for (int i = 0; i < count; ++i)
        {
            var entry = new PlaEntry {
                Id = index.ReadInt32()
            };
            entry.Name = entry.Id.ToString ("D5");
            dir.Add (entry);
        }
        foreach (PlaEntry entry in dir)
        {
            entry.n1 = index.ReadInt32();
            entry.SampleRate = index.ReadUInt32();
            entry.Channels = index.ReadInt32();
            entry.n2 = index.ReadUInt8();
            entry.n3 = index.ReadUInt8();
            index.ReadInt16();
        }
        foreach (PlaEntry entry in dir)
        {
            entry.Offset = index.ReadUInt32();
        }
        foreach (PlaEntry entry in dir)
        {
            int n = entry.Channels * 2;
            entry.Data = new int[n];
            for (int j = 0; j < n; ++j)
                entry.Data[j] = index.ReadInt32();
        }
    }
    long last_offset = file.MaxOffset;
    for (int i = dir.Count - 1; i >= 0; --i)
    {
        dir[i].Size = (uint)(last_offset - dir[i].Offset);
        last_offset = dir[i].Offset;
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/SquadraD/ArcPLA.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
