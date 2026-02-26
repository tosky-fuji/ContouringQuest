# Contouring Quest

PySide6 ベースの医用画像コンツーリング教育アプリケーションです。
CT 画像上で ROI（関心領域）を描画し、正解データとの比較でスコアリングを行います。

> **対応 OS:** Windows 11

---

## ディレクトリ構成

```
Contouring_Quest/
├── app/                         … アプリケーション本体
│   ├── __main__.py              … エントリポイント
│   ├── common/                  … 共通ユーティリティ
│   ├── contouring/              … コンツーリング機能
│   ├── hub/                     … メイン画面
│   ├── leaderboard/             … リーダーボード
│   ├── review/                  … おさらい画面
│   └── scoring/                 … スコアリング
├── contour_quest_config.json    … 設定ファイル
├── nifti/                       … CT・正解ラベル（NIfTI 形式）
├── records/                     … 実行結果の出力先
│   └── csv/                     … スコア CSV
├── LICENSES/                    … ライセンス全文
├── NOTICES/                     … サードパーティ通知
├── requirements.txt             … pip 依存パッケージ一覧
├── 0_install.bat                … tar.gz 展開用インストーラー
└── run.bat                      … アプリ起動スクリプト
```

---

## インストール方法

### 方法 A: 自分で環境構築する場合（requirements.txt）

Python 環境を自分で用意し、pip でパッケージをインストールします。

#### 1. Python 3.11 のインストール

以下のいずれかの方法で Python 3.11 を用意してください。

**pip（venv）の場合:**

```bat
python -m venv contouring_env
contouring_env\Scripts\activate
```

**conda の場合:**

```bat
conda create -n contouring python=3.11
conda activate contouring
```

#### 2. 依存パッケージのインストール

```bat
pip install -r requirements.txt
```

`requirements.txt` の内容:

| パッケージ | 用途 |
|-----------|------|
| PySide6 | GUI フレームワーク（Qt for Python） |
| numpy | 数値計算 |
| nibabel | NIfTI ファイル読み書き |
| scipy | 画像処理（膨張処理等） |
| scikit-image | 画像解析 |

#### 3. NIfTI データの配置

`nifti/` フォルダに CT 画像と正解ラベルを配置します（後述）。

#### 4. 起動

```bat
cd Contouring_Quest
python -m app
```

---

### 方法 B: 配布パッケージを使う場合（tar.gz）

conda-pack で作成済みの Python 環境（`app_env.tar.gz`）を展開して使います。
Python のインストールやパッケージ管理は不要です。

#### 1. zip の展開

配布された zip ファイルを任意のフォルダに展開します。

#### 2. インストール（初回のみ）

`0_install.bat` をダブルクリックします。

このスクリプトが行うこと:
- `app_env.tar.gz` を `app_env/` に展開（3〜10 分程度）
- `conda-unpack` でパスを修正
- `records/` と `nifti/` ディレクトリの作成
- デスクトップショートカットの作成

```
展開後の app_env/ には Python 本体と全依存パッケージが含まれます。
PC のシステムには何もインストールされません。
```

#### 3. NIfTI データの配置

`nifti/` フォルダに CT 画像と正解ラベルを配置します（後述）。

#### 4. 起動

以下のいずれかで起動します:
- デスクトップの **Contouring Quest** ショートカット
- `run.bat` をダブルクリック

---

## NIfTI データの準備

アプリの動作には NIfTI 形式（`.nii.gz`）の CT 画像と正解ラベルが必要です。
`nifti/` フォルダに配置してください。

```
nifti/
├── abdominal_ct.nii.gz     … CT 画像
├── h1.nii.gz               … 正解ラベル（セット1）
├── h1_labels.json           … ラベル定義（セット1）
├── h2.nii.gz               … 正解ラベル（セット2）
└── h2_labels.json           … ラベル定義（セット2）
```

パスは `contour_quest_config.json` で管理されています。
設定画面からも変更できます（パスワード: `kochi`）。

---

## 使い方

### コンツーリング

1. アプリを起動するとハブ画面が表示されます
2. 問題セット（Region）を選択してコンツーリングを開始します
3. CT 画像上で ROI を描画します
4. 制限時間内に描画を完了してください

### 結果の確認（リーダーボード）

全員の結果を確認するには、各参加者の `records/` フォルダを 1 か所に集めてから
リーダーボード画面を開きます。

### おさらい（レビュー）

レビュー画面で自分や他の参加者の描画結果を正解と重ねて確認できます。
CSV と NIfTI の両方が必要です。

---

## 設定の変更

ハブ画面の右上ボタンからパスワード `kochi` を入力すると設定画面に入れます。
ROI セットの追加・変更、CT データのパス変更などが可能です。

---

## 結果データ

実行結果は `records/` フォルダに保存されます:

```
records/
├── csv/              … スコア CSV ファイル
└── Group_X/          … 描画した ROI（NIfTI）と詳細 JSON
```

---

## ライセンス

本アプリケーションのソースコードは **MIT License** で公開されています。詳細は [LICENSE](LICENSE) を参照してください。

### 使用ライブラリ

| ライブラリ | ライセンス |
|-----------|-----------|
| PySide6 / Qt for Python | LGPL-3.0 |
| NumPy | BSD-3-Clause |
| nibabel | MIT |
| SciPy | BSD-3-Clause |
| scikit-image | BSD-3-Clause |

- 各ライブラリのライセンス全文は `LICENSES/` フォルダに同梱されています
- PySide6 の LGPL 準拠情報は `NOTICES/Qt-For-Python-NOTICE.txt` を参照してください
- PySide6 は動的リンクで使用しており、DLL の差し替えが可能です（LGPL-3.0 §4(d)-(e)）
