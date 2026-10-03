# nomikai-navi

複数人の集合駅をさがす Web アプリ。鉄道・バスの時刻表と地図を使う。

## 作り

| | |
|---|---|
| 探索 | 自前の RAPTOR（`scripts/network.py`）。順方向＝最早到着、逆方向＝最遅出発。どちらも経路を復元できる |
| サーバ版 | `server.py`（Python 標準ライブラリのみ、ポート 8000）。任意の入力でその場で計算する |
| 静的版 | `scripts/build_static.py` で `site/` を作る。GitHub Pages 用 |
| 画面 | `frontend/index.html`（共通）＋ MapLibre GL JS。計算は `engine-server.js` / `engine-static.js` で差し替える |

## 動かす

```bash
python3 scripts/fetch_odpt.py     # 鉄道データを取得（ワークスペース直下の .env のトークンを使う）
python3 scripts/build_bars.py     # OSM から飲食店を抽出する（osmium が要る）
python3 scripts/build_index.py    # 索引をつくる
python3 server.py                 # http://127.0.0.1:8000/
```

```bash
python3 scripts/build_static.py       # site/ を作る（CPU 2 コアで約 30 分）
python3 scripts/verify_static.py --compare   # 静的版とサーバ版の答えを突き合わせる
python3 scripts/shot.py dark          # 画面キャプチャ
```

公開の手順と注意は [docs/deploy-github-pages.md](docs/deploy-github-pages.md)。

## データと出典

| データ | 提供元 | ライセンス |
|---|---|---|
| 列車時刻表・駅情報（鉄道 10 事業者 65 路線） | 公共交通オープンデータセンター | 事業者ごとに異なる（下記） |
| バス時刻表（GTFS-JP、3 事業者） | 公共交通オープンデータセンター | 公共交通オープンデータ基本ライセンス / CC BY 4.0 |
| 飲食店の位置 | OpenStreetMap | ODbL |
| 地図の下地 | OpenFreeMap / OpenMapTiles / OpenStreetMap | — |

- **東京都交通局**: CC BY 4.0
- **東京メトロ・つくばエクスプレス・東京臨海高速鉄道・多摩都市モノレール・横浜市交通局・関東バス・京王バス**:
  公共交通オープンデータ基本ライセンス
- **JR東日本・京王電鉄・東武鉄道・相模鉄道**: 公共交通オープンデータチャレンジ限定ライセンス

### 再配布についての注意

基本ライセンス第 8 条 4 項 (1) は、**元のデータの大部分を復元できる派生データ**を
第三者が再利用可能な状態で公開・再配布することを禁じている（チャレンジ限定ライセンスにも同じ条項がある）。

- 取得した時刻表は `data/raw/` に置き、**`.gitignore` で除外している**。
- 公開する `site/` に入れるのは**探索した結果の数値と経路の駅の並びだけ**で、時刻表そのものは入れない。
- 画面には、公共交通オープンデータセンター提供である旨・正確性を保証しない旨・問い合わせ先・
  静的データの取得日を出している（開発者ガイドライン 3.1）。表示内容は `data/site.json`。

## 分かっている制約

- 東急・西武・京急・小田急は列車時刻表が提供されていないため、ネットワークに入っていない。
- 乗換は一律 5 分。直通運転も乗換として扱っている。
- 地図の経路は駅と駅を直線で結んでいる（線路の形は描いていない）。
- 平日ダイヤのみ。静的版は集合時刻 19:00 / 20:00 の 2 つ。
