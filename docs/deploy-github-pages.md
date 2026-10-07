# GitHub Pages に公開する手順

## 1. なぜ事前計算にしたか（まずここを読む）

**サーバ版（`server.py`）はそのままでは GitHub Pages に載らない。** Pages は静的ファイルしか配れない。
素直な解きかたは「時刻表をブラウザに送って、探索もブラウザでやる」だが、**これは規約でできない。**

> **公共交通オープンデータ基本ライセンス 第8条4項(1)**
> 基本ライセンスデータ等や、その複製物および派生データ（…元のデータの全部または**大部分を復元可能である**データをいう）を、
> 有償・無償を問わず、**第三者が再利用可能な状態で公開、再配布、公衆送信および譲渡すること**（を禁止）

列車時刻表 25,671 本をバイナリで配れば、それは元データの復元そのものなので抵触する。
**チャレンジ限定ライセンス（JR東日本・京王・東武・相鉄）にも同じ条項がある。**
一方で「探索結果のような少量の派生物」は射程外と読める。

→ **配るのは「自宅 × 候補駅」の計算結果だけ**にした。時刻表はこのリポジトリの `data/raw/`（git 管理外）に留める。

| 配るもの | 中身 | 復元できるか |
|---|---|---|
| `home/<駅>.json` | その駅に住む人の、候補駅ごとの**帰宅リミット**と**所要時間** | 数値 2 つ/組だけ。できない |
| `bus/<駅>.json` | その駅から乗れるバス停と**最終便の時刻**、最終便ごとのリミット | 1 日 1 本ぶん。できない |
| `route/<候補>.json` | 帰りの経路の**駅の並びと路線名**。時刻は**出発時刻のみ**（＝リミットと同じ値） | 途中駅の時刻を含まない |
| `bars/<候補>.json` | OpenStreetMap の飲み屋（ODbL、出典表示で再配布可） | — |

## 2. 作る

```bash
python3 scripts/build_static.py          # 全部（約 70 分。CPU 2 コアでの実測）
python3 scripts/build_static.py 20       # 試し（自宅 20 件だけ。約 1 分）
```

- 出力は `site/`。このディレクトリをそのまま公開する。
- **`site/` は作り直す前に消す**（`rm -rf site`）。前のビルドの残りが混ざる。
- 計算量: 逆向き探索 1,232（自宅）＋ 632（駅×最終バス時刻の組）＋ 順方向探索 1,232×2（集合時刻）。
- **集合時刻より前に走り終わる便は読み込まない**（`Network(since=...)`）。
  19 時以降に出る経路しか使わないので結果は変わらず、便が 25,671 → 8,691 に減って**探索が 2.8 倍速くなる**
  （西船橋のリミットは絞る前も後も 00:08 で一致することを確認した）。
- できあがりは **約 45MB / 約 5,000 ファイル**。訪問者が落とすのは 1 回あたり **250KB 程度**
  （`meta.json` ＋ 参加者ぶんの `home/*.json` ＋ 選んだ駅の `route`・`bars`）。

### 事前計算にしたことで決まる制約

- **集合時刻は 19:00 / 20:00 の 2 つ**（`PRESETS`）。所要時間は集合時刻ごとに別々に探索するので、
  増やすと `home/*.json` と計算時間がそのぶん増える（1 つ増やすごとに +20 分ほど）。
  サーバ版（`server.py`）は任意の時刻で計算できるので、検証はそちらで行う。
- **候補駅は飲み屋 10 軒以上の 292 駅**（`CAND_MIN_BARS`）。画面の「飲み屋 最低」スライダーはこの中から絞る。
- 自宅に選べるのはネットワークに入っている **1,232 駅**。

## 3. 公開する

リポジトリは**ユーザーが GitHub で作る**。作ったら:

```bash
git remote add origin git@github.com:<ユーザー名>/nomikai-navi.git
git push -u origin main
```

**ブランチ名は `main` にする。** GitHub が自動で作る `github-pages` 環境には
「デプロイできるのは `main` だけ」というブランチ制限が付く。`master` で push すると
ワークフローは走るが **`Branch "master" is not allowed to deploy to github-pages due to
environment protection rules.`** で落ちる（Pages の Source 設定とは別の話なので紛らわしい）。
制限は Settings → Environments → github-pages からも変えられるが、`main` に揃えるほうが早い。

GitHub の **Settings → Pages → Build and deployment → Source** を **GitHub Actions** にして、
`.github/workflows/pages.yml`（このリポジトリに入れてある）が `site/` を配る。

- `site/.nojekyll` を置いてある（Jekyll に処理させない）。
- 公開 URL は `https://<ユーザー名>.github.io/nomikai-navi/`。実際の公開先は https://coins-dawn.github.io/nomikai-navi/ 。
- **`site/` も git にコミットする**（Pages は生成物を配るため）。`.gitignore` で除外しないこと。

## 4. 公開前に必ず確認する

- [ ] `data/site.json` の **問い合わせ先**（`contact_url`）が自分のものになっているか。
      開発者ガイドライン 3.1 は「提供元の明示」「正確性を保証しない旨」「**問い合わせ先**」の 3 点を求めている。
      一般ユーザーが交通事業者へ直接問い合わせないようにするための項目。
- [ ] `data/site.json` の **取得日**（`acquired`）が実際にデータを取った日になっているか。
      ガイドラインは**静的データの取得日時の表示**を求めている。
- [ ] 画面左下の「使っているオープンデータ」に上の 3 点＋取得日が出ているか。
- [ ] JR東日本・京王・東武・相鉄は**チャレンジ限定ライセンス**のデータ。利用条件は提供元の規約に従うこと。

## 5. 更新する

配信データが更新されたら、`scripts/fetch_odpt.py` → `build_bars.py` → `build_index.py` → `build_static.py` の順に流し直し、
`data/site.json` の `acquired` を直してから `main` に push する。push すれば自動で再デプロイされる。

画面だけ直したときは `build_static.py` を全部流さなくてよい:

```bash
cp frontend/index.html site/index.html && cp frontend/engine-static.js site/engine.js
python3 scripts/verify_static.py --compare   # サーバ版（:8000）と突き合わせる
```
