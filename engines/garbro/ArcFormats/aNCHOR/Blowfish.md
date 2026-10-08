# aNCHOR / Blowfish：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Mk2Blowfish.Mk2Blowfish` | `ctx[i] = BigEndian.ToUInt32 (_ctx, 4 * i);` |
| `Mk2Blowfish.Mk2Blowfish` | `ctx[N + 2 + i * 4 + j] = BigEndian.ToUInt32 (_ctx, 4 * (N + 2 + i * 256 + j));` |
| `Mk2BlowfishDecryptor.TransformBlock` | `uint xl = BigEndian.ToUInt32 (inBuffer, offset+i);` |
| `Mk2BlowfishDecryptor.TransformBlock` | `uint xr = BigEndian.ToUInt32 (inBuffer, offset+i+4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Anchor.Mk2Blowfish

#### 状态与常量

```csharp
const int	N = 16 ;

uint[]		ctx ;
```

#### Mk2Blowfish

```csharp
public Mk2Blowfish(byte[] key, byte[] _ctx) {
	short			i;
	short			j;
	short			k;
	uint			data;
	uint			datal;
	uint			datar;

	ctx = new uint[N + 270];

	for (i = 0; i < N + 2; ++i)
	{
		ctx[i] = BigEndian.ToUInt32 (_ctx, 4 * i);
	}

	for (i = 0; i < 4; ++i)
	{
		for (j = 0; j < 256; ++j)
		{
			ctx[N + 2 + i * 4 + j] = BigEndian.ToUInt32 (_ctx, 4 * (N + 2 + i * 256 + j));
		}
	}

	j = 0;
	for (i = 0; i < N + 2; ++i)
	{
		data = 0x00000000;
		for (k = 0; k < 4; ++k)
		{
			data = (data << 8) | key[j];
			j++;
			if (j >= key.Length)
			{
				j = 0;
			}
		}
		ctx[i] = ctx[i] ^ data;
	}

	datal = 0x00000000;
	datar = 0x00000000;

	for (i = 0; i < N + 2; i += 2)
	{
		Encipher(ref datal, ref datar);
		ctx[i] = datal;
		ctx[i + 1] = datar;
	}

	for (i = 0; i < 4; ++i)
	{
		for (j = 0; j < 256; j += 2)
		{
			Encipher(ref datal, ref datar);

			ctx[N + 2 + i * 4 + j] = datal;
			ctx[N + 3 + i * 4 + j] = datar;
		}
	}
}
```

#### CreateDecryptor

```csharp
public ICryptoTransform CreateDecryptor () {
	return new Mk2BlowfishDecryptor (this);
}
```

#### F

```csharp
private uint F(uint x) {
	ushort a;
	ushort b;
	ushort c;
	ushort d;
	uint  y;

	d = (ushort)(x & 0x00FF);
	x >>= 8;
	c = (ushort)(x & 0x00FF);
	x >>= 8;
	b = (ushort)(x & 0x00FF);
	x >>= 8;
	a = (ushort)(x & 0x00FF);

	y = ctx[18 + a] + ctx[22 + b];
	y = y ^ ctx[26 + c];
	y = y ^ ctx[30 + d];

	return y;
}
```

#### Encipher

```csharp
private void Encipher(ref uint xl, ref uint xr) {
	uint	Xl;
	uint	Xr;
	uint	temp;
	short	i;

	Xl = xl;
	Xr = xr;

	for (i = 0; i < N; ++i)
	{
		Xl = Xl ^ ctx[i];
		Xr = F(Xl) ^ Xr;

		temp = Xl;
		Xl = Xr;
		Xr = temp;
	}

	temp = Xl;
	Xl = Xr;
	Xr = temp;

	Xr = Xr ^ ctx[N];
	Xl = Xl ^ ctx[N + 1];

	xl = Xl;
	xr = Xr;
}
```

#### Decipher

```csharp
public void Decipher(ref uint xl, ref uint xr) {
	uint	Xl;
	uint	Xr;
	uint	temp;
	short   i;

	Xl = xl;
	Xr = xr;

	for (i = N + 1; i > 1; --i)
	{
		Xl = Xl ^ ctx[i];
		Xr = F(Xl) ^ Xr;

		temp = Xl;
		Xl = Xr;
		Xr = temp;
	}

	temp = Xl;
	Xl = Xr;
	Xr = temp;

	Xr = Xr ^ ctx[1];
	Xl = Xl ^ ctx[0];

	xl = Xl;
	xr = Xr;
}
```

### GameRes.Formats.Anchor.Mk2BlowfishDecryptor

继承/接口：`ICryptoTransform`。

#### 状态与常量

```csharp
Mk2Blowfish    m_bf ;

public const int BlockSize = 8 ;

public bool CanTransformMultipleBlocks { get { return true; } }

public bool          CanReuseTransform { get { return true; } }

public int              InputBlockSize { get { return BlockSize; } }

public int             OutputBlockSize { get { return BlockSize; } }

static readonly byte[] EmptyArray = new byte[0] ;

bool _disposed = false ;
```

#### Mk2BlowfishDecryptor

```csharp
public Mk2BlowfishDecryptor (Mk2Blowfish bf) {
	m_bf = bf;
}
```

#### TransformBlock

```csharp
public int TransformBlock (byte[] inBuffer, int offset, int count, byte[] outBuffer, int outOffset) {
	for (int i = 0; i < count; i += BlockSize)
	{
		uint xl = BigEndian.ToUInt32 (inBuffer, offset+i);
		uint xr = BigEndian.ToUInt32 (inBuffer, offset+i+4);
		m_bf.Decipher (ref xl, ref xr);
		BigEndian.Pack (xl, outBuffer, outOffset+i);
		BigEndian.Pack (xr, outBuffer, outOffset+i+4);
	}
	return count;
}
```

#### TransformFinalBlock

```csharp
public byte[] TransformFinalBlock (byte[] inBuffer, int offset, int count) {
	if (0 == count)
		return EmptyArray;

	var input = new byte[(count + BlockSize - 1) / BlockSize * BlockSize];
	Buffer.BlockCopy (inBuffer, 0, input, 0, inBuffer.Length);

	var output = new byte[input.Length];
	TransformBlock (input, offset, count, output, 0);

	Array.Resize (ref output, count);
	return output;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/aNCHOR/Blowfish.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
