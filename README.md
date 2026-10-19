# SFTPCN · 更好上手的中文 SFTP 后台

基于 SFTPGo 社区版的 Ubuntu 一键部署方案。默认装好中文界面，通过 **服务器 IP + 端口** 打开后台，为每位用户单独管理目录、传输权限和登录 IP 白名单。

**[产品介绍](https://huahaotech.github.io/sftpcn/) · [文案规范](docs/LOCALIZATION.md) · [验收步骤](docs/ACCEPTANCE.md)**

SFTPCN 是部署和中文适配项目，底层使用官方 SFTPGo，不是另写的 SSH 服务。当前版本 0.1.0，固定使用 SFTPGo 2.7.6，不跟随 `latest` 自动升级。

## 一键安装

支持 Ubuntu 22.04 / 24.04 / 26.04；推荐 amd64 或 arm64。需要 root/sudo 及访问 Ubuntu 软件源、GitHub、Docker Hub 的网络。

```bash
curl -fsSL https://raw.githubusercontent.com/huahaotech/sftpcn/main/install.sh -o /tmp/sftpcn-install.sh && sudo bash /tmp/sftpcn-install.sh
```

也可以先下载仓库、查看源码，再在项目目录执行：

```bash
sudo bash install.sh
```

安装完成后直接打开：

```text
http://你的服务器IP:8080/web/admin?lng=zh
```

首次访问按提示输入安装器显示的随机初始化代码，创建自己的管理员账号。代码另存于 `/opt/sftpcn/SETUP.txt`，没有默认管理员密码。

## 默认配置

| 项目 | 默认值 |
| --- | --- |
| 管理后台 | TCP 8080，直接通过 IP 访问 |
| SFTP 文件传输 | TCP 2022 |
| 原有管理 SSH | 保留原配置，通常为 TCP 22 |
| 访问协议 | 仅开启 SFTP，关闭 FTP、WebDAV、网页文件传输和 SSH 命令 |
| 用户类型 | SFTPGo 虚拟用户，不创建 Linux 登录账号 |
| 数据位置 | `/opt/sftpcn`，文件和账号数据独立持久保存 |
| 默认语言 | 简体中文，支持切换英文 |

后台初始提供 HTTP，正式对公网使用时，应在前面配置 HTTPS 反向代理，或限制管理来源 IP。安装器不会改写现有防火墙或 SSH 配置；请在云安全组/UFW 放行实际使用的端口。

如 UFW 已启用，可按实际管理 IP 放行后台，同时保留现有 SSH 规则：

```bash
sudo ufw allow from 你的管理公网IP to any port 8080 proto tcp
sudo ufw allow 2022/tcp
sudo ufw status
```

不要在未确认 SSH 放行规则时直接启用或重置防火墙。

## 自定义端口

```bash
sudo bash install.sh --web-port 18080 --sftp-port 12022

# 仅允许本机或反向代理访问后台
sudo bash install.sh --web-bind 127.0.0.1
```

已有相同目录、同名容器或端口被占用时安装器会停止，避免覆盖数据。低于 1024 的端口不受支持，保留系统原有 SSH 服务。

### 国内网络与离线镜像

安装器优先使用本机已有的固定版本镜像，没有时依次尝试 Docker Hub 和官方 GitHub Container Registry；每次拉取最多等待 120 秒。不会修改系统镜像源，也不使用未知的第三方镜像。

如果两个官方仓库都无法访问，可以在可联网、CPU 架构与目标机相同的可信机器上执行：

```bash
docker pull drakkan/sftpgo:v2.7.6
docker save drakkan/sftpgo:v2.7.6 -o sftpgo-v2.7.6.tar
sha256sum sftpgo-v2.7.6.tar
```

将镜像文件通过自己的 SSH 通道传到目标服务器，核对传输前后的 SHA256，再执行：

```bash
sudo docker load -i sftpgo-v2.7.6.tar
sudo bash install.sh
```

安装器会复用已导入的固定版本镜像，无需再连接远程镜像仓库。

## 第一次使用

1. 创建管理员并进入“用户管理”，点击“新建用户”。
2. 设置用户名、密码或公钥，选用本地磁盘存储。
3. 用户根目录留空可自动按用户名生成，也可填写 `/srv/sftpgo/data/alice`。每人使用不同目录；目录在首次成功登录时自动创建。
4. 在“登录 IP 白名单”填写真实的客户出口 IP。例如单个 IPv4 使用 `192.0.2.10/32`，IPv6 使用 `2001:db8::1/128`，网段使用 `192.0.2.0/24`。示例地址必须换成实际地址。
5. 给根目录 `/` 设置所需的列目录、上传、下载、创建目录等权限。
6. WinSCP、FileZilla 选择 **SFTP**，填写服务器地址、2022 端口和新建的用户凭据。

**空白名单表示“不限制来源”，不是“禁止所有人”。** 全局 IP 访问规则、自动封禁豁免与单个账号的登录白名单不是同一个功能。不要混用。

修改权限或白名单时，勾选“保存后断开该用户的现有连接”，让新设置立即作用于后续登录。

## 账号辅助命令

所有操作也可以在 Web 后台完成。辅助工具会要求非空 IP 白名单，密码交互输入，不放在命令行中：

```bash
sudo python3 /opt/sftpcn/sftpctl.py create alice --ip 客户公网IP
sudo python3 /opt/sftpcn/sftpctl.py allow alice --ip 客户公网IP/32
sudo python3 /opt/sftpcn/sftpctl.py disable alice
sudo python3 /opt/sftpcn/sftpctl.py enable alice
sudo python3 /opt/sftpcn/sftpctl.py password alice
sudo python3 /opt/sftpcn/sftpctl.py delete alice
```

管理员不叫 `admin` 时，在子命令前加 `--admin 管理员名`。删除账号保留用户文件。重新创建同名用户或使用相同目录会重新暴露原文件，应先核对文件归属。

## 运维与备份

```bash
sudo docker logs --tail 100 sftpcn
sudo docker restart sftpcn
sudo python3 /opt/sftpcn/backup.py
```

备份短暂停止服务，完成或异常后恢复原运行状态；已有传输会中断。备份位于 `/var/backups/sftpcn`，包含文件、数据库、配置、主机密钥与中文 UI，需安全保管。

| 宿主机路径 | 用途 |
| --- | --- |
| `/opt/sftpcn/data/data/用户名` | 用户文件 |
| `/opt/sftpcn/state` | 数据库和 SSH 主机密钥 |
| `/opt/sftpcn/config/sftpgo.json` | 服务配置 |
| `/opt/sftpcn/ui` | 匹配当前镜像的模板和中文语言资源 |

停止、移除服务容器会保留目录：`sudo docker stop sftpcn`，然后 `sudo docker rm sftpcn`。本项目不提供自动删除用户文件或数据目录的命令。

## 中文适配

1,040 个语言条目与 2.7.6 英文基准逐项匹配；476 项按实际功能重新表述。修正了“断开连接”误写成“删除”、将动态验证码译成密码、将对象路径前缀译成密钥前缀等问题。

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_locale.py
```

新版本不应直接覆盖旧语言文件；需要按上游英文基准核对全部键和变量，再验证模板兼容性。

## GitHub Pages

展示页源码位于 `docs/`，仓库内含 Pages 自动部署工作流。仓库管理员首次在 **Settings → Pages → Source** 选择 **GitHub Actions**，推送到 `main` 后即可发布。网站是产品介绍与交互示意，不是可登录的真实后台，不连接任何生产服务器。

## 许可

项目遵循 AGPL-3.0-only，详见 [LICENSE](LICENSE) 与 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。SFTPGo 品牌与 Web UI 附加许可归上游所有，本项目不把其完整主题重新发布为通用模板。
