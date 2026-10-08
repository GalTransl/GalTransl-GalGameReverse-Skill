# CatSystem / ArcBinV1：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `BinV1/CSPACK` / `GameRes.Formats.CatSystem.BinOpenerV1` | `binv1` | `61446740` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BinOpenerV1.TryOpen` | `string fn = br.ReadString();` |
| `BinOpenerV1.TryOpen` | `e.Offset = br.ReadUInt32();` |
| `BinOpenerV1.TryOpen` | `fn = br.ReadString();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.CatSystem.BinEntryV1

继承/接口：`Entry`。

#### 状态与常量

```csharp
public long Size64 { get; set; }
```

### GameRes.Formats.CatSystem.BinStreamV1

继承/接口：`Stream`。

#### 状态与常量

```csharp
private Stream mBaseStream ;

private readonly long mOffset ;

private readonly long mLength ;

private long mPosition = 0L ;

private bool mDisposed = false ;

public override bool CanRead => !this.mDisposed;

public override bool CanSeek => !this.mDisposed;

public override long Length => this.mLength;

public override long Position {
    get
    {
        return this.mPosition;
    }
    set
    {
        if (value < 0)
        {
            throw new ArgumentOutOfRangeException();
        }
        if (value > this.mLength)
        {
            throw new ArgumentOutOfRangeException();
        }
        this.mPosition = value;
    }
}
```

#### BinStreamV1

```csharp
public BinStreamV1(Stream stream, long offset, long length) {
    this.mBaseStream = stream;
    this.mOffset = offset;
    this.mLength = length;
}
```

#### Read

```csharp
public override int Read(byte[] buffer, int offset, int count) {
    Stream stream = this.mBaseStream;

    stream.Position = this.mOffset + this.mPosition;
    int bytesRead = stream.Read(buffer, offset, (int)Math.Min(this.mLength - this.mPosition, count));

    this.Decrypt(buffer, offset, bytesRead, this.mOffset, this.mPosition);
    this.mPosition += bytesRead;

    return bytesRead;
}
```

#### Seek

```csharp
public override long Seek(long offset, SeekOrigin origin) {
    long pos = 0L;
    switch (origin)
    {
        case SeekOrigin.Begin:
        {
            pos = offset;
            break;
        }
        case SeekOrigin.Current:
        {
            pos = this.mPosition + offset;
            break;
        }
        case SeekOrigin.End:
        {
            pos = this.mLength + offset;
            break;
        }
    }

    if (pos < 0)
    {
        throw new ArgumentOutOfRangeException();
    }
    if (pos > this.mLength)
    {
        throw new ArgumentOutOfRangeException();
    }

    this.mPosition = pos;
    return pos;
}
```

#### SetLength

```csharp
public override void SetLength(long value) {
    throw new NotSupportedException();
}
```

#### Decrypt

```csharp
protected virtual void Decrypt(byte[] buffer, long offset, int count, long fileOffset, long arcOffset) {
    for(int i = 0; i < count; ++i)
    {
        byte key = (byte)((fileOffset + arcOffset + i) * 0x9D + (arcOffset + i) * 0x773);
        buffer[offset + i] -= key;
    }
}
```

### GameRes.Formats.CatSystem.BinOpenerV1

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    using (ArcViewStream stream = file.CreateStream())
    {
        using (BinaryReader br = new BinaryReader(stream, Encoding.Unicode, true))
        {
            stream.Position = 8L;

            List<BinEntryV1> entries = new List<BinEntryV1>();
            {
                string fn = br.ReadString();
                while (!string.IsNullOrEmpty(fn))
                {
                    BinEntryV1 e = Create<BinEntryV1>(fn);
                    e.Offset = br.ReadUInt32();
                    e.Size64 = 0L;

                    entries.Add(e);

                    fn = br.ReadString();
                }
            }

            if (entries.Any())
            {
                {
                    BinEntryV1 last = entries.Last();
                    last.Size64 = stream.Length - last.Offset;
                    last.Size = (uint)last.Size64;
                }
                for (int i = 0; i < entries.Count - 1; ++i)
                {
                    BinEntryV1 curr = entries[i + 0];
                    BinEntryV1 next = entries[i + 1];
                    curr.Size64 = next.Offset - curr.Offset;
                    curr.Size = (uint)curr.Size64;
                }
            }

            return new ArcFile(file, this, entries.Cast<Entry>().ToList());
        }
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry(ArcFile arc, Entry entry) {
    if(!(entry is BinEntryV1 e))
    {
        return base.OpenEntry(arc, entry);
    }
    return new BinStreamV1(arc.File.CreateStream(), e.Offset, e.Size64);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/CatSystem/ArcBinV1.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
