# 工业视觉小样本异常检测 PoC 项目开发需求

## 一、项目背景

我正在研究工业视觉缺陷检测技术，希望验证在正常样本较少、缺陷样本极少的情况下，能否通过小样本异常检测算法识别产品表面缺陷。

本次项目属于技术可行性验证（PoC），不需要生产级系统，也不需要接入真实工业相机。

**实验对象：白色方形陶瓷瓷砖。**

核心目标：

1. 使用 AI 生成模拟工业视觉图片。
2. 仅使用正常瓷砖图片训练异常检测模型。
3. 使用缺陷瓷砖图片进行验证。
4. 输出正常/异常判定、异常评分和异常热力图。
5. 评估缺陷检出率、误报率和推理速度。
6. 判断这条技术路线是否值得继续用于真实工业产品检测。

## 二、技术选型

- 开发语言：Python 3.11
- 环境管理：uv
- 深度学习框架：PyTorch
- 异常检测框架：Anomalib
- 首选算法：PatchCore
- 运行设备：Windows + NVIDIA RTX 3080
- 实验界面：Gradio
- 图片格式：PNG
- 图片分辨率：1024×1024

优先使用稳定版本，不使用未经验证的 API。开发前检查 Anomalib 当前版本及对应官方文档，确保代码能够实际运行。

## 三、数据集生成

### 3.1 第一阶段：小规模实验

先生成：

- 正常瓷砖：20 张
- 划痕缺陷：4 张
- 裂纹缺陷：3 张
- 污渍缺陷：3 张

总计 30 张。

### 3.2 第二阶段：完整实验

第一阶段验证成功后扩充至：

- 正常瓷砖：200 张
- 划痕缺陷：20 张
- 裂纹缺陷：20 张
- 污渍缺陷：20 张

总计 260 张。

### 3.3 正常瓷砖图片生成提示词

使用以下英文提示词作为图片生成基础：

**Prompt:**

A realistic industrial machine vision inspection photograph of a single plain white square ceramic tile, viewed directly from above at a perfectly perpendicular 90-degree angle.

The tile is centered on a uniform neutral gray matte background. The entire tile is visible with consistent margins on all four sides.

The ceramic surface is smooth, clean, intact, and uniformly white, with subtle natural material texture.

Soft and even industrial inspection lighting, minimal shadows, no strong reflections, sharp focus, high detail, realistic camera image.

Fixed camera position, fixed focal length, consistent object scale, consistent background, consistent illumination.

No defects, no scratches, no cracks, no stains, no chips, no dirt, no markings, no text, no logos, no watermark, no additional objects.

Square image, 1024x1024 resolution.

**生成要求：**

1. 所有图片保持相同的拍摄角度。
2. 瓷砖尺寸和位置基本一致。
3. 背景、光照基本一致。
4. 允许瓷砖存在轻微自然纹理差异。
5. 允许轻微位置变化，但不能大幅旋转或改变透视。
6. 不允许正常样本出现明显缺陷。
7. 每张图片必须独立保存。
8. 不要简单复制同一张图片充当不同样本。

### 3.4 缺陷图片生成原则

优先使用正常瓷砖底图进行局部编辑，而不是完全重新生成缺陷瓷砖。

必须保持：

- 瓷砖主体不变。
- 背景不变。
- 光照不变。
- 拍摄角度不变。
- 图像尺寸不变。
- 除指定缺陷外，其他区域尽量保持像素一致。

#### A. 划痕缺陷 Prompt

Using the provided clean ceramic tile image as the exact base image, introduce one realistic thin surface scratch on the white ceramic tile.

The scratch should be subtle but clearly visible, with irregular edges and realistic surface damage texture.

Modify only the local scratch region. Preserve the original tile, background, lighting, perspective, camera position, and all unaffected pixels.

Do not introduce any other defects, text, markings, or objects.

#### B. 裂纹缺陷 Prompt

Using the provided clean ceramic tile image as the exact base image, introduce one realistic irregular hairline crack on the ceramic surface.

The crack should have natural branching or uneven geometry, with subtle dark lines and realistic ceramic fracture characteristics.

Modify only the crack region. Preserve all other visual details of the original image.

Do not add additional defects.

#### C. 污渍缺陷 Prompt

Using the provided clean ceramic tile image as the exact base image, introduce one small realistic surface stain.

The stain should have irregular boundaries, subtle color variation, and realistic contact with the ceramic material.

Modify only the stain region. Preserve the original image outside the defect region.

Do not add additional objects or defects.

### 3.5 缺陷变化要求

每种缺陷需要随机改变：

- 缺陷位置。
- 缺陷长度。
- 缺陷宽度。
- 缺陷方向。
- 缺陷形状。
- 缺陷严重程度。

严重程度分为轻度、中度、重度。

禁止所有缺陷都出现在瓷砖中心。

尽量避免生成规律性、重复性的缺陷图案。

## 四、数据集组织

使用以下目录结构：

```text
datasets/
└── ceramic_tile/
    ├── train/
    │   └── good/
    ├── val/
    │   ├── good/
    │   └── bad/
    ├── test/
    │   ├── good/
    │   └── bad/
    └── metadata.csv
```

第一阶段样本较少，仅用于流程验证，不输出具有统计意义的准确率结论。

第二阶段数据划分：

- 正常训练集：160 张
- 正常验证集：20 张
- 正常测试集：20 张
- 缺陷验证集：30 张
- 缺陷测试集：30 张

缺陷图片不参与 PatchCore 正常特征库训练。

生成 metadata.csv，记录图片编号、正常/缺陷标签、缺陷类型、生成提示词、原始底图 ID、随机种子和数据集划分。

同一原始底图及其衍生图片不能跨越训练、验证和测试集合，避免数据泄漏。

## 五、异常检测模型

使用 PatchCore 算法。

要求：

1. 使用 ImageNet 预训练特征提取器。
2. 仅使用正常图片构建特征库。
3. 支持 GPU 加速。
4. 支持保存模型。
5. 支持加载已有模型。
6. 支持单张图片推理。
7. 支持批量推理。
8. 输出异常评分。
9. 输出异常热力图。
10. 支持设置异常判定阈值。

训练阶段不需要缺陷标签。

使用验证集选择判定阈值，测试集仅用于最终评估，不允许根据测试集反复调整阈值。

注意：1024×1024 是原始图片尺寸，不能默认直接缩放至低分辨率而不评估细小缺陷信息损失。第一版可以使用较低输入分辨率跑通流程，随后增加高分辨率 ROI 或分块推理对照实验。

## 六、实验可视化界面

使用 Gradio 构建一个简洁的本地 Web 页面。

页面包含三个主要功能。

### 6.1 数据集管理

显示：

- 正常样本数量。
- 缺陷样本数量。
- 各缺陷类别数量。
- 图片缩略图。
- 数据集划分信息。

支持上传或导入已经生成的图片。

AI 图片生成模块可以独立实现，不要求训练程序必须直接调用生图 API。

如果没有可用的图片生成 API，不得伪造生成结果，应提供提示词导出和图片批量导入功能。

### 6.2 模型训练

支持：

- 选择数据集。
- 设置输入分辨率。
- 设置特征库采样比例。
- 开始训练。
- 查看训练日志。
- 保存训练结果。

### 6.3 缺陷检测

支持上传图片并显示：

1. 原始图片。
2. 异常热力图。
3. 热力图叠加结果。
4. 异常评分。
5. OK / NG 判定。
6. 单张推理耗时。

如果模型能够输出像素级异常图，展示异常区域定位结果。

## 七、模型评估

计算：

- AUROC。
- Precision。
- Recall。
- F1-score。
- 正常样本误报率。
- 缺陷样本漏检率。
- 平均推理耗时。
- P50 / P95 推理耗时。

记录各缺陷类别的检测表现。

输出混淆矩阵和异常评分分布。

如果缺少真实像素级缺陷标注，不得宣称已经验证像素级定位准确率。可以展示热力图供人工观察。

第一轮实验只验证技术流程。

第二轮实验再根据实际测试结果判断模型效果。

## 八、避免 AI 合成数据造成虚假结论

这是本项目的重要要求。

AI 生成的正常图片和缺陷图片可能存在不同的生成痕迹，模型可能识别这些痕迹，而不是真正识别缺陷。

因此：

1. 尽量基于相同的正常底图生成缺陷。
2. 保持正常和缺陷图片的生成流程一致。
3. 避免缺陷图存在额外的背景、曝光或压缩差异。
4. 对不同生成批次进行独立测试。
5. 对训练和测试数据进行重复图片及近重复图片检查。
6. 不将合成数据测试结果等同于真实工业场景效果。

完成合成数据实验后，增加公开真实工业异常检测数据集作为对照，例如 MVTec AD。

只有在真实数据集上也取得合理表现，才能进一步支持技术路线的可行性。

## 九、项目交付要求

请完成一个可以在本地运行的完整 PoC 项目，包括：

- Python 项目代码。
- pyproject.toml。
- 数据集管理模块。
- PatchCore 训练模块。
- 模型推理模块。
- Gradio Web 页面。
- 图片生成提示词模板。
- README.md。
- Windows 安装和启动说明。
- 模型评估脚本。

代码需要模块化，避免所有功能写在单个 Python 文件中。

不要过度设计，不需要数据库、用户系统、权限管理、微服务或 Docker 集群。

## 十、实施顺序

请严格按照以下顺序开发：

**阶段 1：** 创建项目结构和依赖环境。

**阶段 2：** 实现数据集导入与校验。

**阶段 3：** 使用少量测试图片跑通 PatchCore 训练。

**阶段 4：** 实现单张图片异常检测及热力图。

**阶段 5：** 实现 Gradio 可视化页面。

**阶段 6：** 扩充数据集并进行完整评估。

**阶段 7：** 增加真实工业数据集对照实验。

每个阶段完成后执行必要的测试，修复问题后再继续。

不要仅提供设计方案或伪代码，请实际编写可运行代码。

最终目标不是追求复杂架构，而是回答一个问题：

**仅使用少量正常产品图片训练的 PatchCore，能否有效识别此前没有见过的表面缺陷？**