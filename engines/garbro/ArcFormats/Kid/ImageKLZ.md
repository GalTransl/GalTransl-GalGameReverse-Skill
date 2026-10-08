# Kid / ImageKLZ：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `KlzFormat.LzhStreamDecode` | `uint output_size = Binary.BigEndian(input.ReadUInt32());` |
| `KlzFormat.LzhStreamDecode` | `ushort fill_count = Binary.BigEndian(input.ReadUInt16());` |
| `KlzFormat.LzhStreamDecode` | `f_out_bytes.Add(input.ReadUInt8());` |
| `KlzFormat.LzhStreamDecode` | `OO70_sp = Binary.BigEndian(input.ReadUInt16());` |
| `KlzFormat.LzhStreamDecode` | `v0 = decode_table[OO40_sp & 0xFF] & input.ReadUInt8();` |
| `KlzFormat.LzhStreamDecode` | `v1 = input.ReadUInt8();` |
| `KlzFormat.LzhStreamDecode` | `s2 = Binary.BigEndian(input.ReadUInt16());` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Kid.KlzFormat

继承/接口：`DigitalWorks.Tim2Format`。

#### KlzFormat

```csharp
public KlzFormat() {
    Extensions = new string[] { "klz" };
    Settings = null;
}
```

#### LzhStreamDecode

```csharp
public static Stream LzhStreamDecode(IBinaryStream input) {
    byte[] out_bytes = new byte[0x4000];
    List<byte> f_out_bytes = new List<byte>();
    uint output_size = Binary.BigEndian(input.ReadUInt32());
    ushort fill_count = Binary.BigEndian(input.ReadUInt16());
    bool at;
    int v0, s0 = 0, s1, s3;
    byte v1;
    ushort s2;
    int OO40_sp = 0, OO42_sp = 0, OO44_sp, OO48_sp, OO50_sp = 0, OO60_sp = 0, OO70_sp = fill_count;
    int next_read_pos = 0;
    int count = 0;
    int num_passes = 0;
    byte[] decode_table = new byte[] {
        0x01, 0x02, 0x04, 0x08,
        0x10, 0x20, 0x40, 0x80,

        0x81, 0x75, 0x81, 0x69,
        0x00, 0x00, 0x00, 0x00,
        0x01, 0x02, 0x00, 0x00
    };

    if (fill_count > 0x4000)
    {
        next_read_pos = 4;
        while (OO70_sp > 0x4000)
        {
            int cnt = 0;
            int copy_off = next_read_pos + 2;
            while (cnt < 0x4000)
            {
                input.Position = copy_off;
                f_out_bytes.Add(input.ReadUInt8());
                cnt++;
                copy_off++;
            }
            count += 0x4000;
            next_read_pos += cnt + 2;
            num_passes++;
            input.Position = next_read_pos;
            OO70_sp = Binary.BigEndian(input.ReadUInt16());
            if (count >= output_size || next_read_pos >= input.Length)
            {
                Stream stream = new MemoryStream(f_out_bytes.ToArray());
                return stream;
            }
            OO60_sp = next_read_pos + 2;
        }
    }
    else
    {
        OO60_sp = 6;
    }

    OO44_sp = OO60_sp;

    OO48_sp = OO60_sp + 1;
    while (true){
        input.Position = OO44_sp;

        v0 = decode_table[OO40_sp & 0xFF] & input.ReadUInt8();

        if (v0 == 0)
        {
            input.Position = OO48_sp;

            v1 = input.ReadUInt8();
            v0 = OO50_sp + s0;

            out_bytes[v0] = v1;
            OO48_sp++;
            OO42_sp++;
            s0++;
        }
        else if (v0 != 0) {

            OO42_sp += 2;
            input.Position = OO48_sp;

            s2 = Binary.BigEndian(input.ReadUInt16());

            s3 = (s2 & 0x1F) + 2;

            v0 = s0 - (s2 >> 5) - 1;

            s1 = v0 & 0xFFFF;
            OO48_sp += 1;
            v0 = 1;
            while (v0 != 0)
            {
                at = s0 < 0x0800;

                if (at)
                {
                    v0 = s1 & 0xFFFF;
                    at = s0 < v0;
                    if (at)
                    {
                        v1 = out_bytes[OO50_sp];
                        v0 = OO50_sp + s0;

                        out_bytes[v0] = v1;
                        s0 += 1;

                        s1 = (s1 + 1) & 0xFFFF;

                        v0 = s3 & 0xFFFF;
                        s3 = (s3 - 1) & 0xFFFF;
                        continue;
                    }
                }

                v1 = out_bytes[OO50_sp + s1 & 0xFFFF];
                v0 = OO50_sp;
                v0 += s0;

                out_bytes[v0] = v1;
                s0 += 1;

                s1 = (s1 + 1) & 0xFFFF;

                v0 = s3 & 0xFFFF;
                s3 = s3 - 1 & 0xFFFF;
            }
            OO48_sp += 1;
        }

        OO40_sp += 1;

        if ((OO40_sp & 0xFF) == 8)
        {
            OO40_sp = 0;
            OO44_sp = OO48_sp;
            OO48_sp += 1;
            OO42_sp += 1;
        }

        v0 = OO42_sp < OO70_sp - 1 ? 1 : 0;
        if (v0 == 0)
        {
            count += s0;
            if (count >= output_size || next_read_pos >= input.Length)
            {
                f_out_bytes.AddRange(out_bytes);
                Stream stream = new MemoryStream(f_out_bytes.ToArray());
                return stream;
            }
            num_passes += 1;
            if (num_passes == 1)
            {
                next_read_pos += OO70_sp + 6;
            }
            else
            {
                next_read_pos += OO70_sp + 2;
            }

            f_out_bytes.AddRange(out_bytes);

            input.Position = next_read_pos;
            OO70_sp = Binary.BigEndian(input.ReadUInt16());
            if (OO70_sp > 0x4000)
            {
                while (OO70_sp > 0x4000)
                {
                    int cnt = 0;
                    int copy_off = next_read_pos + 2;
                    while (cnt < 0x4000)
                    {
                        input.Position = copy_off;
                        f_out_bytes.Add(input.ReadUInt8());
                        cnt += 1;
                        copy_off += 1;
                    }
                    count += 0x4000;
                    next_read_pos += cnt + 2;
                    input.Position = next_read_pos;
                    OO70_sp = Binary.BigEndian(input.ReadUInt16());
                    if (count >= output_size || next_read_pos >= input.Length)
                    {
                        Stream stream = new MemoryStream(f_out_bytes.ToArray());
                        return stream;
                    }
                }
            }
            s0 = 0;

            OO50_sp = 0;
            OO42_sp = 0;
            OO48_sp = next_read_pos + 2;
            if (OO48_sp > input.Length) {
                Stream stream = new MemoryStream(f_out_bytes.ToArray());
                return stream;
            }
            OO40_sp = 0;
            OO60_sp = OO48_sp;
            OO44_sp = OO60_sp;
            v0 = OO60_sp + 1;
            OO48_sp = v0;
        }
    }

}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Kid/ImageKLZ.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
