# AX3000T / PassWall

在 Linux x86_64（例如 WSL Ubuntu）下，在仓库根目录执行：

```sh
sh scripts/setup-ax3000t-passwall.sh
```

脚本更新固定提交的 feeds，应用兼容补丁并载入配置，不编译固件。
现有 `.config` 会备份为 `.config.before-passwall`。自定义的 `feeds.conf`
须先自行保存并移走，避免覆盖。再次更新 feeds 后也应重新运行本脚本。

PassWall 26.10.16-2、Xray 26.10.17、Sing-box 1.14.3；启用中文、iptables、
SSR 客户端、HAProxy、Simple-Obfs、V2Ray-Plugin 等，取消 filetransfer。
配置同时选择普通/AN8855、stock/大分区四种设备配置，刷机必须匹配实际硬件和分区。
stock 镜像大小上限约 34 MiB，当前插件组合可能超过限制。

兼容补丁包括 LuCI 版本号/legacy iptables、官方 Go 1.27.3 Linux amd64
预编译宿主工具链（带 SHA256 校验）、SSR configure 执行权限，以及仅对
Sing-box transport/wireguard 禁用内联以避开编译器崩溃。
Rust 构建基础设施来自 OpenWrt packages openwrt-23.05，保留原版权声明；
当前不启用 Rust 代理核心，也未验证 Rust 编译。

已通过：配置生成、Go host、mbedTLS、SSR 和 Sing-box 单包构建。
整机固件完整构建与设备运行尚待验证。这里不包含固件、构建缓存、代理设置或日志。
