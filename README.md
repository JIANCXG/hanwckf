<img src="https://avatars.githubusercontent.com/u/53193414?s=200&v=4" alt="logo" width="200" height="200" align="right">

# Project ImmortalWrt

ImmortalWrt is a fork of [OpenWrt](https://openwrt.org), with more packages ported, more devices supported, better performance, and special optimizations for mainland China users.<br/>
Compared the official one, we allow to use hacks or non-upstreamable patches / modifications to achieve our purpose. Source from anywhere.

Default login address: http://192.168.1.1 or http://immortalwrt.lan, username: __root__, password: _none_.

## About immortalwrt-mt798x 
- https://cmi.hanwckf.top/p/immortalwrt-mt798x/

## AX3000T PassWall 自动检查

GitHub Actions 每隔至少 **72 小时**检查 PassWall、配套依赖及 packages、luci、routing、telephony 四个基础软件源，发现变化后自动编译四种 AX3000T 固件并发布到 Releases。PassWall 使用 main 分支，基础软件源使用 openwrt-21.02 分支；全部查询成功后统一锁定精确提交，编译阶段不跟随分支头漂移。工作流每小时第 17 分钟唤醒，距离上次成功检查不足 72 小时会直接跳过，不查询上游；实际检查时间可能受 GitHub 调度延迟影响。检查时间保存在 `.github/ax3000t-passwall-last-check.json`，跨月仍按经过的小时计算。

无更新时只记录检查时间，不重新编译；上游检查失败不推进时间，下次唤醒时重试。手动运行及相关源码推送可立即检查，手动勾选 `force` 可强制重新编译。成功发布记录独立保存，检查时间变化不会触发重复编译。

若检查成功但编译或发布失败，自动重试要等到该次检查满 72 小时，也可手动重试；当前源码或固定版本尚未成功发布时，即使没有新的上游提交也会再次构建。发布前逐一检查四种固件的分区容量、镜像 SHA256，以及 PassWall、Xray、Sing-box、Dnsmasq 的存在性和版本，校验失败则停止发布。详细说明见 [`config/ax3000t-passwall/README.md`](config/ax3000t-passwall/README.md)。

## Development
To build your own firmware you need a GNU/Linux, BSD or MacOSX system (case sensitive filesystem required). Cygwin is unsupported because of the lack of a case sensitive file system.<br/>

  ### Requirements
  To build with this project, Ubuntu 20.04 LTS is preferred. And you need use the CPU based on AMD64 architecture, with at least 4GB RAM and 25 GB available disk space. Make sure the __Internet__ is accessible.

  The following tools are needed to compile ImmortalWrt, the package names vary between distributions.

  - Here is an example for Ubuntu users:<br/>
    - Method 1:
      <details>
        <summary>Setup dependencies via APT</summary>

        ```bash
        sudo apt update -y
        sudo apt full-upgrade -y
        sudo apt install -y ack antlr3 asciidoc autoconf automake autopoint binutils bison build-essential \
          bzip2 ccache clang clangd cmake cpio curl device-tree-compiler ecj fastjar flex gawk gettext gcc-multilib \
          g++-multilib git gperf haveged help2man intltool lib32gcc-s1 libc6-dev-i386 libelf-dev libglib2.0-dev \
          libgmp3-dev libltdl-dev libmpc-dev libmpfr-dev libncurses5-dev libncursesw5 libncursesw5-dev libreadline-dev \
          libssl-dev libtool lld lldb lrzsz mkisofs msmtp nano ninja-build p7zip p7zip-full patch pkgconf python2.7 \
          python3 python3-pip python3-ply python3-docutils qemu-utils re2c rsync scons squashfs-tools subversion swig \
          texinfo uglifyjs upx-ucl unzip vim wget xmlto xxd zlib1g-dev
        ```
      </details>
    - Method 2:
      ```bash
      sudo bash -c 'bash <(curl -sL https://build-scripts.immortalwrt.eu.org/init_build_environment.sh)'
      ```

  Note:
  - Do everything as an unprivileged user, not root, without sudo.
  - Using CPUs based on other architectures should be fine to compile ImmortalWrt, but more hacks are needed - No warranty at all.
  - You must __not__ have spaces or non-ascii characters in PATH or in the work folders on the drive.
  - If you're using Windows Subsystem for Linux (or WSL), removing Windows folders from PATH is required, please see [Build system setup WSL](https://openwrt.org/docs/guide-developer/build-system/wsl) documentation.
  - Using macOS as the host build OS is __not__ recommended. No warranty at all. You can get tips from [Build system setup macOS](https://openwrt.org/docs/guide-developer/build-system/buildroot.exigence.macosx) documentation.
  - For more details, please see [Build system setup](https://openwrt.org/docs/guide-developer/build-system/install-buildsystem) documentation.

  ### Quickstart
  1. Run `git clone --depth=1 https://github.com/hanwckf/immortalwrt-mt798x.git` to clone the source code.
  2. Run `cd immortalwrt-mt798x` to enter source directory.
  3. Run `./scripts/feeds update -a` to obtain all the latest package definitions defined in feeds.conf / feeds.conf.default
  4. Run `./scripts/feeds install -a` to install symlinks for all obtained packages into package/feeds/
  5. Copy the configuration file for your device from the `defconfig` directory to the project root directory and rename it `.config`
     
     ```
     # MT7981
     cp -f defconfig/mt7981-ax3000.config .config

     # MT7986
     cp -f defconfig/mt7986-ax6000.config .config
     
     # MT7986 256M Low Memory
     cp -f defconfig/mt7986-ax6000-256m.config .config
     ```
     
  7. Run `make menuconfig` to select your preferred configuration for the toolchain, target system & firmware packages.
  8. Run `make -j$(nproc)` to build your firmware. This will download all sources, build the cross-compile toolchain and then cross-compile the GNU/Linux kernel & all chosen applications for your target system.

  ### Related Repositories
  The main repository uses multiple sub-repositories to manage packages of different categories. All packages are installed via the ImmortalWrt package manager called opkg. If you're looking to develop the web interface or port packages to ImmortalWrt, please find the fitting repository below.
  - [LuCI Web Interface](https://github.com/immortalwrt/luci): Modern and modular interface to control the device via a web browser.
  - [ImmortalWrt Packages](https://github.com/immortalwrt/packages): Community repository of ported packages.
  - [OpenWrt Routing](https://github.com/openwrt/routing): Packages specifically focused on (mesh) routing.

## Support Information
For a list of supported devices see the [OpenWrt Hardware Database](https://openwrt.org/supported_devices)
  ### Documentation
  - [Quick Start Guide](https://openwrt.org/docs/guide-quick-start/start)
  - [User Guide](https://openwrt.org/docs/guide-user/start)
  - [Developer Documentation](https://openwrt.org/docs/guide-developer/start)
  - [Technical Reference](https://openwrt.org/docs/techref/start)

  ### Support Community
  - Support Chat: group [@ctcgfw_openwrt_discuss](https://t.me/ctcgfw_openwrt_discuss) on [Telegram](https://telegram.org/).
  - Support Chat: group [#immortalwrt](https://matrix.to/#/#immortalwrt:matrix.org) on [Matrix](https://matrix.org/).

## License
ImmortalWrt is licensed under [GPL-2.0-only](https://spdx.org/licenses/GPL-2.0-only.html).

## Acknowledgements
<table>
  <tr>
    <td><a href="https://dlercloud.com/"><img src="https://user-images.githubusercontent.com/22235437/111103249-f9ec6e00-8588-11eb-9bfc-67cc55574555.png" width="183" height="52" border="0" alt="Dler Cloud"></a></td>
    <td><a href="https://www.jetbrains.com/"><img src="https://resources.jetbrains.com/storage/products/company/brand/logos/jb_square.png" width="120" height="120" border="0" alt="JetBrains Black Box Logo logo"></a></td>
    <td><a href="https://sourceforge.net/"><img src="https://sourceforge.net/sflogo.php?type=17&group_id=3663829" alt="SourceForge" width=200></a></td>
  </tr>
</table>
