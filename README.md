# santecpro

Santec **TSL-550** 可调激光器 + **MPM-210** 功率计的扫谱系统。底层扫描依赖 Santec 的 .NET DLL(只能在 Windows 加载),因此系统分成两台电脑协作,项目也拆成两个**可独立部署**的文件夹。

```
控制端(Mac/任意电脑) ──HTTP──▶ Windows 电脑(直连仪器 + DLL) ──GPIB──▶ TSL 激光器 + MPM 功率计
```

## 两个文件夹

| 文件夹 | 部署到 | 作用 | 指南 |
|---|---|---|---|
| [`windows-server/`](windows-server/) | **Windows 电脑** | 直连仪器、加载 DLL、执行扫描,提供 HTTP 接口 | [windows-server/README.md](windows-server/README.md) |
| [`remote-client/`](remote-client/) | **Mac / 控制电脑** | 远程操控、画图、算 IL、导出 CSV | [remote-client/README.md](remote-client/README.md) |

**部署 = 把对应文件夹整包拷到目标电脑**,各自 `pip install -r requirements.txt` 即可。两个文件夹互相独立、自包含。

## 快速上手

**Windows 端**
```bat
cd windows-server
pip install -r requirements.txt && pip install pythonnet
:: 放好 vendor/santec_dll/*.dll 后:
python server.py
```

**控制端**
```bash
cd remote-client
pip install -r requirements.txt
python run_ui.py          # 界面里服务器 URL 指向 http://<Windows_IP>:5000
```

## 文档

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 架构总览与数据流
- [windows-server/README.md](windows-server/README.md) — Windows 端部署与操作
- [remote-client/README.md](remote-client/README.md) — 控制端部署与操作

## 开发

```bash
# 各文件夹独立测试
cd windows-server && pytest      # DLL 用例在非 Windows 上自动跳过
cd remote-client  && pytest
```

改动 `exceptions.py` / `sweep_rules.py` 这类两端共享的小模块后,运行 `python sync_shared.py` 保持两侧一致(`--check` 可用于校验)。

## License

MIT
