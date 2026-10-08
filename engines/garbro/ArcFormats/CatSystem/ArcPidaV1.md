# CatSystem / ArcPidaV1：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PidaV1` / `GameRes.Formats.CatSystem.PidaOpenerV1` | `pidav1` | `7323f26d` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PidaOpenerV1.TryOpen` | `string fn = br.ReadString();` |
| `PidaOpenerV1.TryOpen` | `e.Offset = br.ReadUInt32();` |
| `PidaOpenerV1.TryOpen` | `e.Width = br.ReadUInt16();` |
| `PidaOpenerV1.TryOpen` | `e.Height = br.ReadUInt16();` |
| `PidaOpenerV1.TryOpen` | `e.OffsetX = br.ReadInt16();` |
| `PidaOpenerV1.TryOpen` | `e.OffsetY = br.ReadInt16();` |
| `PidaOpenerV1.TryOpen` | `fn = br.ReadString();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.CatSystem.PidaEntryV1

继承/接口：`Entry`。

#### 状态与常量

```csharp
public ushort Width ;

public ushort Height ;

public short OffsetX ;

public short OffsetY ;
```

### GameRes.Formats.CatSystem.PidaOpenerV1

继承/接口：`ArchiveFormat`。

#### PidaOpenerV1

```csharp
public PidaOpenerV1() {
    ContainedFormats = new[] { "PNG" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    using (ArcViewStream stream = file.CreateStream())
    {
        using (BinaryReader br = new BinaryReader(stream, Encoding.Unicode, true))
        {
            stream.Position = 8L;

            List<PidaEntryV1> entries = new List<PidaEntryV1>();
            {
                string fn = br.ReadString();
                while (!string.IsNullOrEmpty(fn))
                {
                    PidaEntryV1 e = Create<PidaEntryV1>(fn);
                    e.Offset = br.ReadUInt32();
                    e.Size = 0u;

                    e.Width = br.ReadUInt16();
                    e.Height = br.ReadUInt16();
                    e.OffsetX = br.ReadInt16();
                    e.OffsetY = br.ReadInt16();

                    e.Type = "image";
                    entries.Add(e);

                    fn = br.ReadString();
                }
            }

            if (entries.Any())
            {
                long imageDataOffset = stream.Position;

                foreach (PidaEntryV1 e in entries)
                {
                    e.Offset += imageDataOffset;
                }
                {
                    PidaEntryV1 last = entries.Last();
                    last.Size = (uint)(stream.Length - last.Offset);
                }
                for (int i = 0; i < entries.Count - 1; ++i)
                {
                    PidaEntryV1 curr = entries[i + 0];
                    PidaEntryV1 next = entries[i + 1];
                    curr.Size = (uint)(next.Offset - curr.Offset);
                }
            }

            return new ArcFile(file, this, entries.Cast<Entry>().ToList());
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/CatSystem/ArcPidaV1.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
