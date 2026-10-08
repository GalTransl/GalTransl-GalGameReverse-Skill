# Malie / MalieEncryption：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| 辅助算法 | 不独立读取索引；见调用入口和下面的变换步骤 |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Malie.NoOpDecryptor

继承/接口：`IMalieDecryptor`。

### GameRes.Formats.Malie.EncryptedStream

继承/接口：`Stream`。

#### 状态与常量

```csharp
ArcView.Frame   m_view ;

IMalieDecryptor m_dec ;

long            m_max_offset ;

long            m_position = 0 ;

byte[]          m_current_block = new byte[BlockLength] ;

int             m_current_block_length = 0 ;

long            m_current_block_position = 0 ;

public const int BlockLength = 0x1000 ;

public IMalieDecryptor Decryptor { get { return m_dec; } }

public override bool  CanRead { get { return !m_disposed; } }

public override bool  CanSeek { get { return !m_disposed; } }

public override long Length { get { return m_max_offset; } }

public override long Position {
    get { return m_position; }
    set { m_position = value; }
}

bool m_disposed = false ;
```

#### EncryptedStream

```csharp
public EncryptedStream (ArcView mmap, IMalieDecryptor decryptor) {
    m_view = mmap.CreateFrame();
    m_dec = decryptor;
    m_max_offset = mmap.MaxOffset;
}
```

#### Read

```csharp
public override int Read (byte[] buf, int index, int count) {
    int total_read = 0;
    bool refill_buffer = !(m_position >= m_current_block_position && m_position < m_current_block_position + m_current_block_length);
    while (count > 0 && m_position < m_max_offset)
    {
        if (refill_buffer)
        {
            m_current_block_position = m_position & ~((long)BlockLength-1);
            FillBuffer();
        }
        int src_offset = (int)m_position & (BlockLength-1);
        int available = Math.Min (count, m_current_block_length - src_offset);
        Buffer.BlockCopy (m_current_block, src_offset, buf, index, available);
        m_position += available;
        total_read += available;
        index += available;
        count -= available;
        refill_buffer = true;
    }
    return total_read;
}
```

#### FillBuffer

```csharp
private void FillBuffer () {
    m_current_block_length = m_view.Read (m_current_block_position, m_current_block, 0, (uint)BlockLength);
    for (int offset = 0; offset < m_current_block_length; offset += 0x10)
    {
        m_dec.DecryptBlock (m_current_block_position+offset, m_current_block, offset);
    }
}
```

#### Seek

```csharp
public override long Seek (long pos, SeekOrigin whence) {
    if (SeekOrigin.Current == whence)
        m_position += pos;
    else if (SeekOrigin.End == whence)
        m_position = m_max_offset + pos;
    else
        m_position = pos;
    return m_position;
}
```

#### SetLength

```csharp
public override void SetLength (long length) {
    throw new NotSupportedException();
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Malie/MalieEncryption.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
