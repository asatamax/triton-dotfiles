# Triton Dotfiles

> 暗号化とAIフレンドリーな設定管理を備えた、セキュアなマルチマシンdotfiles管理ツール

[![Release](https://img.shields.io/github/v/release/asatamax/triton-dotfiles)](https://github.com/asatamax/triton-dotfiles/releases)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

![Triton TUI](documents/triton-tui.png)

## なぜTriton？

複数マシン間でのdotfiles管理は面倒な作業です：
- 手動でのファイルコピーはミスが起きやすい
- 機密ファイル（SSH鍵、認証情報）は暗号化が必要
- マシン間で何が変わったかを追跡するのは手間がかかる

Tritonはこれらを解決します：
- **一元管理** - プライベートGitリポジトリに集約
- **選択的暗号化** - 機密ファイルをAES-256-GCMで暗号化
- **ビジュアル差分** - 任意の2台のマシン間を比較
- **ワンコマンド同期** - 既存ファイルの自動バックアップ付き

## 機能

- **マルチマシン同期** - 各マシンがリポジトリ内に専用フォルダを持つ
- **選択的暗号化** - SSH鍵や認証情報は暗号化、設定ファイルはそのまま
- **インタラクティブTUI** - ファイルの閲覧、比較、復元を視覚的に
- **AIフレンドリーCLI** - `--schema`オプションでLLMエージェント向けJSON出力
- **安全な復元** - 上書き前に既存ファイルをアーカイブ
- **Git統合** - コミット/プッシュワークフローを内蔵

## 必要条件

- Python 3.11以上
- Git（リポジトリストレージ用）

## インストール

```bash
# uv を使用（推奨）
uv tool install git+https://github.com/asatamax/triton-dotfiles.git

# pipx を使用
pipx install git+https://github.com/asatamax/triton-dotfiles.git

# インストール確認
triton --version
```

## クイックスタート

```bash
# 1. セットアップウィザードを実行
triton init

# 2. ウィザードがガイドします：
#    - ~/.config/triton/ ディレクトリの作成
#    - 暗号化キー（master.key）の生成
#    - vault（Gitリポジトリ）のセットアップ
#    - 初期バックアップ対象の選択

# 3. 最初のバックアップを作成
triton backup

# 4. リポジトリにコミット＆プッシュ
triton git-commit-push
```

## 使い方

### TUI（推奨）

インタラクティブターミナルブラウザを起動：

```bash
triton
```

**キーボードショートカット：**
| キー | 操作 |
|-----|--------|
| `?` | すべてのショートカットを表示 |
| `Space` | ファイルを選択 |
| `R` | 選択したファイルを復元 |
| `d` | 差分ビューを表示 |
| `s` | 分割ビュー（ローカル vs バックアップ） |
| `m` | マシンを切り替え |
| `Ctrl+P` | コマンドパレット |
| `q` | 終了 |

### CLI

```bash
triton status                    # 現在の状態を表示
triton backup                    # 現在のマシンをバックアップ
triton restore <machine>         # 別マシンから復元
triton diff <machine1> <machine2> # 2台のマシンを比較
triton export <machine> <file> <dest>  # 特定ファイルをエクスポート
```

変更を加えずに操作をプレビューするには `--dry-run` を使用。

## 設定

Tritonは設定を `~/.config/triton/` に保存します：

```
~/.config/triton/
├── config.yml    # バックアップ対象と設定
├── master.key    # 暗号化キー（安全に保管！）
└── archives/     # 復元前の安全バックアップ
```

### バックアップ対象の追加

**推奨：AIアシスタントを使用**

Claude Codeなどのツールを使用している場合、`triton-config`スキルで設定を管理できます：

```bash
# AIが以下のようなコマンドを実行できます：
triton config target add ~/.ssh --recursive
triton config target add ~/ --files '.zshrc,.gitconfig'
```

**手動設定：** 詳細は [documents/CONFIGURATION.md](documents/CONFIGURATION.md) を参照。

## セキュリティ

### master.keyについて

`master.key`ファイルは機密ファイルの暗号化キーです。

**重要：**
- `triton init`実行時に暗号学的に安全な乱数で生成
- `id_rsa*`、`credentials`、`*.pem`などのパターンにマッチするファイルの暗号化に使用
- **Gitにはコミットされない**（tritonが保護）
- **紛失すると暗号化ファイルは復号できません**

**バックアップの推奨：**
- パスワードマネージャーに保存（1Password、Bitwardenなど）
- セキュアなUSBドライブに保管
- 信頼できるマシンへはセキュアな方法で共有（メールは不可！）

### 暗号化の仕組み

```
バックアップ:  ~/.ssh/id_rsa  →  repo/Machine/.ssh/id_rsa.enc  (暗号化)
復元:         repo/Machine/.ssh/id_rsa.enc  →  ~/.ssh/id_rsa  (復号化)
```

設定ファイル（`.zshrc`、`.gitconfig`）はリポジトリ内で読み取り可能なまま保存されます。

## ライセンス

MITライセンス - 詳細は [LICENSE](LICENSE) を参照。

---

**リンク：** [バグ報告](https://github.com/asatamax/triton-dotfiles/issues) | [ドキュメント](documents/CONFIGURATION.md)
