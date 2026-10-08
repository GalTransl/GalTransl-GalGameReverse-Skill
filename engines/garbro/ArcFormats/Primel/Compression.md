# Primel / Compression：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `LzssPackedStream.Unpack` | `unpacked_size = reader.ReadInt32();` |
| `LzssPackedStream.Unpack` | `frame_size = 2 << reader.ReadUInt16();` |
| `LzssPackedStream.Unpack` | `bits = BaseStream.ReadByte();` |
| `LzssPackedStream.Unpack` | `int c = BaseStream.ReadByte();` |
| `LzssPackedStream.Unpack` | `int p = c \| BaseStream.ReadByte() << 8;` |
| `LzssPackedStream.Unpack` | `int count = BaseStream.ReadByte();` |
| `RlePackedStream.Unpack` | `unpacked_size = reader.ReadInt32();` |
| `RlePackedStream.Unpack` | `int prev_byte = BaseStream.ReadByte();` |
| `RlePackedStream.Unpack` | `int b = BaseStream.ReadByte();` |
| `RlePackedStream.Unpack` | `int count = BaseStream.ReadByte();` |
| `RlePackedStream.Unpack` | `b = BaseStream.ReadByte();` |
| `RangePackedStream.Unpack` | `int chunk_len = reader.ReadInt32();` |
| `RangePackedStream.Unpack` | `byte ctl = reader.ReadByte();` |
| `RangePackedStream.Unpack` | `int count = reader.ReadByte();` |
| `RangePackedStream.Unpack` | `byte i = reader.ReadByte();` |
| `RangePackedStream.Unpack` | `byte b = reader.ReadByte();` |
| `RangePackedStream.Unpack` | `freq[i] = (ushort)((reader.ReadByte() << 7) \| b);` |
| `RangePackedStream.Unpack` | `uint high  = Binary.BigEndian (reader.ReadUInt32());` |
| `RangePackedStream.Unpack` | `high = (high << 8) \| reader.ReadByte();` |
| `MtfPackedStream.Unpack` | `start_index = reader.ReadInt32();` |
| `MtfPackedStream.Unpack` | `int b = BaseStream.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Primel.LzssPackedStream

继承/接口：`PackedStream`。

#### Unpack

```csharp
protected override IEnumerator<int> Unpack () {
    int unpacked_size, frame_size;
    using (var reader = new ArcView.Reader (BaseStream))
    {
        unpacked_size = reader.ReadInt32();
        frame_size = 2 << reader.ReadUInt16();
    }
    var frame = new byte[frame_size];
    int frame_pos = 0;
    int dst = 0;
    int bits = 2;
    while (dst < unpacked_size)
    {
        bits >>= 1;
        if (1 == bits)
        {
            bits = BaseStream.ReadByte();
            if (-1 == bits)
                yield break;
            bits |= 0x100;
        }
        int c = BaseStream.ReadByte();
        if (-1 == c)
            yield break;
        if (0 != (bits & 1))
        {
            if (YieldByte ((byte)c))
                yield return YieldOffset;
            frame[frame_pos++ % frame_size] = (byte)c;
            ++dst;
        }
        else
        {
            int p = c | BaseStream.ReadByte() << 8;
            int count = BaseStream.ReadByte();
            if (-1 == count)
                yield break;
            count += 4;
            p = frame_pos - p;
            if (p < 0)
                p += frame_size;

            while (count --> 0)
            {
                byte b = frame[p++ % frame_size];
                if (YieldByte (b))
                    yield return YieldOffset;
                frame[frame_pos++ % frame_size] = b;
                ++dst;
            }
        }
    }
}
```

### GameRes.Formats.Primel.RlePackedStream

继承/接口：`PackedStream`。

#### Unpack

```csharp
protected override IEnumerator<int> Unpack () {
    int unpacked_size;
    using (var reader = new ArcView.Reader (BaseStream))
        unpacked_size = reader.ReadInt32();
    int dst = 0;
    int prev_byte = BaseStream.ReadByte();
    while (dst+1 < unpacked_size)
    {
        int b = BaseStream.ReadByte();
        if (-1 == b)
            break;
        if (b == prev_byte)
        {
            int count = BaseStream.ReadByte();
            if (-1 == count)
                break;
            count += 2;
            while (count --> 0)
            {
                if (YieldByte ((byte)b))
                    yield return YieldOffset;
                ++dst;
            }
            b = BaseStream.ReadByte();
        }
        else
        {
            if (YieldByte ((byte)prev_byte))
                yield return YieldOffset;
            ++dst;
        }
        prev_byte = b;
    }
    if (dst < unpacked_size && prev_byte != -1)
    {
        YieldByte ((byte)prev_byte);
    }
}
```

### GameRes.Formats.Primel.RangePackedStream

继承/接口：`PackedStream`。

#### Unpack

```csharp
protected override IEnumerator<int> Unpack () {
    var freq = new ushort[0x100];
    var table2 = new byte[0xFFFF00];
    var table3 = new uint[0x100];
    var table4 = new uint[0x100];
    using (var reader = new ArcView.Reader (BaseStream))
    {
        for (;;)
        {
            int chunk_len = reader.ReadInt32();

            byte ctl = reader.ReadByte();
            for (int i = 0; i < 0x100; ++i)
                freq[i] = 0;

            switch (ctl & 0x1F)
            {
            case 1:
                int count = reader.ReadByte();
                while (count --> 0)
                {
                    byte i = reader.ReadByte();
                    byte b = reader.ReadByte();

                    if (0 != (b & 0x80))
                        freq[i] = (ushort)(b & 0x7F);
                    else
                        freq[i] = (ushort)((reader.ReadByte() << 7) | b);
                }
                break;

            case 2:
                for (int i = 0; i < 256; i++)
                {
                    byte b = reader.ReadByte();

                    if (0 != (b & 0x80))
                        freq[i] = (ushort)(b & 0x7F);
                    else
                        freq[i] = (ushort)((reader.ReadByte() << 7) | b);
                }
                break;
            }

            uint f = 0;
            for (int i = 0; i < 0x100; i++)
            {
                table3[i] = f;
                table4[i] = freq[i];

                for (int j = freq[i]; j > 0; --j)
                    table2[f++] = (byte)i;
            }

            uint range = 0xC0000000;
            uint high  = Binary.BigEndian (reader.ReadUInt32());

            for (int i = 0; i < chunk_len; i++)
            {
                uint index = high / (range >> 12);
                byte c = table2[index];

                if (YieldByte (c))
                    yield return YieldOffset;

                high -= (range >> 12) * table3[c];
                range = (range >> 12) * table4[c];

                while (0 == (range & 0xFF000000))
                {
                    high = (high << 8) | reader.ReadByte();
                    range <<= 8;
                }
            }
            if (0 == (ctl & 0x80))
                break;
        }
    }
}
```

### GameRes.Formats.Primel.MtfPackedStream

继承/接口：`PackedStream`。

#### Unpack

```csharp
protected override IEnumerator<int> Unpack () {
    int start_index;
    using (var reader = new ArcView.Reader (BaseStream))
        start_index = reader.ReadInt32();

    byte[] table1 = Enumerable.Range (0, 256).Select (x => (byte)x).ToArray();
    var input = new List<byte>();
    for (int i = 0; ; ++i)
    {
        int b = BaseStream.ReadByte();
        if (-1 == b)
            break;
        byte c    = table1[b];
        byte prev = table1[0];

        if (prev != c)
        {
            for (int j = 1; ; ++j)
            {
                byte t = table1[j];
                table1[j] = prev;
                prev = t;

                if (t == c) break;
            }
            table1[0] = c;
        }
        input.Add (c);
    }
    int input_length = input.Count;
    var table2 = new int[256];
    for (int i = 0; i < input_length; ++i)
        table2[input[i]]++;

    int l = input_length;
    for (int i = 255; i >= 0; --i)
    {
        l -= table2[i];
        table2[i] = l;
    }

    var order = new int[input_length];
    for (int i = 0; i < input_length; ++i)
        order[table2[input[i]]++] = i;

    int index = start_index;
    for (;;)
    {
        index = order[index];
        if (YieldByte (input[index]))
            yield return YieldOffset;
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Primel/Compression.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
