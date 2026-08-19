# 第三方组件与通知清单

审计日期：2026-08-13。范围为 `build/bepinex_runtime` 中实际会被 `tools/build_release.ps1` 复制到补丁 ZIP 的文件，以及随包字体。本文件是组件与来源清单，不替代随包附带的上游许可证全文，也不是法律意见。

## 结论

构建器现在会检查并随包复制 BepInEx、BepInEx.Harmony、HarmonyX、原 Harmony、MonoMod、Mono.Cecil、UnityDoorstop 与 Noto Sans SC 的上游许可证原文。UnityDoorstop 另附对应 v4.5.0 官方源代码归档；任一文件缺失时构建会失败。所有材料均取自表中所列的官方仓库与确定版本，未手工改写许可证正文。

## 本地文件与上游通知

| 本地文件 | 上游项目 | 本地可识别版本 | 上游许可/通知 | 发布状态 |
| --- | --- | --- | --- | --- |
| `BepInEx.dll`、`BepInEx.Preloader.dll` 及 XML | [BepInEx 5.4.23.5](https://github.com/BepInEx/BepInEx/releases/tag/v5.4.23.5) | `5.4.23.5` | [MIT License](https://github.com/BepInEx/BepInEx/blob/v5.4.23.5/LICENSE) | 已有全文；构建脚本复制为 `licenses/BepInEx-MIT.txt` |
| `BepInEx.Harmony.dll`、`0Harmony20.dll`、`HarmonyXInterop.dll` | [BepInEx.Harmony](https://github.com/BepInEx/BepInEx.Harmony) | `2.0.0.0` / `1.0.0.0` | [MIT License](https://github.com/BepInEx/BepInEx.Harmony/blob/master/LICENSE) | 已随包附 `BepInExHarmony-MIT.txt` |
| `0Harmony.dll` 及 XML | [HarmonyX](https://github.com/BepInEx/HarmonyX)（含原 Harmony 代码） | 程序集版本 `2.9.0.0` | [HarmonyX MIT](https://github.com/BepInEx/HarmonyX/blob/v2.9.0/LICENSE) 与 [原 Harmony MIT](https://github.com/BepInEx/HarmonyX/blob/v2.9.0/LICENSE.Harmony) 两份通知 | 已随包附 `HarmonyX-MIT.txt` 与 `Harmony-original-MIT.txt` |
| `MonoMod.RuntimeDetour.dll`、`MonoMod.Utils.dll` 及 XML | [MonoMod](https://github.com/MonoMod/MonoMod) | 程序集版本 `22.1.29.1` | [MIT License](https://github.com/MonoMod/MonoMod/blob/v22.01.29.01/LICENSE) | 已随包附 `MonoMod-MIT.txt` |
| `Mono.Cecil*.dll` | [Mono.Cecil](https://github.com/jbevain/cecil) | `0.10.4.0` | [MIT License](https://github.com/jbevain/cecil/blob/0.10.4/LICENSE.txt) | 已随包附 `MonoCecil-MIT.txt` |
| `winhttp.dll`、`doorstop_config.ini`、`.doorstop_version` | [UnityDoorstop 4.5.0](https://github.com/NeighTools/UnityDoorstop/releases/tag/v4.5.0) | 文件版本 `4.5.0.0` | [GNU LGPL 2.1](https://github.com/NeighTools/UnityDoorstop/blob/v4.5.0/LICENSE) | 已随包附 `UnityDoorstop-LGPL-2.1.txt` 与未修改的 `UnityDoorstop-v4.5.0-source.zip` |
| `NotoSansCJKsc-Regular.otf` | [Noto Sans CJK](https://github.com/notofonts/noto-cjk) | 官方静态 Simplified Chinese Regular；由构建清单 SHA-256 固定 | [SIL OFL 1.1](https://github.com/notofonts/noto-cjk/blob/main/Sans/LICENSE) | 已有全文；构建脚本复制到 `licenses/` 与字体目录 |

`BepInEx.Harmony.dll` 与两个互操作 DLL 的归属依据是 BepInEx.Harmony 官方仓库同时包含 `BepInEx.Harmony`、`HarmonyX2Interop` 和 `HarmonyXInterop` 三个项目。BepInEx 5.4.23.5 标签页列出的依赖版本与本地程序集元数据并不完全一致，因此版本号只记录可直接读取的本地标识；取得许可证文件时还应以所用官方发布包或确定提交再次核对。

## 公开 ZIP 至少应包含

- `THIRD_PARTY_NOTICES.md`：本清单。
- `BepInEx-MIT.txt`：BepInEx 5.4.23.5 项目本体。
- `BepInExHarmony-MIT.txt`：BepInEx.Harmony 与互操作 DLL。
- `HarmonyX-MIT.txt` 与 `Harmony-original-MIT.txt`：两份不同版权声明。
- `MonoMod-MIT.txt`。
- `MonoCecil-MIT.txt`。
- `UnityDoorstop-LGPL-2.1.txt`，以及完成 LGPL 分发要求所需的源代码取得说明或其他材料。
- `NotoSansSC-OFL.txt`；字体目录继续保留 `OFL.txt`。

构建脚本会逐一检查以上文件并复制到 `licenses/`；缺少许可证正文或 UnityDoorstop 对应源代码时拒绝生成 ZIP。
