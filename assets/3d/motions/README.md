# 人形の動き

## mixamo/

[Mixamo](https://www.mixamo.com/)（Adobe）の動き。Adobe ID があれば無料で、個人・商用・非営利の作品にロイヤリティなしで使える。動きのファイルそのものは再配布できないので、FBX は git に入れない（.gitignore）。使う人が自分で落として置く（docs/decisions.md D-027）。

落とし方：

1. mixamo.com にログインし、Characters で **Y Bot** を選ぶ。
2. Animations で動きを選び、Download で **FBX Binary(.fbx) / Without Skin / 30 / none** にして落とす。
3. ファイル名を小文字と `_` に直して、ここに置く。

| ファイル | Mixamo の名前（説明） |
|---|---|
| `sitting_idle.fbx` | Sitting Idle（Sitting In Chair Hands Resting On Thighs） |
| `sitting_talking.fbx` | Sitting Talking（Sitting And Talking To Another Person。一覧の最初のもの） |
| `sitting_laughing.fbx` | Sitting Laughing（Sitting While Laughing） |
| `sitting_impatient.fbx` | Sitting（Sitting And Impatiently Waiting） |
| `sitting_rubbing_arm.fbx` | Sitting Rubbing Arm（Sitting And Rubbing Arm） |
| `disbelief_forward.fbx` | Sitting Disbelief（Sitting In Disbelief With Head Forward） |
| `disbelief_back.fbx` | Sitting Disbelief（Sitting In Disbelief With Head Back） |
| `scared.fbx` | Scared（Surprised Jumping Out Of Seat） |

使い方は `scripts/blender/kit.py` の `Character.play` と `Character.bake`。
