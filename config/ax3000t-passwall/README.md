# AX3000T / PassWall

在 Linux x86_64（例如 WSL Ubuntu）下，在仓库根目录执行：

```sh
sh scripts/setup-ax3000t-passwall.sh
```

脚本更新 `feeds.conf.default` 指定提交的 feeds，应用兼容补丁并载入配置，不编译固件。
所有六个 feeds 均固定到精确提交；编译不会跟随软件源分支头漂移。
现有 `.config` 会备份为 `.config.before-passwall`。自定义的 `feeds.conf`
须先自行保存并移走，避免覆盖。再次更新 feeds 后也应重新运行本脚本。

PassWall 和代理核心版本以 `feeds.conf.default` 及每次发布的 `build-info.json` 为准；启用中文、iptables、
SSR 客户端、HAProxy、Simple-Obfs、V2Ray-Plugin、UPnP（miniupnpd 和中文管理界面）等，取消 filetransfer。
配置同时选择普通/AN8855、stock/大分区四种设备配置，刷机必须匹配实际硬件和分区。
stock 配置按本仓库 DTS/升级脚本将内核放在 34 MiB 的 `ubi_kernel`、rootfs 放在
78 MiB 的 `ubi`，普通配置共用 112 MiB 的 `ubi`。云编译按对应布局校验镜像、
分区容量和 SHA256，任何一个缺失或超限都会报错并停止发布。
四种固件的软件包清单还必须包含与本次固定源码配方一致的 PassWall、Xray、Sing-box
及 Dnsmasq 版本；缺失或版本不符会阻止发布。PassWall 按旧版 LuCI 兼容补丁生成的
版本号校验，其他包按 OpenWrt 21.02 的 `<版本>-<release>` 格式校验。

兼容补丁包括 LuCI 版本号/legacy iptables、官方 Go 1.27.3 Linux amd64
预编译宿主工具链（带 SHA256 校验）、SSR configure 执行权限，以及仅对
Sing-box transport/wireguard 禁用内联以避开编译器崩溃。
Rust 构建基础设施来自 OpenWrt packages openwrt-23.05，保留原版权声明；
当前不启用 Rust 代理核心，也未验证 Rust 编译。

## 自动更新和云编译

工作流：`.github/workflows/ax3000t-passwall.yml`，仅在 `JIANCXG/hanwckf` 运行。

- 每小时第 17 分钟唤醒；距上次成功检查至少 72 小时才查询上游。
  检查 PassWall 和 passwall-packages 的 main 分支，以及 packages、luci、routing、
  telephony 的 openwrt-21.02 分支。GitHub 调度可能延迟，跨月仍按经过的小时计算。
- 全部查询成功后，统一更新 `feeds.conf.default` 中的六条固定提交。
  所有软件源版本均参与构建指纹；与上次成功发布的源码、配置和固定版本一致时不编译，
  只记录检查时间。源码依赖可追溯不等于承诺固件逐字节可复现。
- 使用同一次编译生成普通、普通 stock、AN8855、AN8855 stock 四种固件。
  保留原有软件包组合，不自动删减 stock 软件包。
- 四种固件全部通过文件、软件包和容量检查后，上传 GitHub Actions artifact（30 天）
  并创建 GitHub Release，附 SHA256、软件包清单、配置和源提交。
- 仅在发布成功后提交 `.github/ax3000t-passwall-last-success.json`，因此编译失败不会
  被误记为已发布。上游查询失败不推进检查时间，下次每小时唤醒会再次查询；
  如果上游查询成功但编译或发布失败，自动重试仍须等到本次检查满 72 小时，
  也可手动运行或重新运行失败任务。运行中的编译不会被下个定时任务取消。
- Actions → **AX3000T PassWall Auto Build** → **Run workflow** 可手动检测；
  勾选 `force` 可强制重编译。首次运行没有成功记录，会直接编译。
- 本工作流需要 Actions 已启用及内置 `GITHUB_TOKEN` 的 Contents 写权限；不需要 PAT。
  GitHub 对长期无仓库活动的公开仓库可能停用定时任务，停用后须手动重新启用。
- 上游未来改变依赖或破坏 21.02 兼容性时，补丁/编译会明确失败，需修复后继续；
  自动更新不保证每次上游提交都能成功编译。

本地检查：`python3 -m unittest discover -s scripts/ci/tests -v`。
设备运行仍需实机验证；此仓库不包含构建缓存、代理设置或日志。
