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

配布された zip ファイルを任意のフォルダに展開し、`0_install.bat` をダブルクリックしてください。

このスクリプトが行うこと:
- `app_env.tar.gz` を `app_env/` に展開（3〜10 分程度）
- `conda-unpack` でパスを修正
- `records/` と `nifti/` ディレクトリの作成
- デスクトップショートカットの作成

> PC のシステムには何もインストールされません。フォルダ内に展開するのみです。

### 起動

以下のいずれかで起動します:
- デスクトップの **Contouring Quest** ショートカット
- `run.bat` をダブルクリック

> **補足:** Python 環境をお持ちの方は、`pip install -r requirements.txt` でパッケージを導入し `python -m app` で直接起動することもできます。

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
