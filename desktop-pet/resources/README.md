# 角色素材热替换目录

本目录随安装包一起分发（打包后位于 `<安装目录>/resources/resources/`）。

## 当前版本（SVG 角色）
角色直接由 `renderer/index.html` 内的 SVG 绘制，无需外部素材即可运行。
如果你想替换外观，直接编辑 `renderer/index.html` 里的 `<svg id="char">` 路径与 `:root` 颜色变量即可。

## 未来接入真·Live2D 时的素材规范
若后续改用 pixi-live2d-display，把模型放到本目录：

```
resources/
  model/
    baobei.model3.json     # 模型入口
    baobei.moc3            # 网格数据
    baobei.physics3.json   # 物理（辫子/背带摆动）
    textures/
      texture_00.png
    motions/
      idle.motion3.json    # 呼吸
      tap_head.motion3.json
      tap_body.motion3.json
```

### 分层要求
- 头发（刘海 / 后发 / 左右麻花辫）独立图层，便于物理摆动
- 眼睛：眼白 / 瞳孔 / 上眼皮 分层（瞳孔用于跟随，眼皮用于眨眼）
- 脸颊腮红单独一层，控制害羞时透明度
- 背带裤：裤身 / 背带 / 口袋 分层

### 参数命名约定（Live2D 标准参数）
- `ParamAngleX` / `ParamAngleY`：头部跟随鼠标
- `ParamEyeBallX` / `ParamEyeBallY`：眼球跟随
- `ParamEyeLOpen` / `ParamEyeROpen`：眨眼
- `ParamMouthOpenY` / `ParamMouthForm`：嘴型（开心/哈欠）
- `ParamCheek`：腮红
- `ParamBreath`：呼吸
- `ParamHairFront` / `ParamHairSide`：头发物理
