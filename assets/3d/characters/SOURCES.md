# 3D の人形（出典とライセンス）

## 自前の人形（own_*.glb）

`scripts/blender/make_characters.py` が Blender の中で作った（2026-11-25、docs/decisions.md D-031）。形はメタボール、色は単色の材質だけで、外部の素材・画像・生成 AI は使っていない。このプロジェクトの著作物で、クレジットは要らない。作り直すときは、スクリプトを直して書き出し直す（glb は手で直さない）。

| ファイル | 人形 | 身長 |
|---|---|---|
| `own_young_man.glb` | 若い男（パーカー・ジーンズ） | 1.72 m |
| `own_young_woman.glb` | 若い女（ブラウス・スカート・ボブ） | 1.60 m |
| `own_old_man.glb` | 年配の男（カーディガン・眼鏡・口ひげ） | 1.66 m |
| `own_old_woman.glb` | 年配の女（カーディガン・眼鏡・おだんご） | 1.52 m |

## Quaternius（前の人形）

どれも Quaternius の作品で、ライセンスは CC0 1.0（パブリックドメイン。商用可、クレジット不要）。2026-11-24 に Poly Pizza から入手した（docs/decisions.md D-027）。

| ファイル | 元の名前 | 入手先 | 収録パック |
|---|---|---|---|
| `casual_man.glb` | Casual Character | https://poly.pizza/m/kZ3DmIoGip | Ultimate Modular Men Pack |
| `casual_woman.glb` | Animated Woman | https://poly.pizza/m/9kF7eTDbhO | Ultimate Modular Women Pack |

作者のサイト：https://quaternius.com/
