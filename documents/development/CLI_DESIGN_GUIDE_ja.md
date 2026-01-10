# CLI Design Guide

Triton CLI の出力フォーマットとスタイルに関するガイドライン。

## 基本原則

1. **絵文字は使用しない** - 📁🔧✅ などの絵文字は幅が不安定でレイアウトが崩れる
2. **Unicode記号は使用可** - ✓✗!⚫⚪ などの記号は幅が安定している
3. **色とプレフィックスを組み合わせる** - 色覚多様性への配慮、ログ出力時の可読性確保

## カラーリング

| 用途 | 色 | Colorama |
|------|-----|----------|
| 成功・存在・追加 | 緑 | `Fore.GREEN` |
| 警告・変更 | 黄 | `Fore.YELLOW` |
| エラー・失敗・削除 | 赤 | `Fore.RED` |
| 情報・ラベル | シアン | `Fore.CYAN` |
| 通常テキスト | デフォルト | `Style.RESET_ALL` |

## コマンド種別による表現の使い分け

### 設定系コマンド（状態確認・検証）

`config validate`, `config target list`, `config target check` など

記号ベースの表現を使用：

```
✓ ~/.ssh/config
✗ ~/.tmux.conf (not found)
! Path does not exist: /Users/hiro/.m2
```

| 状態 | 記号 | 色 |
|------|------|-----|
| 成功・存在 | `✓` | 緑 |
| 失敗・不在 | `✗` | 赤 |
| 警告 | `!` | 黄 |

### 動作系コマンド（実行・変更）

`backup`, `restore`, `git-commit-push`, `export` など

テキストプレフィックスを使用：

```
Error: Failed to copy ~/.zshrc - Permission denied
Warning: File already exists, creating backup
```

| 状態 | プレフィックス | 色 |
|------|---------------|-----|
| エラー | `Error:` | 赤 |
| 警告 | `Warning:` | 黄 |
| 成功 | （情報付き完了文） | 緑またはデフォルト |

## 差分表示（Git風）

```
M .aws/config          # Modified（黄）
+ .config/bat/config   # Added（緑）
- .old/removed.txt     # Deleted（赤）
```

| 状態 | プレフィックス | 色 |
|------|---------------|-----|
| 変更 | `M` | 黄 |
| 追加 | `+` | 緑 |
| 削除 | `-` | 赤 |

差分詳細表示（unified diff形式）:
```
  --- a/.aws/config
  +++ b/.aws/config
  @@ -3,10 +3,6 @@        # シアン
  -removed line           # 赤
  +added line             # 緑
```

## リスト表示

### index番号

リスト項目にはindex番号を付与（緑色）：

```
Targets:
  [0] ~/.config/triton (recursive)
  [1] ~/.ssh (recursive)
  [2] ~/.aws (recursive)
```

将来的な番号指定オプション追加に備える。

### マシン一覧

現在のマシンを `⚫`、他のマシンを `⚪` で表示：

```
Available machines:
  ⚪ HomePC (91 files)
  ⚫ WorkLaptop (62 files)
  ⚪ OfficeDesktop (75 files)
```

## メッセージフォーマット

### 見出し・セクション

シンプルに、必要に応じて色を付ける：

```python
click.echo(f"{Fore.CYAN}Targets:{Style.RESET_ALL}")
```

### サマリー

コンパクトな1行形式：

```
0 errors, 9 warnings
37 unchanged, 18 modified, +36, -7
```

### 完了メッセージ

情報を含める：

```
Backup complete: 62 files copied
Restore complete: 5 files restored
```

### 確認プロンプト

目的を明確に記述：

```
Restore 5 files to ~/.config? [y/N]:
Delete 3 orphaned files? [y/N]:
```

### dry-run表示

括弧形式：

```
(dry-run) Would copy ~/.zshrc
(dry-run) Would delete ~/.old/config
```

### プログレス表示

ファイル名を出力（ログとして参照可能）：

```
Copying ~/.zshrc
Copying ~/.vimrc
Copying ~/.config/git/ignore
Backup complete: 62 files copied
```

## 例外ルール

原則として本ガイドに従う。例外が必要な場合は、コード内コメントに理由を明記する：

```python
# CLI Design Guide例外: ここでは記号を使わない理由は...
click.echo(f"{Fore.RED}Error: {message}{Style.RESET_ALL}")
```

## 実装例

### 設定系コマンド

```python
# 成功
click.echo(f"  {Fore.GREEN}✓{Style.RESET_ALL} {file_path}")

# 失敗
click.echo(f"  {Fore.RED}✗{Style.RESET_ALL} {file_path} (not found)")

# 警告
click.echo(f"  {Fore.YELLOW}!{Style.RESET_ALL} Path does not exist: {path}")
```

### 動作系コマンド

```python
# エラー
click.echo(f"{Fore.RED}Error: {message}{Style.RESET_ALL}")

# 警告
click.echo(f"{Fore.YELLOW}Warning: {message}{Style.RESET_ALL}")

# 完了
click.echo(f"Backup complete: {count} files copied")
```

### 差分表示

```python
# ファイル一覧
if status == "added":
    print(f"{Fore.GREEN}+ {path}{Style.RESET_ALL}")
elif status == "deleted":
    print(f"{Fore.RED}- {path}{Style.RESET_ALL}")
elif status == "modified":
    print(f"{Fore.YELLOW}M {path}{Style.RESET_ALL}")

# 差分詳細
if line.startswith("+"):
    print(f"  {Fore.GREEN}{line}{Style.RESET_ALL}")
elif line.startswith("-"):
    print(f"  {Fore.RED}{line}{Style.RESET_ALL}")
elif line.startswith("@@"):
    print(f"  {Fore.CYAN}{line}{Style.RESET_ALL}")
```
